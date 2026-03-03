"""
Failure Ledger — Self-Healing Loop
====================================

Accumulates verified claim failures across pipeline runs and generates
per-question guardrails that the answerer reads before generating.

How it works:
1. After each run, record_failures() saves failed claims per question
2. Before each answer, get_guardrails(qid) returns deduped failure patterns
3. The answerer sees these as "DO NOT make these claims" instructions
4. Failures that stop recurring decay after DECAY_RUNS runs

Storage: knowledge/failure_ledger.json
"""

import os
import json
import hashlib
import time
from pathlib import Path
from typing import Optional
from collections import defaultdict


LEDGER_FILE = "knowledge/failure_ledger.json"
MAX_GUARDRAILS_PER_QUESTION = 15   # Don't overwhelm the prompt
DECAY_RUNS = 5                      # Remove after N runs without recurrence
MIN_OCCURRENCES_FOR_RULE = 2        # Only promote to guardrail after 2+ failures


def _normalize_claim(text: str) -> str:
    """Normalize a claim for deduplication."""
    t = text.strip().lower()
    # Remove citation markers
    import re
    t = re.sub(r'\[\[.*?\]\]', '', t)
    t = re.sub(r'\s+', ' ', t).strip()
    return t[:200]


def _claim_hash(text: str) -> str:
    """Short hash for deduplication."""
    return hashlib.sha256(_normalize_claim(text).encode()).hexdigest()[:16]


def _extract_pattern(claim_text: str, detail: str) -> Optional[str]:
    """
    Extract a generalizable pattern from a specific failure.
    Returns a human-readable guardrail rule.
    """
    text = claim_text.strip()
    detail = (detail or "").strip()

    # Pattern: wrong page citation
    if "does not appear on the cited page" in detail or "None of the" in detail:
        # Extract what was claimed and where
        return f"DO NOT cite this claim without verifying the page number: \"{text[:120]}\""

    # Pattern: inference not in source
    inference_markers = [
        "no single point of failure",
        "eliminates", "ensures that no",
        "without any centralized",
        "fully autonomous",
        "completely independent",
    ]
    for marker in inference_markers:
        if marker in text.lower():
            return f"DO NOT infer \"{marker}\" — state only what the docs literally say. Failed claim: \"{text[:100]}\""

    # Pattern: wrong terminology
    if "term mismatch" in detail.lower() or "does not use" in detail.lower():
        return f"TERMINOLOGY: The docs do not use this phrasing. Failed claim: \"{text[:120]}\""

    # Default: specific claim avoidance
    return f"AVOID: \"{text[:150]}\" — this failed verification in a previous run."


class FailureLedger:
    """Persistent ledger of verification failures across runs."""

    def __init__(self, path: str = LEDGER_FILE):
        self._path = path
        self._data = {"failures": {}, "meta": {"total_runs": 0, "last_updated": ""}}
        self._load()

    def _load(self):
        try:
            if os.path.exists(self._path):
                with open(self._path) as f:
                    self._data = json.load(f)
        except (json.JSONDecodeError, IOError):
            self._data = {"failures": {}, "meta": {"total_runs": 0, "last_updated": ""}}

    def save(self):
        os.makedirs(os.path.dirname(self._path) or ".", exist_ok=True)
        self._data["meta"]["last_updated"] = time.strftime("%Y-%m-%dT%H:%M:%S")
        with open(self._path, "w") as f:
            json.dump(self._data, f, indent=2)

    def record_failures(self, question_id: str, failed_claims: list[dict],
                        run_number: int):
        """
        Record failed claims from a pipeline run.

        Args:
            question_id: e.g. "Q1"
            failed_claims: list of claim dicts with 'text', 'grounding' fields
            run_number: current run number for decay tracking
        """
        if question_id not in self._data["failures"]:
            self._data["failures"][question_id] = {}

        qfails = self._data["failures"][question_id]

        for claim in failed_claims:
            text = claim.get("text", "")
            if not text:
                continue

            h = _claim_hash(text)
            detail = claim.get("grounding", {}).get("detail", "")

            if h in qfails:
                # Recurring failure — increment count, update last seen
                qfails[h]["count"] += 1
                qfails[h]["last_run"] = run_number
                # Keep the best detail message
                if detail and len(detail) > len(qfails[h].get("detail", "")):
                    qfails[h]["detail"] = detail
            else:
                # New failure
                pattern = _extract_pattern(text, detail)
                qfails[h] = {
                    "claim_text": text[:200],
                    "detail": detail[:200],
                    "pattern": pattern,
                    "count": 1,
                    "first_run": run_number,
                    "last_run": run_number,
                }

        self._data["meta"]["total_runs"] = run_number
        self._prune_decayed(run_number)

    def _prune_decayed(self, current_run: int):
        """Remove failures that haven't recurred in DECAY_RUNS runs."""
        for qid in list(self._data["failures"].keys()):
            qfails = self._data["failures"][qid]
            to_remove = [
                h for h, entry in qfails.items()
                if (current_run - entry["last_run"]) >= DECAY_RUNS
            ]
            for h in to_remove:
                del qfails[h]

    def get_guardrails(self, question_id: str) -> list[str]:
        """
        Get guardrail instructions for the answerer, based on accumulated
        failure patterns for this question.

        Returns list of human-readable rules, sorted by recurrence count.
        """
        qfails = self._data["failures"].get(question_id, {})
        if not qfails:
            return []

        # Sort by count (most recurring first), then by recency
        entries = sorted(
            qfails.values(),
            key=lambda e: (e["count"], e["last_run"]),
            reverse=True,
        )

        guardrails = []
        for entry in entries:
            pattern = entry.get("pattern", "")
            if not pattern:
                pattern = f"AVOID: \"{entry['claim_text'][:150]}\" — failed {entry['count']}x"

            # Only include patterns that have occurred 2+ times OR are very recent
            if entry["count"] >= MIN_OCCURRENCES_FOR_RULE:
                guardrails.append(f"[{entry['count']}x] {pattern}")
            elif entry["last_run"] == self._data["meta"].get("total_runs", 0):
                # Include single-occurrence failures from the most recent run
                guardrails.append(f"[1x] {pattern}")

            if len(guardrails) >= MAX_GUARDRAILS_PER_QUESTION:
                break

        return guardrails

    def get_all_guardrails(self) -> dict[str, list[str]]:
        """Get guardrails for all questions."""
        return {
            qid: self.get_guardrails(qid)
            for qid in self._data["failures"]
        }

    @property
    def stats(self) -> dict:
        total = sum(
            len(v) for v in self._data["failures"].values()
        )
        by_q = {
            qid: len(entries)
            for qid, entries in self._data["failures"].items()
        }
        return {
            "total_failures_tracked": total,
            "by_question": by_q,
            "total_runs": self._data["meta"].get("total_runs", 0),
        }


# ── Singleton ──

_instance: Optional[FailureLedger] = None


def get_failure_ledger() -> FailureLedger:
    global _instance
    if _instance is None:
        _instance = FailureLedger()
    return _instance


# ── Test ──

if __name__ == "__main__":
    import tempfile
    print("=== Failure Ledger Test ===\n")

    ledger = FailureLedger(os.path.join(tempfile.gettempdir(), "test_ledger.json"))

    # Simulate run 1
    ledger.record_failures("Q1", [
        {"text": "DDC has no single point of failure", "grounding": {"detail": "inference"}},
        {"text": "16/48 scheme cited on wrong page", "grounding": {"detail": "None of the key terms found"}},
    ], run_number=1)

    # Simulate run 2 — same failures recur
    ledger.record_failures("Q1", [
        {"text": "DDC has no single point of failure", "grounding": {"detail": "inference"}},
        {"text": "Nodes operate fully autonomously", "grounding": {"detail": "inference"}},
    ], run_number=2)

    guardrails = ledger.get_guardrails("Q1")
    print(f"  Guardrails for Q1 ({len(guardrails)}):")
    for g in guardrails:
        print(f"    {g}")

    print(f"\n  Stats: {ledger.stats}")

    # Save and reload
    ledger.save()
    ledger2 = FailureLedger(ledger._path)
    assert len(ledger2.get_guardrails("Q1")) == len(guardrails)
    print(f"  ✓ Persistence works")

    os.remove(ledger._path)
    print(f"\n  ALL TESTS PASSED ✅")
