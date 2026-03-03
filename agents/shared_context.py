"""
Shared Context Builder — Phase 1 of Parallel Pipeline
======================================================

Builds all read-only shared state ONCE before parallelizing questions:
  - PDF text extraction → page index
  - Pseudo-chunk creation  
  - Vector index building
  - Evidence retrieval for ALL questions
  - Question routing
  - Verifier initialization (NLI model, cross-LLM client)
  - Claim cache loading
  - PDF hash tracking (for cache invalidation)

Everything returned is IMMUTABLE during Phase 2.
Questions read from this shared context but never modify it.
"""

import os
import time
import hashlib
from pathlib import Path
from dataclasses import dataclass, field
from typing import Optional

import yaml


@dataclass
class SharedContext:
    """Immutable shared state built in Phase 1, consumed by Phase 2."""

    # Config
    pipeline_config: dict = field(default_factory=dict)
    eval_spec: dict = field(default_factory=dict)
    questions: dict = field(default_factory=dict)

    # Corpus data
    chunks: list = field(default_factory=list)
    page_index: dict = field(default_factory=dict)  # (filename, page) → text
    full_corpus_text: str = ""

    # Tier 1 (full-context) support
    tier: int = 2                  # 1 = full-context, 2 = RAG chunks
    full_text: str = ""            # Complete document text (Tier 1 only)

    # Chunks metadata for citation resolution: chunk_id → {pdf_file, page_start}
    chunks_metadata: dict = field(default_factory=dict)

    # Evidence per question (pre-retrieved)
    all_evidence: dict = field(default_factory=dict)  # qid → evidence dict

    # Routing decisions
    routing: dict = field(default_factory=dict)  # qid → route dict

    # Verifier handles (initialized once, shared across questions)
    nli_verifier: object = None
    nli_available: bool = False
    cross_llm_checker: object = None
    cross_llm_available: bool = False
    aggregate_verdicts_fn: object = None  # The aggregation function

    # Claim cache
    claim_cache: object = None

    # Failure ledger (self-healing)
    failure_ledger: object = None

    # Timing
    phase1_elapsed: float = 0.0

    # Failed claims from previous runs (for self-healing)
    historical_failures: list = field(default_factory=list)


def build_shared_context(
    pdf_dir: str = "docs/pdfs",
    config_path: str = "config/pipeline_config.yaml",
    eval_spec_path: str = "evaluation/evaluation_spec.yaml",
    console=None,
) -> SharedContext:
    """
    Phase 1: Build all shared state.

    This is the only sequential phase. Everything here runs once,
    then Phase 2 fires all questions in parallel reading from this context.

    Returns:
        SharedContext with all fields populated.
    """
    start = time.time()
    ctx = SharedContext()

    _log = lambda msg: console.print(msg) if console else print(msg)

    # ── Load configs ──
    _log("[bold cyan]Phase 1.1: Loading configuration[/bold cyan]" if console else "Phase 1.1: Loading configuration")
    with open(config_path) as f:
        ctx.pipeline_config = yaml.safe_load(f)
    with open(eval_spec_path) as f:
        ctx.eval_spec = yaml.safe_load(f)
    ctx.questions = {
        qid: q["text"] for qid, q in ctx.eval_spec["questions"].items()
    }

    # ── Ingest PDFs ──
    _log("[bold cyan]Phase 1.2: Ingesting PDFs[/bold cyan]" if console else "Phase 1.2: Ingesting PDFs")
    from agents.ingestion_agent import ingest_all_pdfs
    ctx.chunks = ingest_all_pdfs(pdf_dir, config_path)
    if not ctx.chunks:
        raise RuntimeError("No chunks produced from PDF ingestion")
    _log(f"  ✓ {len(ctx.chunks)} chunks created")

    # Capture tier + full_text if available (Tier 1 = full-context mode)
    try:
        from agents.ingestion_agent import get_ingestion_result
        ingestion_result = get_ingestion_result()
        if ingestion_result:
            ctx.tier = ingestion_result.get("tier", 2)
            ctx.full_text = ingestion_result.get("full_text", "") or ""
            if ctx.tier == 1 and ctx.full_text:
                _log(f"  ✓ Tier 1 (full-context): {len(ctx.full_text):,} chars available")
            else:
                _log(f"  ✓ Tier 2 (RAG chunks)")
    except (ImportError, AttributeError):
        _log("  ✓ Tier 2 (RAG chunks — get_ingestion_result not available)")

    # ── Build page index ──
    _log("[bold cyan]Phase 1.3: Building page index[/bold cyan]" if console else "Phase 1.3: Building page index")
    for chunk in ctx.chunks:
        key = (chunk["pdf_file"], chunk.get("page_start", 0))
        if key not in ctx.page_index:
            ctx.page_index[key] = chunk["text"]
        else:
            ctx.page_index[key] += "\n" + chunk["text"]
    ctx.full_corpus_text = "\n\n".join(c["text"] for c in ctx.chunks)
    _log(f"  ✓ {len(ctx.page_index)} pages indexed")

    # Build chunks_metadata for citation resolution
    for chunk in ctx.chunks:
        ctx.chunks_metadata[chunk.get("chunk_id", "")] = {
            "pdf_file": chunk.get("pdf_file", ""),
            "page_start": chunk.get("page_start", 0),
        }

    # ── Track PDF hashes for cache invalidation ──
    _log("[bold cyan]Phase 1.4: Loading claim cache[/bold cyan]" if console else "Phase 1.4: Loading claim cache")
    try:
        from agents.claim_cache import get_claim_cache
    except ImportError:
        from agents.claim_cache import get_claim_cache
    ctx.claim_cache = get_claim_cache()

    pdf_files = list(Path(pdf_dir).glob("*.pdf"))
    for pdf_path in pdf_files:
        # If an _EDITED.md exists, hash that instead of the PDF
        # This ensures the cache is invalidated when edits change
        edited_name = pdf_path.name.replace('.pdf', '_EDITED.md').replace(' ', '_')
        edited_path = Path("knowledge/edited_markdown") / edited_name
        if edited_path.exists():
            ctx.claim_cache.set_pdf_hash(pdf_path.name, str(edited_path))
        else:
            ctx.claim_cache.set_pdf_hash(pdf_path.name, str(pdf_path))
    _log(f"  ✓ Cache loaded: {ctx.claim_cache.stats['total_cached']} cached verdicts")

    # ── Load historical failures (for self-healing) ──
    _log("[bold cyan]Phase 1.5: Loading historical failures[/bold cyan]" if console else "Phase 1.5: Loading historical failures")
    ctx.historical_failures = _load_historical_failures()
    _log(f"  ✓ {len(ctx.historical_failures)} known failure patterns loaded")

    # Initialize failure ledger (self-healing guardrails)
    ctx.failure_ledger = _load_failure_ledger()
    if ctx.failure_ledger:
        stats = ctx.failure_ledger.stats
        _log(f"  ✓ Failure ledger loaded: {stats['total_failures_tracked']} failures tracked across {stats['total_runs']} runs")
    else:
        _log(f"  ⚠ Failure ledger not available")

    # ── Retrieve evidence for all questions ──
    _log("[bold cyan]Phase 1.6: Retrieving evidence[/bold cyan]" if console else "Phase 1.6: Retrieving evidence")

    if ctx.tier == 1:
        # Tier 1: All chunks are evidence (answer agent uses full_text)
        _log("  Tier 1: All page-chunks included as evidence (no retrieval needed)")
        for qid, qtext in ctx.questions.items():
            ctx.all_evidence[qid] = {
                "question_id": qid,
                "evidence": ctx.chunks,
                "stats": {
                    "returned": len(ctx.chunks),
                    "avg_relevance": 1.0,
                },
                "coverage_notes": ["Tier 1: All document pages included as evidence"],
            }
            _log(f"  ✓ {qid}: {len(ctx.chunks)} page-chunks (full corpus)")
    else:
        # Tier 2: Vector retrieval
        from agents.retriever_agent import retrieve_evidence
        for qid, qtext in ctx.questions.items():
            evidence = retrieve_evidence(qid, qtext, config_path)
            ctx.all_evidence[qid] = evidence
            _log(f"  ✓ {qid}: {evidence['stats']['returned']} chunks (avg relevance: {evidence['stats']['avg_relevance']})")

    # ── Route questions ──
    _log("[bold cyan]Phase 1.7: Routing questions[/bold cyan]" if console else "Phase 1.7: Routing questions")
    from agents.router_agent import route_question
    for qid, qtext in ctx.questions.items():
        question_spec = ctx.eval_spec["questions"].get(qid, {})
        evidence_summary = ""
        if qid in ctx.all_evidence:
            for chunk in ctx.all_evidence[qid]["evidence"][:5]:
                evidence_summary += f"[{chunk['chunk_id']}]: {chunk['text'][:150]}...\n"
        result = route_question(qid, qtext, question_spec, evidence_summary)
        ctx.routing[qid] = result
        _log(f"  ✓ {qid} → Loop {result['loop']}: {result['reason']}")

    # ── Initialize verifiers (shared across all questions) ──
    _log("[bold cyan]Phase 1.8: Initializing verifiers[/bold cyan]" if console else "Phase 1.8: Initializing verifiers")

    # NLI
    try:
        from agents.nli_verifier import get_nli_verifier
        ctx.nli_verifier = get_nli_verifier()
        ctx.nli_available = True
        _log("  ✓ NLI verifier: loaded")
    except ImportError:
        try:
            from agents.nli_verifier import get_nli_verifier
            ctx.nli_verifier = get_nli_verifier()
            ctx.nli_available = True
            _log("  ✓ NLI verifier: loaded")
        except ImportError:
            _log("  ⚠ NLI verifier: not available")

    # Cross-LLM
    try:
        from agents.cross_llm_checker import get_cross_llm_checker, aggregate_verdicts
        ctx.cross_llm_checker = get_cross_llm_checker()
        ctx.cross_llm_available = ctx.cross_llm_checker.available
        ctx.aggregate_verdicts_fn = aggregate_verdicts
        _log(f"  ✓ Cross-LLM checker: {'loaded' if ctx.cross_llm_available else 'not available'}")
    except ImportError:
        try:
            from agents.cross_llm_checker import get_cross_llm_checker, aggregate_verdicts
            ctx.cross_llm_checker = get_cross_llm_checker()
            ctx.cross_llm_available = ctx.cross_llm_checker.available
            ctx.aggregate_verdicts_fn = aggregate_verdicts
            _log(f"  ✓ Cross-LLM checker: {'loaded' if ctx.cross_llm_available else 'not available'}")
        except ImportError:
            _log("  ⚠ Cross-LLM checker: not available")

    ctx.phase1_elapsed = time.time() - start
    _log(f"\n[green]Phase 1 complete in {ctx.phase1_elapsed:.1f}s[/green]" if console
         else f"\nPhase 1 complete in {ctx.phase1_elapsed:.1f}s")

    return ctx


def _load_historical_failures() -> list[str]:
    """
    Load claim texts that failed verification in previous runs.
    Used by the self-healing answer generator to avoid regenerating known-bad claims.
    
    DEPRECATED: Now handled by FailureLedger with per-question guardrails.
    This function is kept for backward compatibility but returns an empty list.
    """
    return []


def _load_failure_ledger():
    """Load the persistent failure ledger."""
    try:
        from agents.failure_ledger import get_failure_ledger
        return get_failure_ledger()
    except ImportError:
        try:
            from failure_ledger import get_failure_ledger
            return get_failure_ledger()
        except ImportError:
            return None
