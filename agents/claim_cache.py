"""
Claim Cache — Pre-Computed Claim Bank
======================================

Persists verified claim→verdict mappings across pipeline runs.
If the same claim (text + citation) was verified before and the
source PDF hasn't changed, skip verification entirely.

Over time the pipeline gets faster as more claims are seen.

Storage: JSON file at knowledge/claim_cache.json
Key: SHA-256 of (claim_text + cited_file + cited_page + source_pdf_hash)

This means:
  - Same claim citing same page → cache hit (skip verification)
  - Same claim citing different page → cache miss (re-verify)
  - PDF changed (new hash) → all claims from that PDF invalidated
"""

import os
import json
import hashlib
import time
from pathlib import Path
from typing import Optional


CACHE_FILE = "knowledge/claim_cache.json"
MAX_CACHE_AGE_DAYS = 30  # Invalidate entries older than this


class ClaimCache:
    """Persistent cache of verified claim verdicts."""

    def __init__(self, cache_path: str = CACHE_FILE):
        self._path = cache_path
        self._cache: dict[str, dict] = {}
        self._pdf_hashes: dict[str, str] = {}
        self._hits = 0
        self._misses = 0
        self._load()

    def _load(self):
        """Load cache from disk."""
        try:
            if os.path.exists(self._path):
                with open(self._path) as f:
                    data = json.load(f)
                self._cache = data.get("claims", {})
                self._pdf_hashes = data.get("pdf_hashes", {})
                # Prune expired entries
                self._prune_expired()
        except (json.JSONDecodeError, IOError):
            self._cache = {}
            self._pdf_hashes = {}

    def save(self):
        """Persist cache to disk."""
        os.makedirs(os.path.dirname(self._path) or ".", exist_ok=True)
        data = {
            "claims": self._cache,
            "pdf_hashes": self._pdf_hashes,
            "last_saved": time.time(),
            "stats": {"total_entries": len(self._cache)},
        }
        with open(self._path, "w") as f:
            json.dump(data, f, indent=2)

    def _prune_expired(self):
        """Remove entries older than MAX_CACHE_AGE_DAYS."""
        cutoff = time.time() - (MAX_CACHE_AGE_DAYS * 86400)
        expired = [k for k, v in self._cache.items() if v.get("timestamp", 0) < cutoff]
        for k in expired:
            del self._cache[k]

    # ── PDF hash tracking ──

    def set_pdf_hash(self, pdf_filename: str, pdf_path: str):
        """Compute and store the hash of a PDF file."""
        h = self._hash_file(pdf_path)
        old_hash = self._pdf_hashes.get(pdf_filename)
        self._pdf_hashes[pdf_filename] = h
        if old_hash and old_hash != h:
            # PDF changed — invalidate all claims from this PDF
            self._invalidate_pdf(pdf_filename)

    def _hash_file(self, path: str) -> str:
        """SHA-256 of file contents."""
        h = hashlib.sha256()
        with open(path, "rb") as f:
            for chunk in iter(lambda: f.read(8192), b""):
                h.update(chunk)
        return h.hexdigest()[:16]

    def _invalidate_pdf(self, pdf_filename: str):
        """Remove all cached claims that reference this PDF."""
        to_delete = [
            k for k, v in self._cache.items()
            if v.get("cited_file") == pdf_filename
        ]
        for k in to_delete:
            del self._cache[k]

    # ── Claim lookup ──

    def _make_key(self, claim_text: str, cited_file: str, cited_page: int) -> str:
        """Create a deterministic cache key for a claim."""
        raw = f"{claim_text.strip().lower()}|{cited_file}|{cited_page}"
        return hashlib.sha256(raw.encode()).hexdigest()[:24]

    def lookup(self, claim_text: str, cited_file: str, cited_page: int) -> Optional[dict]:
        """
        Check if a claim has a cached verdict.

        Returns:
            Cached verdict dict if found and valid, None otherwise.
            Verdict dict has: {verdict, confidence, signals, reasoning, cached_at}
        """
        key = self._make_key(claim_text, cited_file, cited_page)
        entry = self._cache.get(key)
        if entry is None:
            self._misses += 1
            return None

        # Check if the PDF this claim references has changed
        current_hash = self._pdf_hashes.get(cited_file, "")
        if entry.get("pdf_hash") and entry["pdf_hash"] != current_hash:
            # PDF changed since this verdict was cached
            del self._cache[key]
            self._misses += 1
            return None

        self._hits += 1
        return entry.get("verdict")

    def store(self, claim_text: str, cited_file: str, cited_page: int,
              verdict: dict):
        """Store a verified claim verdict in the cache."""
        key = self._make_key(claim_text, cited_file, cited_page)
        self._cache[key] = {
            "claim_text": claim_text[:200],  # Truncate for storage
            "cited_file": cited_file,
            "cited_page": cited_page,
            "pdf_hash": self._pdf_hashes.get(cited_file, ""),
            "verdict": verdict,
            "timestamp": time.time(),
        }

    # ── Stats ──

    @property
    def stats(self) -> dict:
        return {
            "total_cached": len(self._cache),
            "hits": self._hits,
            "misses": self._misses,
            "hit_rate": (self._hits / max(1, self._hits + self._misses)),
            "pdfs_tracked": len(self._pdf_hashes),
        }

    def reset_stats(self):
        self._hits = 0
        self._misses = 0


# ── Singleton ──

_instance: Optional[ClaimCache] = None


def get_claim_cache() -> ClaimCache:
    """Get or create the singleton claim cache."""
    global _instance
    if _instance is None:
        _instance = ClaimCache()
    return _instance


# ── Test ──

if __name__ == "__main__":
    print("=== Claim Cache Test ===\n")

    cache = ClaimCache("/tmp/test_claim_cache.json")

    # Test store and lookup
    cache.store(
        "DDC uses 16/48 erasure coding",
        "Data_Redundancy_Strategy.pdf", 1,
        {"final_verdict": "pass", "final_confidence": 0.95}
    )

    result = cache.lookup(
        "DDC uses 16/48 erasure coding",
        "Data_Redundancy_Strategy.pdf", 1
    )
    assert result is not None
    assert result["final_verdict"] == "pass"
    print(f"  ✓ Store and lookup works")

    # Test cache miss
    result = cache.lookup("totally different claim", "other.pdf", 5)
    assert result is None
    print(f"  ✓ Cache miss works")

    # Test stats
    print(f"  Stats: {cache.stats}")

    # Test save/reload
    cache.save()
    cache2 = ClaimCache("/tmp/test_claim_cache.json")
    result = cache2.lookup(
        "DDC uses 16/48 erasure coding",
        "Data_Redundancy_Strategy.pdf", 1
    )
    assert result is not None
    print(f"  ✓ Save/reload persistence works")

    # Cleanup
    os.remove("/tmp/test_claim_cache.json")
    print(f"\n  ALL TESTS PASSED ✅")
