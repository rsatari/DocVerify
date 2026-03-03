"""
Cross-LLM Checker + Verdict Aggregator
========================================

Two components:

1. Cross-LLM Checker
   Uses a DIFFERENT model provider than the answer generator (Claude)
   to independently verify each claim against evidence.
   Default: Gemini 2.5 Flash ($0.30/1M input, $2.50/1M output) — cheapest
   option that's still highly capable. Falls back to GPT-4.1-mini if
   Gemini is unavailable.

   Why cross-provider matters:
   - Claude and GPT share correlated failure modes
   - Different training data → different blind spots
   - Research shows 15-25% hallucination reduction vs same-provider checking

2. Verdict Aggregator
   Combines all verification signals (citation grounding, NLI, cross-LLM)
   into a single pass/fail/flag verdict per claim using majority voting
   with weighted confidence.

Requirements:
  pip install google-generativeai   # for Gemini
  # OR
  pip install openai                # for GPT-4.1-mini fallback

  Both are optional — pipeline works with just grounding + NLI.
"""

import os
import re
import json
import time
import threading
from typing import Optional

# ============================================================
# Configuration
# ============================================================

# Provider priority: try Gemini first (cheapest), then GPT
GEMINI_MODEL = "gemini-3.1-pro-preview"
GPT_FALLBACK_MODEL = "gpt-4.1-mini"

# Verdict thresholds
CROSS_LLM_BATCH_SIZE = 10  # Max claims per API call (Gemini supports batching in prompt)

# Aggregator weights — how much each verifier's opinion counts
WEIGHT_GROUNDING = 0.35    # Citation grounding (fast, deterministic, catches term mismatches)
WEIGHT_NLI = 0.40          # NLI entailment (semantic, catches meaning drift)
WEIGHT_CROSS_LLM = 0.25   # Cross-LLM (catches provider-specific bias)

# Final verdict thresholds
PASS_THRESHOLD = 0.60      # Weighted score >= this → pass
FAIL_THRESHOLD = 0.30      # Weighted score < this → fail
# Between FAIL and PASS → flag


# ============================================================
# 1. Cross-LLM Checker
# ============================================================

class CrossLLMChecker:
    """
    Verifies claims using a different LLM provider than the answer generator.
    Sends claim + evidence, gets a simple supported/unsupported/partial verdict.
    """

    def __init__(self):
        self._provider = None
        self._client = None
        self._available = False
        self._lock = threading.Lock()  # Thread safety for concurrent API calls
        self._init_provider()

    def _init_provider(self):
        """Try to initialize Gemini, fall back to GPT."""
        # Try Gemini first
        gemini_key = os.environ.get("GOOGLE_API_KEY") or os.environ.get("GEMINI_API_KEY")
        if gemini_key:
            try:
                # Try new SDK first (google.genai)
                try:
                    from google import genai as genai_new
                    self._client = genai_new.Client(api_key=gemini_key)
                    self._provider = "gemini_new"
                    self._available = True
                    print(f"    → Cross-LLM checker: Gemini ({GEMINI_MODEL}) [new SDK]")
                    return
                except (ImportError, Exception):
                    pass

                # Fall back to deprecated SDK (google.generativeai)
                import google.generativeai as genai
                genai.configure(api_key=gemini_key)
                self._client = genai.GenerativeModel(GEMINI_MODEL)
                self._provider = "gemini"
                self._available = True
                print(f"    → Cross-LLM checker: Gemini ({GEMINI_MODEL})")
                return
            except Exception as e:
                print(f"    ⚠ Gemini init failed: {e}")

        # Fall back to GPT
        openai_key = os.environ.get("OPENAI_API_KEY")
        if openai_key:
            try:
                from openai import OpenAI
                self._client = OpenAI(api_key=openai_key)
                self._provider = "openai"
                self._available = True
                print(f"    → Cross-LLM checker: OpenAI ({GPT_FALLBACK_MODEL})")
                return
            except Exception as e:
                print(f"    ⚠ OpenAI init failed: {e}")

        print(f"    → Cross-LLM checker: not available (no GOOGLE_API_KEY or OPENAI_API_KEY)")
        self._available = False

    @property
    def available(self) -> bool:
        return self._available

    def check_batch(self, claims: list[dict], page_index: dict) -> list[dict]:
        """
        Verify a batch of claims against their cited evidence.

        Args:
            claims: List of decomposed claims with cited_file, cited_page, text
            page_index: {(filename, page_num) → page_text}

        Returns:
            List of {verdict, confidence, detail} dicts (same order as claims)
        """
        if not self._available:
            return [{"verdict": "unavailable", "confidence": 0.0,
                     "detail": "Cross-LLM checker not configured"} for _ in claims]

        # Build claim-evidence pairs
        pairs = []
        for claim in claims:
            evidence = self._get_evidence(claim, page_index)
            pairs.append({
                "claim_id": claim.get("claim_id", "?"),
                "claim_text": claim.get("text", ""),
                "evidence_text": evidence[:2000] if evidence else "",
            })

        # Process in batches
        results = []
        for i in range(0, len(pairs), CROSS_LLM_BATCH_SIZE):
            batch = pairs[i:i + CROSS_LLM_BATCH_SIZE]
            batch_results = self._verify_batch(batch)
            results.extend(batch_results)

        return results

    def _get_evidence(self, claim: dict, page_index: dict) -> str:
        """Get the evidence text for a claim from the page index."""
        cited_file = claim.get("cited_file", "")
        cited_page = claim.get("cited_page", 0)
        if not cited_file or not cited_page:
            return ""

        # Direct lookup
        text = page_index.get((cited_file, cited_page), "")
        if text:
            return text

        # Fuzzy filename match
        for (f, p), t in page_index.items():
            if p == cited_page and (cited_file in f or f in cited_file):
                return t

        return ""

    def _verify_batch(self, pairs: list[dict]) -> list[dict]:
        """Send a batch of claim-evidence pairs to the cross-LLM."""
        if not pairs:
            return []

        # No lock needed — API calls are stateless and thread-safe
        # Build the prompt
        claims_text = ""
        for j, p in enumerate(pairs):
            claims_text += f"""
CLAIM {j+1} [{p['claim_id']}]:
  Claim: {p['claim_text'][:200]}
  Evidence: {p['evidence_text'][:500]}
"""

        prompt = f"""You are a fact-checker. For each claim below, determine if it is DIRECTLY SUPPORTED by the provided evidence text.

Rules:
- "supported": The evidence explicitly states or directly implies the claim
- "unsupported": The evidence does not address this claim, or the claim goes beyond what the evidence says
- "contradicted": The evidence directly contradicts the claim
- Be STRICT: if the claim uses different terminology than the evidence (e.g., "Ed25519" when evidence says "sr25519"), mark as contradicted
- If the claim makes an inference not stated in the evidence (e.g., "no centralized coordinator" when evidence only describes P2P), mark as unsupported

{claims_text}

Respond with ONLY a JSON array of objects, one per claim:
[{{"claim_id": "...", "verdict": "supported|unsupported|contradicted", "reason": "brief explanation"}}]

No markdown, no backticks, no commentary."""

        try:
            if self._provider in ("gemini", "gemini_new"):
                return self._call_gemini(prompt, pairs)
            elif self._provider == "openai":
                return self._call_openai(prompt, pairs)
        except Exception as e:
            print(f"    ⚠ Cross-LLM batch failed: {e}")
            return [{"verdict": "error", "confidence": 0.0,
                     "detail": f"API error: {str(e)[:100]}"} for _ in pairs]

    def _call_gemini(self, prompt: str, pairs: list[dict]) -> list[dict]:
        """Call Gemini API (supports both old and new SDK)."""
        if self._provider == "gemini_new":
            # New SDK: google.genai
            response = self._client.models.generate_content(
                model=GEMINI_MODEL,
                contents=prompt,
                config={"temperature": 0.0, "max_output_tokens": 1000},
            )
            # Track cost — estimate tokens from usage_metadata if available
            try:
                from agents.cost_tracker import track_cost
                um = getattr(response, 'usage_metadata', None)
                if um:
                    track_cost("cross_llm", "—", GEMINI_MODEL,
                               getattr(um, 'prompt_token_count', 0),
                               getattr(um, 'candidates_token_count', 0))
                else:
                    # Estimate: ~4 chars per token
                    track_cost("cross_llm", "—", GEMINI_MODEL,
                               len(prompt) // 4, len(response.text) // 4)
            except ImportError:
                pass
            return self._parse_response(response.text, pairs)
        else:
            # Old SDK: google.generativeai
            response = self._client.generate_content(
                prompt,
                generation_config={"temperature": 0.0, "max_output_tokens": 1000},
            )
            try:
                from agents.cost_tracker import track_cost
                um = getattr(response, 'usage_metadata', None)
                if um:
                    track_cost("cross_llm", "—", GEMINI_MODEL,
                               getattr(um, 'prompt_token_count', 0),
                               getattr(um, 'candidates_token_count', 0))
                else:
                    track_cost("cross_llm", "—", GEMINI_MODEL,
                               len(prompt) // 4, len(response.text) // 4)
            except ImportError:
                pass
            return self._parse_response(response.text, pairs)

    def _call_openai(self, prompt: str, pairs: list[dict]) -> list[dict]:
        """Call OpenAI API."""
        response = self._client.chat.completions.create(
            model=GPT_FALLBACK_MODEL,
            messages=[{"role": "user", "content": prompt}],
            temperature=0.0,
            max_tokens=1000,
        )
        try:
            from agents.cost_tracker import track_cost
            track_cost("cross_llm", "—", GPT_FALLBACK_MODEL,
                       response.usage.prompt_tokens, response.usage.completion_tokens)
        except (ImportError, AttributeError):
            pass
        return self._parse_response(response.choices[0].message.content, pairs)

    def _parse_response(self, text: str, pairs: list[dict]) -> list[dict]:
        """Parse the LLM response into verdict dicts."""
        # Strip markdown fences
        text = text.strip()
        text = re.sub(r'^```(?:json)?\s*', '', text)
        text = re.sub(r'\s*```$', '', text)

        try:
            verdicts = json.loads(text)
        except json.JSONDecodeError:
            # Try to extract JSON array from the response
            match = re.search(r'\[.*\]', text, re.DOTALL)
            if match:
                try:
                    verdicts = json.loads(match.group())
                except json.JSONDecodeError:
                    return [{"verdict": "error", "confidence": 0.0,
                             "detail": "Failed to parse cross-LLM response"} for _ in pairs]
            else:
                return [{"verdict": "error", "confidence": 0.0,
                         "detail": "No JSON in cross-LLM response"} for _ in pairs]

        # Map verdicts back to results
        results = []
        verdict_map = {v.get("claim_id", ""): v for v in verdicts} if verdicts else {}

        for p in pairs:
            v = verdict_map.get(p["claim_id"], {})
            raw_verdict = v.get("verdict", "error")
            reason = v.get("reason", "")

            if raw_verdict == "supported":
                results.append({
                    "verdict": "supported",
                    "confidence": 0.85,
                    "detail": f"Cross-LLM ({self._provider}): supported — {reason}"
                })
            elif raw_verdict == "contradicted":
                results.append({
                    "verdict": "contradicted",
                    "confidence": 0.90,
                    "detail": f"Cross-LLM ({self._provider}): contradicted — {reason}"
                })
            elif raw_verdict == "unsupported":
                results.append({
                    "verdict": "unsupported",
                    "confidence": 0.80,
                    "detail": f"Cross-LLM ({self._provider}): unsupported — {reason}"
                })
            else:
                results.append({
                    "verdict": "error",
                    "confidence": 0.0,
                    "detail": f"Cross-LLM: unparseable verdict '{raw_verdict}'"
                })

        return results


# ============================================================
# 2. Verdict Aggregator
# ============================================================

def aggregate_verdicts(claim: dict) -> dict:
    """
    Combine all verification signals into a single verdict.

    Signals (all optional — aggregator works with whatever is available):
      - claim["grounding"]: {verdict: grounded|ungrounded|mismatch|uncited, confidence}
      - claim["nli"]: {verdict: entailed|neutral|contradicted, confidence, scores}
      - claim["cross_llm"]: {verdict: supported|unsupported|contradicted, confidence}

    Returns:
      {
          "final_verdict": "pass" | "fail" | "flag",
          "final_confidence": float,
          "signals": {grounding: ..., nli: ..., cross_llm: ...},
          "reasoning": str
      }
    """
    grounding = claim.get("grounding", {})
    nli = claim.get("nli", None)
    cross_llm = claim.get("cross_llm", None)

    # ── Map each signal to a numeric score ──
    # Score: 1.0 = definitely supported, 0.0 = definitely unsupported/contradicted
    signals = {}
    reasoning_parts = []

    # Grounding signal
    g_verdict = grounding.get("verdict", "uncited")
    if g_verdict == "grounded":
        g_score = 0.7 + (0.3 * grounding.get("confidence", 0.5))
        signals["grounding"] = g_score
        reasoning_parts.append(f"Grounding: ✅ {g_score:.2f}")
    elif g_verdict == "mismatch":
        signals["grounding"] = 0.0
        reasoning_parts.append(f"Grounding: ❌ mismatch")
    elif g_verdict == "ungrounded":
        g_conf = grounding.get("confidence", 0)
        signals["grounding"] = g_conf * 0.4  # Partial credit for partial matches
        reasoning_parts.append(f"Grounding: ⚠️ ungrounded ({g_conf:.0%})")
    elif g_verdict == "uncited":
        # No citation — neutral, don't penalize or reward
        reasoning_parts.append(f"Grounding: ➖ uncited")
    else:
        reasoning_parts.append(f"Grounding: ? {g_verdict}")

    # NLI signal
    if nli:
        n_verdict = nli.get("verdict", "neutral")
        if n_verdict == "entailed":
            n_score = 0.6 + (0.4 * nli.get("confidence", 0.5))
            signals["nli"] = n_score
            reasoning_parts.append(f"NLI: ✅ entailed ({nli.get('confidence', 0):.0%})")
        elif n_verdict == "contradicted":
            signals["nli"] = 0.0
            reasoning_parts.append(f"NLI: ❌ contradicted ({nli.get('confidence', 0):.0%})")
        elif n_verdict == "neutral":
            # NLI neutral means "can't determine" — treat as genuinely neutral
            # Should NOT drag down a claim that passes grounding
            n_score = 0.50
            signals["nli"] = n_score
            reasoning_parts.append(f"NLI: 🟡 neutral")

    # Cross-LLM signal
    if cross_llm and cross_llm.get("verdict") not in ("error", "unavailable"):
        c_verdict = cross_llm.get("verdict", "error")
        if c_verdict == "supported":
            signals["cross_llm"] = 0.85
            reasoning_parts.append(f"Cross-LLM: ✅ supported")
        elif c_verdict == "contradicted":
            signals["cross_llm"] = 0.0
            reasoning_parts.append(f"Cross-LLM: ❌ contradicted")
        elif c_verdict == "unsupported":
            # "Unsupported" means Gemini couldn't confirm, not that it's wrong
            signals["cross_llm"] = 0.35
            reasoning_parts.append(f"Cross-LLM: ⚠️ unsupported")

    # ── Hard fail rules (override weighted scoring) ──

    # Rule 1: ANY verifier says "contradicted/mismatch" → fail
    if grounding.get("verdict") == "mismatch":
        return _verdict("fail", 0.0, signals,
                        "HARD FAIL: Citation grounding found term mismatch",
                        reasoning_parts)

    if nli and nli.get("verdict") == "contradicted" and nli.get("confidence", 0) >= 0.70:
        return _verdict("fail", 0.0, signals,
                        f"HARD FAIL: NLI detected contradiction ({nli['confidence']:.0%})",
                        reasoning_parts)

    if cross_llm and cross_llm.get("verdict") == "contradicted":
        return _verdict("fail", 0.05, signals,
                        "HARD FAIL: Cross-LLM detected contradiction",
                        reasoning_parts)

    # Rule 2: TWO verifiers say unsupported/ungrounded → fail
    negative_count = 0
    if grounding.get("verdict") == "ungrounded" and grounding.get("confidence", 0) == 0:
        negative_count += 1
    if nli and nli.get("verdict") == "contradicted":
        negative_count += 1
    if cross_llm and cross_llm.get("verdict") == "contradicted":
        negative_count += 1
    # Note: cross-LLM "unsupported" means "can't confirm" — NOT a contradiction.
    # It should not count toward majority fail.
    if negative_count >= 2:
        # But even majority fail should yield to strong grounding evidence
        if grounding.get("verdict") == "grounded" and grounding.get("confidence", 0) >= 0.66:
            reasoning_parts.append(f"MAJORITY OVERRIDE: {negative_count} negatives but grounding strong")
        else:
            return _verdict("fail", 0.10, signals,
                            f"MAJORITY FAIL: {negative_count} verifiers rejected",
                            reasoning_parts)

    # ── Grounding override ──
    # When grounding found strong evidence (term match ratio ≥ 0.66 AND verdict is "grounded"),
    # trust it over uncertain or contradicting NLI/cross-LLM signals.
    # 
    # Rationale: Grounding is deterministic — it literally found the key terms on the cited page.
    # NLI (DeBERTa) often returns "contradicted" on paraphrased technical claims because the
    # wording differs from the source. Cross-LLM "unsupported" means "can't confirm."
    # Neither of these should override physical evidence that the terms exist on the page.
    #
    # Exception: If BOTH NLI and cross-LLM say "contradicted" AND grounding confidence
    # is below 1.0 (partial match), defer to the verifiers.
    g_ratio = grounding.get("confidence", 0)
    g_is_strong = (grounding.get("verdict") == "grounded" and g_ratio >= 0.66)

    if g_is_strong:
        nli_contradicted = nli and nli.get("verdict") == "contradicted"
        xlm_contradicted = cross_llm and cross_llm.get("verdict") == "contradicted"

        # Only defer to verifiers when BOTH contradict AND grounding is partial
        both_contradict_partial = (nli_contradicted and xlm_contradicted and g_ratio < 1.0)

        if not both_contradict_partial:
            override_score = max(0.65, signals.get("grounding", 0.65))
            reasoning_parts.append(
                f"GROUNDING OVERRIDE: terms found ({g_ratio:.0%}), "
                f"NLI={'contradicted' if nli_contradicted else 'ok'}, "
                f"XLM={'contradicted' if xlm_contradicted else 'ok'} → {override_score:.2f}"
            )
            return _verdict("pass", override_score, signals,
                            f"Grounding override: strong match trumps uncertain/wrong verifiers",
                            reasoning_parts)

    # ── Weighted scoring ──
    if not signals:
        # No signals at all — uncited claim with no NLI/cross-LLM
        # Let it pass, evaluator will handle
        return _verdict("pass", 0.50, signals,
                        "No verification signals — passing through",
                        reasoning_parts)

    # Compute weighted average with available signals
    total_weight = 0.0
    weighted_sum = 0.0

    weight_map = {
        "grounding": WEIGHT_GROUNDING,
        "nli": WEIGHT_NLI,
        "cross_llm": WEIGHT_CROSS_LLM,
    }

    for signal_name, score in signals.items():
        w = weight_map.get(signal_name, 0.25)
        weighted_sum += score * w
        total_weight += w

    final_score = weighted_sum / total_weight if total_weight > 0 else 0.5

    # ── Determine verdict from score ──
    if final_score >= PASS_THRESHOLD:
        return _verdict("pass", final_score, signals,
                        f"Weighted score {final_score:.2f} ≥ {PASS_THRESHOLD}",
                        reasoning_parts)
    elif final_score < FAIL_THRESHOLD:
        return _verdict("fail", final_score, signals,
                        f"Weighted score {final_score:.2f} < {FAIL_THRESHOLD}",
                        reasoning_parts)
    else:
        return _verdict("flag", final_score, signals,
                        f"Weighted score {final_score:.2f} between thresholds — flagging",
                        reasoning_parts)


def _verdict(verdict: str, confidence: float, signals: dict,
             reasoning: str, parts: list) -> dict:
    """Build a verdict result dict."""
    return {
        "final_verdict": verdict,
        "final_confidence": round(confidence, 4),
        "signals": signals,
        "reasoning": reasoning,
        "signal_details": " | ".join(parts),
    }


# ============================================================
# Singleton
# ============================================================

_checker_instance: Optional[CrossLLMChecker] = None


def get_cross_llm_checker() -> CrossLLMChecker:
    """Get or create the singleton cross-LLM checker."""
    global _checker_instance
    if _checker_instance is None:
        _checker_instance = CrossLLMChecker()
    return _checker_instance


# ============================================================
# Test
# ============================================================

if __name__ == "__main__":
    print("=== Verdict Aggregator Test ===\n")

    test_cases = [
        {
            "name": "All three agree: supported",
            "claim": {
                "grounding": {"verdict": "grounded", "confidence": 0.9},
                "nli": {"verdict": "entailed", "confidence": 0.88},
                "cross_llm": {"verdict": "supported", "confidence": 0.85},
            },
            "expected": "pass",
        },
        {
            "name": "Grounding mismatch (hard fail)",
            "claim": {
                "grounding": {"verdict": "mismatch", "confidence": 0.95},
                "nli": {"verdict": "entailed", "confidence": 0.7},
                "cross_llm": {"verdict": "supported", "confidence": 0.85},
            },
            "expected": "fail",
        },
        {
            "name": "NLI contradicted (hard fail)",
            "claim": {
                "grounding": {"verdict": "grounded", "confidence": 0.8},
                "nli": {"verdict": "contradicted", "confidence": 0.85},
                "cross_llm": {"verdict": "supported", "confidence": 0.85},
            },
            "expected": "fail",
        },
        {
            "name": "Two say unsupported (majority fail)",
            "claim": {
                "grounding": {"verdict": "ungrounded", "confidence": 0.0},
                "nli": {"verdict": "neutral", "confidence": 0.5},
                "cross_llm": {"verdict": "unsupported", "confidence": 0.80},
            },
            "expected": "fail",
        },
        {
            "name": "Grounding weak but NLI entailed → flag",
            "claim": {
                "grounding": {"verdict": "ungrounded", "confidence": 0.3},
                "nli": {"verdict": "entailed", "confidence": 0.72},
            },
            "expected": "flag",  # or pass depending on weights
        },
        {
            "name": "Only grounding, no NLI/cross-LLM, grounded",
            "claim": {
                "grounding": {"verdict": "grounded", "confidence": 0.85},
            },
            "expected": "pass",
        },
        {
            "name": "Uncited claim, no other signals",
            "claim": {
                "grounding": {"verdict": "uncited", "confidence": 0.0},
            },
            "expected": "pass",  # passes through to evaluator
        },
    ]

    all_pass = True
    for tc in test_cases:
        result = aggregate_verdicts(tc["claim"])
        icon = {"pass": "✅", "fail": "❌", "flag": "🟡"}.get(result["final_verdict"], "?")
        match = result["final_verdict"] == tc["expected"]
        if not match:
            all_pass = False

        print(f"  {icon} {tc['name']}")
        print(f"     Verdict: {result['final_verdict']} (expected {tc['expected']}) "
              f"[{'PASS' if match else 'FAIL'}]")
        print(f"     Score: {result['final_confidence']:.2f}")
        print(f"     Signals: {result['signal_details']}")
        print(f"     Reason: {result['reasoning']}")
        print()

    print(f"{'=' * 50}")
    print(f"Result: {'ALL TESTS PASSED ✅' if all_pass else 'SOME TESTS FAILED ❌'}")
