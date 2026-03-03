"""
NLI Verifier — Non-LLM Entailment Checking
============================================

Uses DeBERTa-v3 fine-tuned on NLI to verify whether a claim
is entailed by its cited evidence. No LLM involved — deterministic,
reproducible, and free to run locally.

This breaks the "LLM checking LLM" circularity that causes
correlated failures in the evaluation pipeline.

Models (configurable):
  - cross-encoder/nli-deberta-v3-base   (~440MB, 90% MNLI, faster)
  - cross-encoder/nli-deberta-v3-large  (~1.4GB, 92% MNLI, best accuracy)

Requirements:
  pip install transformers torch sentencepiece

Usage:
  from nli_verifier import NLIVerifier
  nli = NLIVerifier()                     # loads model once
  result = nli.check(claim, evidence)     # returns {verdict, scores, ...}
  results = nli.check_batch(claims, evidences)  # batch mode
"""

import os
import re
import time
import threading
from typing import Optional

# ============================================================
# Configuration
# ============================================================

# Model options — base is the default (good tradeoff of speed vs accuracy)
NLI_MODEL_BASE = "cross-encoder/nli-deberta-v3-base"
NLI_MODEL_LARGE = "cross-encoder/nli-deberta-v3-large"

# Label ordering for cross-encoder NLI models
# IMPORTANT: cross-encoder models output [contradiction, entailment, neutral]
LABEL_NAMES = ["contradiction", "entailment", "neutral"]

# Thresholds
ENTAILMENT_THRESHOLD = 0.65    # Minimum entailment prob to consider "supported"
CONTRADICTION_THRESHOLD = 0.70  # Minimum contradiction prob to flag as "contradicted"

# Max token length for the model (DeBERTa handles up to 512 tokens)
MAX_SEQ_LENGTH = 512

# Environment variable to select model size
# Set NLI_MODEL=large to use the large model
MODEL_SIZE_ENV = os.environ.get("NLI_MODEL_SIZE", "base")


class NLIVerifier:
    """
    Singleton-style NLI verifier using DeBERTa.
    Loads the model once on first use, then reuses for all checks.
    """

    def __init__(self, model_size: str = None, device: str = None):
        """
        Initialize the NLI verifier.

        Args:
            model_size: "base" or "large". Defaults to NLI_MODEL_SIZE env var or "base".
            device: "cuda", "cpu", or None (auto-detect).
        """
        self.model_size = model_size or MODEL_SIZE_ENV
        self.model_name = NLI_MODEL_LARGE if self.model_size == "large" else NLI_MODEL_BASE
        self._device_preference = device
        self._model = None
        self._tokenizer = None
        self._device = None
        self._load_time = None
        self._lock = threading.Lock()  # Thread safety for concurrent inference

    def _ensure_loaded(self):
        """Lazy-load the model on first use."""
        if self._model is not None:
            return

        import torch
        from transformers import AutoTokenizer, AutoModelForSequenceClassification

        start = time.time()
        print(f"    Loading NLI model: {self.model_name}...")

        # Device selection
        if self._device_preference:
            self._device = torch.device(self._device_preference)
        elif torch.cuda.is_available():
            self._device = torch.device("cuda")
        else:
            self._device = torch.device("cpu")

        self._tokenizer = AutoTokenizer.from_pretrained(self.model_name)
        self._model = AutoModelForSequenceClassification.from_pretrained(self.model_name)
        self._model.to(self._device)
        self._model.eval()

        self._load_time = time.time() - start
        print(f"    NLI model loaded in {self._load_time:.1f}s on {self._device}")

    def check(self, claim: str, evidence: str) -> dict:
        """
        Check if a claim is entailed by the evidence.

        Args:
            claim: The hypothesis (atomic claim to verify)
            evidence: The premise (source text from the cited page)

        Returns:
            {
                "verdict": "entailed" | "neutral" | "contradicted",
                "scores": {"entailment": float, "neutral": float, "contradiction": float},
                "confidence": float (the winning score),
                "detail": str
            }
        """
        with self._lock:
            self._ensure_loaded()
            import torch

            # Clean inputs
            claim = self._clean_text(claim)
            evidence = self._clean_text(evidence)

            if not claim or not evidence:
                return {
                    "verdict": "neutral",
                    "scores": {"entailment": 0.0, "neutral": 1.0, "contradiction": 0.0},
                    "confidence": 0.0,
                    "detail": "Empty claim or evidence."
                }

            # Truncate evidence if too long (keep claim short, evidence can be long)
            # DeBERTa handles 512 tokens total; claim is typically 20-50 tokens
            # Leave ~400 tokens for evidence
            if len(evidence) > 1500:
                evidence = evidence[:1500]

            # Tokenize: premise=evidence, hypothesis=claim
            inputs = self._tokenizer(
                evidence, claim,
                truncation=True,
                max_length=MAX_SEQ_LENGTH,
                return_tensors="pt",
                padding=True,
            ).to(self._device)

            with torch.no_grad():
                logits = self._model(**inputs).logits
                probs = torch.softmax(logits, dim=-1)[0].cpu().tolist()

            # Map to labels: cross-encoder outputs [contradiction, entailment, neutral]
            scores = {
                "contradiction": round(probs[0], 4),
                "entailment": round(probs[1], 4),
                "neutral": round(probs[2], 4),
            }

            # Determine verdict
            if scores["entailment"] >= ENTAILMENT_THRESHOLD:
                verdict = "entailed"
                confidence = scores["entailment"]
                detail = f"NLI: Claim is entailed by evidence (p={confidence:.2%})"
            elif scores["contradiction"] >= CONTRADICTION_THRESHOLD:
                verdict = "contradicted"
                confidence = scores["contradiction"]
                detail = f"NLI: Claim contradicts evidence (p={confidence:.2%})"
            else:
                verdict = "neutral"
                confidence = scores["neutral"]
                # Provide more useful detail
                top_label = max(scores, key=scores.get)
                detail = (f"NLI: Evidence neither supports nor contradicts claim. "
                          f"Top: {top_label}={scores[top_label]:.2%}")

            return {
                "verdict": verdict,
                "scores": scores,
                "confidence": round(confidence, 4),
                "detail": detail,
            }

    def check_batch(self, claims: list[str], evidences: list[str]) -> list[dict]:
        """
        Batch verification for efficiency.
        Each (claim, evidence) pair is checked independently.
        Thread-safe: uses a lock to prevent concurrent model access.

        Args:
            claims: List of hypothesis strings
            evidences: List of premise strings (same length as claims)

        Returns:
            List of result dicts (same format as check())
        """
        assert len(claims) == len(evidences), "claims and evidences must be same length"
        with self._lock:
            self._ensure_loaded()
            import torch

            # Clean inputs
            clean_claims = [self._clean_text(c) for c in claims]
            clean_evidences = [self._clean_text(e)[:1500] for e in evidences]

            # Tokenize all pairs at once
            inputs = self._tokenizer(
                clean_evidences, clean_claims,  # premise, hypothesis order
                truncation=True,
                max_length=MAX_SEQ_LENGTH,
                return_tensors="pt",
                padding=True,
            ).to(self._device)

            with torch.no_grad():
                logits = self._model(**inputs).logits
                all_probs = torch.softmax(logits, dim=-1).cpu().tolist()

            results = []
            for i, probs in enumerate(all_probs):
                scores = {
                    "contradiction": round(probs[0], 4),
                    "entailment": round(probs[1], 4),
                    "neutral": round(probs[2], 4),
                }

                if scores["entailment"] >= ENTAILMENT_THRESHOLD:
                    verdict = "entailed"
                    confidence = scores["entailment"]
                    detail = f"NLI: entailed (p={confidence:.2%})"
                elif scores["contradiction"] >= CONTRADICTION_THRESHOLD:
                    verdict = "contradicted"
                    confidence = scores["contradiction"]
                    detail = f"NLI: contradicted (p={confidence:.2%})"
                else:
                    verdict = "neutral"
                    confidence = scores["neutral"]
                    top_label = max(scores, key=scores.get)
                    detail = f"NLI: neutral (top: {top_label}={scores[top_label]:.2%})"

                results.append({
                    "verdict": verdict,
                    "scores": scores,
                    "confidence": round(confidence, 4),
                    "detail": detail,
                })

            return results

    @staticmethod
    def _clean_text(text: str) -> str:
        """Strip citations, markdown, and normalize whitespace."""
        if not text:
            return ""
        # Remove citation markers
        text = re.sub(r'\[\[doc:[^\]]+\]\]', '', text)
        text = re.sub(r'\[\[chunk:[^\]]+\]\]', '', text)
        # Remove markdown formatting
        text = re.sub(r'[*_]{1,3}', '', text)
        text = re.sub(r'#+\s*', '', text)
        # Normalize whitespace
        text = re.sub(r'\s+', ' ', text).strip()
        return text


# ============================================================
# Singleton accessor for pipeline integration
# ============================================================

_verifier_instance: Optional[NLIVerifier] = None


def get_nli_verifier(model_size: str = None) -> NLIVerifier:
    """Get or create the singleton NLI verifier instance.
    Raises ImportError if torch is not available."""
    global _verifier_instance
    if _verifier_instance is None:
        # Check dependencies before creating instance
        try:
            import torch  # noqa: F401
            from transformers import AutoTokenizer, AutoModelForSequenceClassification  # noqa: F401
        except ImportError as e:
            raise ImportError(
                f"NLI verifier requires torch and transformers. "
                f"Install with: pip install torch transformers sentencepiece. "
                f"Original error: {e}"
            )
        _verifier_instance = NLIVerifier(model_size=model_size)
    return _verifier_instance


def nli_check_claim(claim_text: str, evidence_text: str,
                    model_size: str = None) -> dict:
    """
    Convenience function: verify a single claim against evidence.
    Loads model on first call, reuses thereafter.
    """
    verifier = get_nli_verifier(model_size)
    return verifier.check(claim_text, evidence_text)


def nli_check_batch(claims: list[str], evidences: list[str],
                    model_size: str = None) -> list[dict]:
    """
    Convenience function: verify a batch of claims.
    """
    verifier = get_nli_verifier(model_size)
    return verifier.check_batch(claims, evidences)


# ============================================================
# Test
# ============================================================

if __name__ == "__main__":
    print("=== NLI Verifier Test ===\n")

    verifier = NLIVerifier(model_size="base")

    test_cases = [
        {
            "name": "Clear entailment",
            "claim": "Dragon 1 uses a 16/48 erasure coding scheme",
            "evidence": "Dragon 1 cluster uses a 16/48 erasure coding scheme. Any 16 of 48 shares can reconstruct the original data.",
            "expected": "entailed",
        },
        {
            "name": "Clear contradiction (Ed25519 vs sr25519)",
            "claim": "The data wallet is an Ed25519 keypair",
            "evidence": "CLI outputs: mnemonic, key type: sr25519, address, public key",
            "expected": "contradicted",
        },
        {
            "name": "Neutral (inference not stated)",
            "claim": "DDC operates without a centralized coordinator",
            "evidence": "Nodes can self-bootstrap using themselves as bootstrap node. DHT-based peer discovery with replication factor k=5.",
            "expected": "neutral",
        },
        {
            "name": "Entailment (paraphrased)",
            "claim": "Nodes can continue working even when the blockchain is unavailable",
            "evidence": "Storage and cache nodes use disk-persisted blockchain indexes so they can restart and function even if the blockchain is unavailable.",
            "expected": "entailed",
        },
        {
            "name": "Overstated (cryptographically verified)",
            "claim": "DDC provides a cryptographically verified audit trail for every data operation",
            "evidence": "DAC is a trust layer that captures real-time traffic and compute metrics, serving as the verified data source for blockchain-level inspection.",
            "expected": "neutral",  # "verified data source" ≠ "cryptographically verified audit trail for every operation"
        },
    ]

    for tc in test_cases:
        result = verifier.check(tc["claim"], tc["evidence"])
        icon = {"entailed": "✅", "neutral": "🟡", "contradicted": "❌"}.get(result["verdict"], "?")
        match = "PASS" if result["verdict"] == tc["expected"] else "SOFT" if (
            tc["expected"] == "neutral" and result["verdict"] != "entailed") else "FAIL"
        print(f"  {icon} {tc['name']}: {result['verdict']} (expected {tc['expected']}) [{match}]")
        print(f"     Scores: E={result['scores']['entailment']:.2%} "
              f"N={result['scores']['neutral']:.2%} "
              f"C={result['scores']['contradiction']:.2%}")
        print(f"     {result['detail']}")
        print()

    # Batch test
    print("=== Batch Test ===")
    claims_batch = [tc["claim"] for tc in test_cases]
    evidence_batch = [tc["evidence"] for tc in test_cases]
    batch_results = verifier.check_batch(claims_batch, evidence_batch)
    for tc, r in zip(test_cases, batch_results):
        print(f"  {tc['name']}: {r['verdict']} (E={r['scores']['entailment']:.2%})")
