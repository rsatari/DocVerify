"""
Knowledge Store — Persistent Memory for the DDC Evaluator Pipeline
===================================================================

A JSON-backed store that accumulates intelligence across pipeline runs.
Every run reads from the store at startup and writes back at the end,
so the pipeline gets smarter over time.

What it tracks:
  1. Entity Registry — DDC-specific terms, aliases, relationships, chunk refs
  2. Retrieval Feedback — which query variants / chunks led to good answers
  3. Evaluation History — score trends per question, persistent gaps
  4. Research Cache — external findings so we don't re-search identical claims
  5. Document Registry — what each PDF covers, section maps, staleness tracking
  6. Terminology Map — user-facing terms ↔ protocol entities (addresses gap #7)

Design:
  - Single JSON file (knowledge/knowledge_store.json) for simplicity
  - Atomic writes (write to .tmp, then rename) to avoid corruption
  - Each sub-store is a dict keyed by stable IDs
  - Timestamps on everything for staleness detection
  - All methods are pure Python, no external deps beyond stdlib + yaml
"""

import json
import os
import hashlib
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional


DEFAULT_STORE_PATH = "knowledge/knowledge_store.json"


class KnowledgeStore:
    """
    Persistent, cross-run knowledge accumulator for the DDC evaluator pipeline.

    Usage:
        store = KnowledgeStore.load()
        # ... pipeline runs, agents read/write to store ...
        store.save()
    """

    def __init__(self, path: str = DEFAULT_STORE_PATH):
        self.path = path
        self.data = {
            "meta": {
                "created_at": datetime.now().isoformat(),
                "last_updated": datetime.now().isoformat(),
                "total_runs": 0,
                "schema_version": 1,
            },
            "entity_registry": {},
            "retrieval_feedback": {},
            "evaluation_history": [],
            "research_cache": {},
            "document_registry": {},
            "terminology_map": {},
            "gap_tracker": {},
        }

    # ------------------------------------------------------------------
    # Persistence
    # ------------------------------------------------------------------

    @classmethod
    def load(cls, path: str = DEFAULT_STORE_PATH) -> "KnowledgeStore":
        """Load from disk, or create a fresh store if none exists."""
        store = cls(path)
        if os.path.exists(path):
            try:
                with open(path, "r") as f:
                    stored = json.load(f)
                # Merge with defaults so new fields are always present
                for key in store.data:
                    if key in stored:
                        store.data[key] = stored[key]
                print(f"  [KnowledgeStore] Loaded from {path} "
                      f"(run #{store.data['meta']['total_runs']}, "
                      f"{len(store.data['entity_registry'])} entities, "
                      f"{len(store.data['research_cache'])} cached research results)")
            except (json.JSONDecodeError, KeyError) as e:
                print(f"  [KnowledgeStore] WARNING: Corrupt store at {path}, starting fresh: {e}")
        else:
            print(f"  [KnowledgeStore] No existing store found, creating fresh at {path}")
        return store

    def save(self):
        """Atomic save: write to .tmp, then rename."""
        self.data["meta"]["last_updated"] = datetime.now().isoformat()
        os.makedirs(os.path.dirname(self.path) or ".", exist_ok=True)
        tmp_path = self.path + ".tmp"
        with open(tmp_path, "w") as f:
            json.dump(self.data, f, indent=2, default=str)
        os.replace(tmp_path, self.path)

    def increment_run(self):
        """Call at the start of each pipeline run."""
        self.data["meta"]["total_runs"] += 1

    # ------------------------------------------------------------------
    # 1. Entity Registry
    # ------------------------------------------------------------------

    def register_entities(self, chunk_id: str, entities: list[str],
                          pdf_file: str, content_type: str = "prose"):
        """
        Register entities found in a chunk. Accumulates across runs.
        Builds an inverted index: entity → [chunk_ids where it appears].
        """
        registry = self.data["entity_registry"]
        for entity in entities:
            key = entity.lower().strip()
            if key not in registry:
                registry[key] = {
                    "canonical_name": entity,
                    "aliases": set(),
                    "chunk_refs": [],
                    "document_refs": set(),
                    "first_seen": datetime.now().isoformat(),
                    "last_seen": datetime.now().isoformat(),
                    "occurrence_count": 0,
                    "content_types_seen": set(),
                    "related_entities": set(),
                }
            entry = registry[key]
            # Update: use sets-as-lists for JSON serialization
            entry["last_seen"] = datetime.now().isoformat()
            entry["occurrence_count"] += 1

            if chunk_id not in entry["chunk_refs"]:
                entry["chunk_refs"].append(chunk_id)
            if isinstance(entry["document_refs"], list):
                entry["document_refs"] = set(entry["document_refs"])
            entry["document_refs"].add(pdf_file)
            if isinstance(entry["content_types_seen"], list):
                entry["content_types_seen"] = set(entry["content_types_seen"])
            entry["content_types_seen"].add(content_type)

            # Track co-occurring entities (same chunk = likely related)
            if isinstance(entry["related_entities"], list):
                entry["related_entities"] = set(entry["related_entities"])
            for other in entities:
                if other.lower().strip() != key:
                    entry["related_entities"].add(other.lower().strip())

    def add_entity_alias(self, canonical: str, alias: str):
        """Map a user-facing term to a protocol entity."""
        key = canonical.lower().strip()
        if key in self.data["entity_registry"]:
            entry = self.data["entity_registry"][key]
            if isinstance(entry["aliases"], list):
                entry["aliases"] = set(entry["aliases"])
            entry["aliases"].add(alias.lower().strip())

    def get_entity_chunks(self, entity: str) -> list[str]:
        """Get all chunk IDs where an entity appears."""
        key = entity.lower().strip()
        entry = self.data["entity_registry"].get(key, {})
        return entry.get("chunk_refs", [])

    def get_related_entities(self, entity: str) -> list[str]:
        """Get entities that co-occur with the given entity."""
        key = entity.lower().strip()
        entry = self.data["entity_registry"].get(key, {})
        related = entry.get("related_entities", [])
        return list(related) if isinstance(related, (set, list)) else []

    def get_top_entities(self, n: int = 30) -> list[dict]:
        """Get the most frequently occurring entities."""
        registry = self.data["entity_registry"]
        sorted_entities = sorted(
            registry.items(),
            key=lambda x: x[1].get("occurrence_count", 0),
            reverse=True
        )
        return [{"entity": k, **v} for k, v in sorted_entities[:n]]

    # ------------------------------------------------------------------
    # 2. Retrieval Feedback
    # ------------------------------------------------------------------

    def record_retrieval_outcome(self, question_id: str, query_variant: str,
                                  chunk_id: str, was_cited: bool,
                                  relevance_score: float):
        """
        Record whether a retrieved chunk was actually useful (cited in answer).
        Over time, this tells us which query variants produce good results.
        """
        feedback = self.data["retrieval_feedback"]

        # Key by query variant
        variant_key = hashlib.md5(query_variant.encode()).hexdigest()[:12]
        if variant_key not in feedback:
            feedback[variant_key] = {
                "query_text": query_variant,
                "total_retrievals": 0,
                "cited_count": 0,
                "uncited_count": 0,
                "avg_relevance": 0.0,
                "question_ids": [],
                "best_chunks": [],      # chunks that got cited
                "wasted_chunks": [],    # chunks retrieved but never cited
            }

        entry = feedback[variant_key]
        entry["total_retrievals"] += 1
        if question_id not in entry["question_ids"]:
            entry["question_ids"].append(question_id)

        if was_cited:
            entry["cited_count"] += 1
            if chunk_id not in entry["best_chunks"]:
                entry["best_chunks"].append(chunk_id)
        else:
            entry["uncited_count"] += 1
            if chunk_id not in entry["wasted_chunks"]:
                entry["wasted_chunks"].append(chunk_id)

        # Running average
        n = entry["total_retrievals"]
        entry["avg_relevance"] = (
            (entry["avg_relevance"] * (n - 1) + relevance_score) / n
        )

    def get_effective_query_variants(self, min_citation_rate: float = 0.3) -> list[dict]:
        """Get query variants that have a good citation rate."""
        feedback = self.data["retrieval_feedback"]
        effective = []
        for variant_key, entry in feedback.items():
            if entry["total_retrievals"] > 0:
                citation_rate = entry["cited_count"] / entry["total_retrievals"]
                if citation_rate >= min_citation_rate:
                    effective.append({
                        "query": entry["query_text"],
                        "citation_rate": citation_rate,
                        "total": entry["total_retrievals"],
                        **entry
                    })
        return sorted(effective, key=lambda x: x["citation_rate"], reverse=True)

    def get_wasted_query_variants(self, max_citation_rate: float = 0.1) -> list[dict]:
        """Get query variants that rarely produce useful results."""
        feedback = self.data["retrieval_feedback"]
        wasted = []
        for variant_key, entry in feedback.items():
            if entry["total_retrievals"] >= 3:  # need enough data
                citation_rate = entry["cited_count"] / entry["total_retrievals"]
                if citation_rate <= max_citation_rate:
                    wasted.append({
                        "query": entry["query_text"],
                        "citation_rate": citation_rate,
                        **entry
                    })
        return sorted(wasted, key=lambda x: x["citation_rate"])

    # ------------------------------------------------------------------
    # 3. Evaluation History
    # ------------------------------------------------------------------

    def record_evaluation(self, timestamp: str, question_id: str,
                          scores: dict, passed: bool, loop: str,
                          missing_concepts: list[str] = None,
                          failures: list[str] = None):
        """Record a single question's evaluation result."""
        self.data["evaluation_history"].append({
            "timestamp": timestamp,
            "question_id": question_id,
            "scores": scores,
            "passed": passed,
            "loop": loop,
            "missing_concepts": missing_concepts or [],
            "failures": failures or [],
            "run_number": self.data["meta"]["total_runs"],
        })

    def get_score_trend(self, question_id: str, last_n: int = 10) -> list[dict]:
        """Get the last N evaluation scores for a question."""
        history = self.data["evaluation_history"]
        q_history = [h for h in history if h["question_id"] == question_id]
        return q_history[-last_n:]

    def get_persistent_gaps(self, min_occurrences: int = 2) -> list[dict]:
        """
        Find concepts/failures that keep appearing across multiple runs.
        These are the real documentation gaps vs. one-off retrieval misses.
        """
        gap_counts = {}
        for entry in self.data["evaluation_history"]:
            for concept in entry.get("missing_concepts", []):
                key = concept.lower().strip()
                if key not in gap_counts:
                    gap_counts[key] = {
                        "concept": concept,
                        "occurrences": 0,
                        "question_ids": set(),
                        "first_seen": entry["timestamp"],
                        "last_seen": entry["timestamp"],
                    }
                gap_counts[key]["occurrences"] += 1
                gap_counts[key]["question_ids"].add(entry["question_id"])
                gap_counts[key]["last_seen"] = entry["timestamp"]

        persistent = [
            {**v, "question_ids": list(v["question_ids"])}
            for v in gap_counts.values()
            if v["occurrences"] >= min_occurrences
        ]
        return sorted(persistent, key=lambda x: x["occurrences"], reverse=True)

    # ------------------------------------------------------------------
    # 4. Research Cache
    # ------------------------------------------------------------------

    def cache_research(self, claim_text: str, platform: str,
                       results: dict, ttl_days: int = 30):
        """
        Cache external research results for a claim + platform pair.
        Avoids redundant web searches across runs.
        """
        cache_key = hashlib.md5(
            f"{claim_text.lower().strip()}::{platform.lower()}".encode()
        ).hexdigest()

        self.data["research_cache"][cache_key] = {
            "claim_text": claim_text,
            "platform": platform,
            "results": results,
            "cached_at": datetime.now().isoformat(),
            "expires_at": (datetime.now() + timedelta(days=ttl_days)).isoformat(),
            "hit_count": 0,
        }

    def get_cached_research(self, claim_text: str, platform: str) -> Optional[dict]:
        """
        Retrieve cached research if it exists and hasn't expired.
        Returns None if cache miss or expired.
        """
        cache_key = hashlib.md5(
            f"{claim_text.lower().strip()}::{platform.lower()}".encode()
        ).hexdigest()

        entry = self.data["research_cache"].get(cache_key)
        if not entry:
            return None

        # Check expiry
        expires = datetime.fromisoformat(entry["expires_at"])
        if datetime.now() > expires:
            del self.data["research_cache"][cache_key]
            return None

        entry["hit_count"] += 1
        return entry["results"]

    def get_cache_stats(self) -> dict:
        """Get research cache statistics."""
        cache = self.data["research_cache"]
        now = datetime.now()
        active = sum(1 for e in cache.values()
                     if datetime.fromisoformat(e["expires_at"]) > now)
        total_hits = sum(e.get("hit_count", 0) for e in cache.values())
        platforms = {}
        for e in cache.values():
            p = e.get("platform", "unknown")
            platforms[p] = platforms.get(p, 0) + 1

        return {
            "total_entries": len(cache),
            "active_entries": active,
            "expired_entries": len(cache) - active,
            "total_hits": total_hits,
            "platforms": platforms,
        }

    # ------------------------------------------------------------------
    # 5. Document Registry
    # ------------------------------------------------------------------

    def register_document(self, pdf_file: str, page_count: int,
                          extraction_method: str, chunk_count: int,
                          sections: list[str] = None,
                          file_hash: str = None):
        """
        Register a document and its metadata. Tracks changes across runs
        by comparing file hashes.
        """
        registry = self.data["document_registry"]
        existing = registry.get(pdf_file)

        is_updated = False
        if existing and file_hash and existing.get("file_hash") != file_hash:
            is_updated = True

        registry[pdf_file] = {
            "pdf_file": pdf_file,
            "page_count": page_count,
            "chunk_count": chunk_count,
            "extraction_method": extraction_method,
            "sections": sections or [],
            "file_hash": file_hash,
            "first_ingested": existing["first_ingested"] if existing else datetime.now().isoformat(),
            "last_ingested": datetime.now().isoformat(),
            "ingestion_count": (existing.get("ingestion_count", 0) + 1) if existing else 1,
            "was_updated": is_updated,
            "previous_hash": existing.get("file_hash") if is_updated else None,
        }

        if is_updated:
            print(f"  [KnowledgeStore] Document UPDATED: {pdf_file} (hash changed)")

        return is_updated

    def get_document_changes(self) -> list[dict]:
        """Get documents that changed since last run."""
        return [
            doc for doc in self.data["document_registry"].values()
            if doc.get("was_updated")
        ]

    # ------------------------------------------------------------------
    # 6. Terminology Map
    # ------------------------------------------------------------------

    def add_terminology_mapping(self, user_term: str, protocol_entity: str,
                                 source: str = "auto"):
        """
        Map a user-facing term to a DDC protocol entity.
        Example: "data wallet" → "ownerAccountId"
                 "my key"      → "ownerPubKey / DEK"
        """
        term_map = self.data["terminology_map"]
        key = user_term.lower().strip()
        if key not in term_map:
            term_map[key] = {
                "user_term": user_term,
                "protocol_entities": [],
                "source": source,
                "added_at": datetime.now().isoformat(),
            }
        if protocol_entity not in term_map[key]["protocol_entities"]:
            term_map[key]["protocol_entities"].append(protocol_entity)

    def resolve_term(self, user_term: str) -> list[str]:
        """Resolve a user-facing term to protocol entities."""
        key = user_term.lower().strip()
        entry = self.data["terminology_map"].get(key, {})
        return entry.get("protocol_entities", [])

    def get_all_mappings(self) -> dict:
        """Get the full terminology map."""
        return self.data["terminology_map"]

    # ------------------------------------------------------------------
    # 7. Gap Tracker
    # ------------------------------------------------------------------

    def track_gap(self, gap_id: str, description: str, question_id: str,
                  priority: str = "P1", status: str = "open"):
        """
        Track a documentation gap across runs. Gaps can be:
        - "open": identified but not addressed
        - "addressed": doc was updated to cover it
        - "verified": pipeline confirmed the gap is resolved (score improved)
        """
        tracker = self.data["gap_tracker"]
        if gap_id not in tracker:
            tracker[gap_id] = {
                "gap_id": gap_id,
                "description": description,
                "question_ids": [question_id],
                "priority": priority,
                "status": status,
                "first_identified": datetime.now().isoformat(),
                "last_seen": datetime.now().isoformat(),
                "run_count": 1,
                "status_history": [{
                    "status": status,
                    "timestamp": datetime.now().isoformat(),
                    "run_number": self.data["meta"]["total_runs"],
                }],
            }
        else:
            entry = tracker[gap_id]
            entry["last_seen"] = datetime.now().isoformat()
            entry["run_count"] += 1
            if question_id not in entry["question_ids"]:
                entry["question_ids"].append(question_id)
            # Update status if changed
            if entry["status"] != status:
                entry["status"] = status
                entry["status_history"].append({
                    "status": status,
                    "timestamp": datetime.now().isoformat(),
                    "run_number": self.data["meta"]["total_runs"],
                })

    def get_open_gaps(self) -> list[dict]:
        """Get all unresolved gaps, sorted by priority then run count."""
        tracker = self.data["gap_tracker"]
        open_gaps = [g for g in tracker.values() if g["status"] == "open"]
        priority_order = {"P0": 0, "P1": 1, "P2": 2, "P3": 3}
        return sorted(
            open_gaps,
            key=lambda g: (priority_order.get(g["priority"], 99), -g["run_count"])
        )

    def resolve_gap(self, gap_id: str, status: str = "addressed"):
        """Mark a gap as addressed or verified."""
        self.track_gap(gap_id, "", "", status=status)

    # ------------------------------------------------------------------
    # Serialization helpers (sets → lists for JSON)
    # ------------------------------------------------------------------

    def save(self):
        """Atomic save with set→list conversion for JSON compatibility."""
        self.data["meta"]["last_updated"] = datetime.now().isoformat()

        # Convert sets to lists throughout entity_registry
        for key, entry in self.data["entity_registry"].items():
            for field in ["aliases", "document_refs", "content_types_seen", "related_entities"]:
                if isinstance(entry.get(field), set):
                    entry[field] = sorted(list(entry[field]))

        # Convert sets in gap_tracker question_ids
        for key, entry in self.data["gap_tracker"].items():
            for field in ["question_ids"]:
                if isinstance(entry.get(field), set):
                    entry[field] = sorted(list(entry[field]))

        # Convert sets in evaluation_history
        for entry in self.data["evaluation_history"]:
            for field in entry:
                if isinstance(entry[field], set):
                    entry[field] = sorted(list(entry[field]))

        os.makedirs(os.path.dirname(self.path) or ".", exist_ok=True)
        tmp_path = self.path + ".tmp"
        with open(tmp_path, "w") as f:
            json.dump(self.data, f, indent=2, default=str)
        os.replace(tmp_path, self.path)
        print(f"  [KnowledgeStore] Saved to {self.path}")

    # ------------------------------------------------------------------
    # Summary / diagnostics
    # ------------------------------------------------------------------

    def summary(self) -> dict:
        """Get a diagnostic summary of the knowledge store."""
        meta = self.data["meta"]
        return {
            "total_runs": meta["total_runs"],
            "last_updated": meta["last_updated"],
            "entities": len(self.data["entity_registry"]),
            "retrieval_feedback_entries": len(self.data["retrieval_feedback"]),
            "evaluation_records": len(self.data["evaluation_history"]),
            "research_cache": self.get_cache_stats(),
            "documents": len(self.data["document_registry"]),
            "terminology_mappings": len(self.data["terminology_map"]),
            "open_gaps": len(self.get_open_gaps()),
            "persistent_gaps": len(self.get_persistent_gaps()),
        }


# ---------------------------------------------------------------------------
# Convenience: auto-populate terminology map with known DDC mappings
# ---------------------------------------------------------------------------

DEFAULT_TERMINOLOGY = {
    "data wallet": ["ownerAccountId", "ownerPubKey", "Ed25519 keypair"],
    "my key": ["ownerPubKey", "DEK (Data Encryption Key)", "Ed25519 signing key"],
    "encryption key": ["DEK", "HKDF-SHA256 derived key", "X25519 encryption key"],
    "access control": ["PolicyGrant", "EncryptionGrant", "AuthToken", "pallet ACL"],
    "sharing data": ["delegateAccess", "token delegation", "EncryptionGrant"],
    "storing data": ["createBucket", "upload", "DdcClient.buildAndConnect"],
    "node": ["storage node", "CDN node", "DDC node provider"],
    "cluster": ["DDC cluster", "on-chain cluster pallet", "Dragon 1"],
    "replication": ["erasure coding", "K/N scheme", "data redundancy"],
    "security": ["client-side encryption", "PolicyGrant", "DEK", "X25519"],
}


def initialize_default_terminology(store: KnowledgeStore):
    """Seed the terminology map with known DDC term mappings."""
    for user_term, protocol_entities in DEFAULT_TERMINOLOGY.items():
        for entity in protocol_entities:
            store.add_terminology_mapping(user_term, entity, source="default_seed")


if __name__ == "__main__":
    # Quick test
    store = KnowledgeStore.load()
    store.increment_run()

    # Seed terminology
    initialize_default_terminology(store)

    # Register some test entities
    store.register_entities("p1-0001", ["DEK", "HKDF-SHA256", "PolicyGrant"],
                            "Encrypted_Data_Access.pdf", "protobuf_spec")
    store.register_entities("p3-0058", ["erasure coding", "DHT", "Kademlia"],
                            "DDC_from_Sergey_Poluyan.pdf", "prose")

    # Record evaluation
    store.record_evaluation(
        timestamp=datetime.now().isoformat(),
        question_id="Q3",
        scores={"grounded_correctness": 0.85, "completeness": 0.60},
        passed=False,
        loop="A",
        missing_concepts=["Authentication mechanism", "Key loss scenario"],
    )

    # Track a gap
    store.track_gap("GAP-001", "Key loss scenario not documented", "Q3", "P0")

    # Cache some research
    store.cache_research(
        "Databricks uses customer-managed keys via AWS KMS",
        "databricks",
        {"verdict": "confirmed", "source": "docs.databricks.com"},
        ttl_days=30,
    )

    store.save()

    # Print summary
    print(json.dumps(store.summary(), indent=2))
