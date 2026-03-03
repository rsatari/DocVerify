#!/usr/bin/env python3
"""
DDC Documentation Evaluator — Two-Phase Parallel Pipeline
==========================================================

ARCHITECTURE:

  Phase 1 (Sequential, ~5s):
    Build shared read-only context: ingest PDFs, retrieve evidence,
    route questions, load verifiers, load claim cache.

  Phase 2 (Parallel, ~30-40s):
    Fire all questions simultaneously. Each question independently:
    → Generate answer (Claude Opus, self-healing)
    → Verify (grounding + NLI + cross-LLM, parallel)
    → Loop B research (if routed)
    → Evaluate (GPT-5.2 + RAGAS faithfulness, parallel)

  Phase 3 (Sequential, ~2s):
    Collect results, retry failures, generate report, save cache.

IMPROVEMENTS OVER V1:
  ✅ Two-phase parallel: 3 questions execute simultaneously
  ✅ Claim cache: Skip verification for previously-verified claims
  ✅ Self-healing answers: Generator avoids claims that failed before
  ✅ Parallel verification: NLI + cross-LLM run simultaneously
  ✅ Parallel evaluation: GPT-5.2 + RAGAS run simultaneously
  ✅ RAGAS faithfulness cross-check with score blending
  ✅ Speculative verification (claim-level parallelism)

Usage:
    python run_pipeline_v3.py
    python run_pipeline_v3.py --sequential  # Fall back to sequential mode
"""

import os
import sys
import json
import time
import argparse
from datetime import datetime
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from dotenv import load_dotenv

try:
    from rich.console import Console
    from rich.panel import Panel
    from rich.table import Table
    from rich.live import Live
    from rich import print as rprint
    RICH_AVAILABLE = True
except ImportError:
    RICH_AVAILABLE = False

import yaml

console = Console() if RICH_AVAILABLE else None


def check_prerequisites():
    """Verify everything is in place before running."""
    load_dotenv()
    errors = []
    warnings = []

    if not os.environ.get("ANTHROPIC_API_KEY"):
        errors.append("Missing ANTHROPIC_API_KEY in .env file")
    if not os.environ.get("OPENAI_API_KEY"):
        errors.append("Missing OPENAI_API_KEY in .env file")
    if not os.environ.get("TAVILY_API_KEY"):
        warnings.append("Missing TAVILY_API_KEY — Loop B will use OpenAI search only")
    if not os.environ.get("GOOGLE_API_KEY"):
        warnings.append("Missing GOOGLE_API_KEY — Cross-LLM checker will use GPT fallback")

    pdf_dir = Path("docs/pdfs")
    pdf_dir.mkdir(parents=True, exist_ok=True)
    pdf_files = list(pdf_dir.glob("*.pdf"))
    if not pdf_files:
        errors.append(f"No PDF files found in {pdf_dir}/")

    if not Path("config/pipeline_config.yaml").exists():
        errors.append("Missing config/pipeline_config.yaml")
    if not Path("evaluation/evaluation_spec.yaml").exists():
        errors.append("Missing evaluation/evaluation_spec.yaml")

    if errors:
        for e in errors:
            print(f"  ✗ {e}")
        print("\nSetup instructions:")
        print("  1. Copy PDFs into docs/pdfs/")
        print("  2. Copy .env.example to .env and add API keys")
        print("  3. Run again: python run_pipeline_v3.py")
        sys.exit(1)

    if RICH_AVAILABLE:
        status_lines = [
            f"[green]✓[/green] API keys configured",
            f"[green]✓[/green] {len(pdf_files)} PDF files found",
            f"[green]✓[/green] Config files present",
        ]
        for w in warnings:
            status_lines.append(f"[yellow]⚠[/yellow] {w}")
        console.print(Panel("\n".join(status_lines),
                           title="[green]Prerequisites OK[/green]",
                           border_style="green"))


def run_parallel(ctx) -> dict:
    """
    Phase 2: Run all questions in parallel.

    Returns dict of qid → QuestionResult
    """
    from agents.question_worker import process_question

    results = {}
    qids = list(ctx.questions.keys())

    if RICH_AVAILABLE:
        console.print(f"\n[bold cyan]═══ PHASE 2: PARALLEL EXECUTION ({len(qids)} questions) ═══[/bold cyan]")
    else:
        print(f"\n═══ PHASE 2: PARALLEL EXECUTION ({len(qids)} questions) ═══")

    with ThreadPoolExecutor(max_workers=len(qids)) as executor:
        futures = {
            executor.submit(process_question, qid, ctx, console): qid
            for qid in qids
        }

        for future in as_completed(futures):
            qid = futures[future]
            try:
                result = future.result(timeout=300)  # 5 min max per question
                results[qid] = result
            except Exception as e:
                print(f"  [{qid}] FAILED: {e}")
                from agents.question_worker import QuestionResult
                results[qid] = QuestionResult(
                    question_id=qid,
                    question_text=ctx.questions[qid],
                    error=str(e)
                )

    return results


def run_sequential(ctx) -> dict:
    """Fallback: Run questions sequentially (easier to debug)."""
    from agents.question_worker import process_question

    results = {}
    for qid in ctx.questions:
        if RICH_AVAILABLE:
            console.print(f"\n[bold cyan]═══ Processing {qid} ═══[/bold cyan]")
        result = process_question(qid, ctx, console)
        results[qid] = result

    return results


def phase3_finalize(ctx, results: dict, timestamp: str):
    """
    Phase 3: Collect results, retry failures, generate report, save cache.
    """
    if RICH_AVAILABLE:
        console.print(f"\n[bold cyan]═══ PHASE 3: FINALIZATION ═══[/bold cyan]")
    else:
        print("\n═══ PHASE 3: FINALIZATION ═══")

    # ── Retry failed questions in Loop B ──
    failed_qids = [
        qid for qid, r in results.items()
        if r.evaluation and not r.evaluation.get("passed", False) and r.loop == "A"
    ]

    # ── Generate improvement suggestions ──
    print("  Generating improvement suggestions...")
    from agents.editor_agent import propose_improvements

    all_chunks = []
    for qid, ev in ctx.all_evidence.items():
        all_chunks.extend(ev["evidence"])
    seen = set()
    unique_chunks = [c for c in all_chunks if c["chunk_id"] not in seen and not seen.add(c["chunk_id"])]

    all_evaluations_list = [r.evaluation for r in results.values() if r.evaluation]
    improvements = propose_improvements(all_evaluations_list, unique_chunks)
    print(f"  ✓ {len(improvements.get('proposed_changes', []))} improvements proposed")

    # ── Save claim cache ──
    if ctx.claim_cache:
        ctx.claim_cache.save()
        stats = ctx.claim_cache.stats
        print(f"  ✓ Claim cache saved: {stats['total_cached']} entries, "
              f"{stats['hit_rate']:.0%} hit rate")

    # ── Save failure ledger ──
    if ctx.failure_ledger:
        ctx.failure_ledger.save()
        stats = ctx.failure_ledger.stats
        print(f"  ✓ Failure ledger saved: {stats['total_failures_tracked']} failures "
              f"across {stats['by_question']}")

    # ── Save verification data for self-healing ──
    verification_data = {}
    for qid, r in results.items():
        if r.verification:
            verification_data[qid] = {
                "claims": [
                    {
                        "text": c.get("text", ""),
                        "final_verdict": c.get("final_verdict", "pass"),
                        "claim_id": c.get("claim_id", ""),
                    }
                    for c in r.verification.get("claims", [])
                ],
                "stats": r.verification.get("stats", {}),
            }

    # ── Save all reports ──
    save_reports(ctx, results, improvements, verification_data, timestamp)

    return improvements


def save_reports(ctx, results: dict, improvements: dict,
                 verification_data: dict, timestamp: str):
    """Save all results to the reports directory."""
    reports_dir = Path("reports")
    reports_dir.mkdir(exist_ok=True)

    # Collect structured data
    all_answers = {}
    all_evaluations = {}
    all_claims = {}
    all_research = {}
    all_correlations = {}
    all_gap_reports = {}

    for qid, r in results.items():
        all_answers[qid] = r.answer
        all_evaluations[qid] = r.evaluation
        if r.claims:
            all_claims[qid] = r.claims
        if r.research:
            all_research[qid] = r.research
        if r.correlation:
            all_correlations[qid] = r.correlation
        if r.gap_report:
            all_gap_reports[qid] = r.gap_report

    # Save JSON files
    _save_json(reports_dir / "latest_answers.json", all_answers)
    _save_json(reports_dir / "latest_scores.json", all_evaluations)
    _save_json(reports_dir / "latest_improvements.json", improvements)
    _save_json(reports_dir / "latest_routing.json", ctx.routing)
    _save_json(reports_dir / "latest_verification.json", verification_data)

    if all_claims:
        _save_json(reports_dir / "latest_claims.json", all_claims)
    if all_research:
        _save_json(reports_dir / "latest_research.json", all_research)
    if all_correlations:
        _save_json(reports_dir / "latest_correlations.json", all_correlations)
    if all_gap_reports:
        _save_json(reports_dir / "latest_gap_report.json", all_gap_reports)

    # Save evidence
    _save_json(reports_dir / "latest_evidence.json", ctx.all_evidence)

    # Save tier info
    _save_json(reports_dir / "latest_tier_info.json", {
        "tier": ctx.tier,
        "doc_count": len(set(c.get("pdf_file", "") for c in ctx.chunks)),
        "page_count": len(ctx.chunks),
    })

    # Generate markdown report
    report_md = generate_report(results, ctx, improvements, timestamp)
    with open(reports_dir / "latest_report.md", "w") as f:
        f.write(report_md)

    # Historical score tracking
    history_file = reports_dir / "historical_scores.json"
    history = []
    if history_file.exists():
        with open(history_file) as f:
            history = json.load(f)

    history.append({
        "timestamp": timestamp,
        "scores": {
            qid: {
                "overall": r.evaluation.get("overall_score", 0) if r.evaluation else 0,
                "passed": r.evaluation.get("passed", False) if r.evaluation else False,
                "loop": r.loop,
                "elapsed": r.elapsed,
                "cache_hits": r.verification.get("stats", {}).get("cache_hits", 0) if r.verification else 0,
            }
            for qid, r in results.items()
        }
    })
    _save_json(history_file, history)

    print(f"  ✓ Reports saved to {reports_dir}/")


def _save_json(path, data):
    with open(path, "w") as f:
        json.dump(data, f, indent=2, default=str)


def generate_report(results: dict, ctx, improvements: dict, timestamp: str) -> str:
    """Generate the human-readable Markdown report."""
    # Read evaluator model info from config
    try:
        import yaml as _yaml
        from pathlib import Path as _Path
        _cfg_path = _Path("config/pipeline_config.yaml")
        if _cfg_path.exists():
            with open(_cfg_path) as _f:
                _cfg = _yaml.safe_load(_f)
            _eval_model = _cfg.get("models", {}).get("evaluator", {}).get("model", "gpt-5.2")
            _eval_provider = _cfg.get("models", {}).get("evaluator", {}).get("provider", "openai")
        else:
            _eval_model, _eval_provider = "gpt-5.2", "openai"
    except Exception:
        _eval_model, _eval_provider = "gpt-5.2", "openai"

    lines = [
        f"# DDC Documentation Evaluation Report",
        f"**Generated:** {timestamp}",
        f"**Pipeline:** Two-Phase Parallel v3 (Tier {ctx.tier})",
        f"**Answerer:** Claude (Anthropic) | **Evaluator:** {_eval_model} ({_eval_provider}) | **RAGAS:** GPT-4o",
        f"**Verification:** Grounding + NLI (DeBERTa) + Cross-LLM (Gemini) + Claim Cache",
        "",
        "---",
        "",
        "## Summary",
        ""
    ]

    # Summary table
    lines.append("| Question | Loop | Overall | Correctness | RAGAS Faith. | Verdict | Time |")
    lines.append("|----------|------|---------|-------------|--------------|---------|------|")
    for qid, r in results.items():
        if r.evaluation:
            overall = r.evaluation.get("overall_score", 0)
            scores = r.evaluation.get("scores", {})
            passed = "✅ PASS" if r.evaluation.get("passed") else "❌ FAIL"
            ragas = r.evaluation.get("ragas_faithfulness")
            ragas_str = f"{ragas:.2f}" if ragas is not None else "N/A"
            lines.append(
                f"| {qid} | {r.loop} | {overall:.2f} | "
                f"{scores.get('grounded_correctness', 0):.2f} | {ragas_str} | "
                f"{passed} | {r.elapsed:.1f}s |"
            )

    # Performance
    lines.extend(["", "### Performance", ""])
    total_time = sum(r.elapsed for r in results.values())
    phase1_time = ctx.phase1_elapsed
    lines.append(f"- **Phase 1 (setup):** {phase1_time:.1f}s")
    lines.append(f"- **Phase 2 (parallel):** {max(r.elapsed for r in results.values()):.1f}s wall-clock")
    lines.append(f"- **Total question time:** {total_time:.1f}s (sum of all questions)")

    if ctx.claim_cache:
        stats = ctx.claim_cache.stats
        lines.append(f"- **Claim cache:** {stats['total_cached']} entries, "
                     f"{stats['hits']} hits, {stats['hit_rate']:.0%} hit rate")

    # Routing
    lines.extend(["", "### Routing Decisions", ""])
    for qid, route in ctx.routing.items():
        targets = ", ".join(route.get("comparison_targets", [])) or "—"
        lines.append(f"- **{qid}** → Loop {route['loop']}: {route['reason']}")
        if route["loop"] == "B":
            lines.append(f"  - Comparison targets: {targets}")

    # Verification stats
    lines.extend(["", "### Verification Summary", ""])
    for qid, r in results.items():
        if r.verification:
            stats = r.verification.get("stats", {})
            lines.append(
                f"- **{qid}:** {stats.get('total', 0)} claims → "
                f"✅ {stats.get('passed', 0)} pass, "
                f"❌ {stats.get('failed', 0)} fail, "
                f"🟡 {stats.get('flagged', 0)} flag "
                f"(cache: {stats.get('cache_hits', 0)} hits)"
            )

    lines.extend(["", "---", ""])

    # Detailed results per question
    for qid, r in results.items():
        lines.extend([
            f"## {qid}: Detailed Results (Loop {r.loop})",
            "",
            f"### Question",
            f"> {r.question_text}",
            "",
        ])

        # Comparison table for Loop B
        if r.loop == "B" and r.correlation:
            corr = r.correlation
            lines.extend(["### Comparison Table", ""])
            lines.append("| Aspect | DDC Position | External Position | Classification |")
            lines.append("|--------|-------------|-------------------|----------------|")
            for row in corr.get("comparison_table", []):
                lines.append(
                    f"| {row.get('aspect', '')} | "
                    f"{row.get('ddc_position', '')[:60]} | "
                    f"{row.get('external_position', '')[:60]} | "
                    f"{row.get('classification', '')} |"
                )
            lines.append("")

        # Answer
        label = "(Enriched)" if r.loop == "B" else "(Closed-Book)"
        lines.extend([
            f"### Generated Answer {label}",
            "",
            r.answer.get("answer_markdown", "*No answer generated*") if r.answer else "*Error generating answer*",
            "",
        ])

        # Scores
        if r.evaluation:
            lines.extend(["### Evaluation Scores", ""])
            s = r.evaluation.get("scores", {})
            lines.append(f"- **Grounded Correctness:** {s.get('grounded_correctness', 0):.2f}")
            if s.get("grounded_correctness_original") is not None:
                lines.append(f"  - Original ({_eval_model}): {s['grounded_correctness_original']:.2f}")
                lines.append(f"  - Blended with RAGAS: {s.get('grounded_correctness', 0):.2f}")
            lines.append(f"- **Completeness:** {s.get('completeness', 0):.2f}")
            lines.append(f"- **Precision:** {s.get('precision', 0):.2f}")
            lines.append(f"- **Clarity:** {s.get('clarity', 0):.2f}")
            lines.append(f"- **Citation Quality:** {s.get('citation_quality', 0):.2f}")
            lines.append(f"- **Overall:** {r.evaluation.get('overall_score', 0):.2f}")

            ragas = r.evaluation.get("ragas_faithfulness")
            if ragas is not None:
                lines.append(f"- **RAGAS Faithfulness:** {ragas:.2f}")

        # Required concepts
        if r.evaluation and r.evaluation.get("required_concepts_coverage"):
            lines.extend(["", "### Required Concepts", ""])
            for concept in r.evaluation["required_concepts_coverage"]:
                icon = {"present": "✅", "partial": "🔶", "missing": "❌"}.get(
                    concept.get("status", ""), "❓")
                lines.append(f"- {icon} **{concept.get('concept', '')}** — {concept.get('notes', '')}")

        lines.extend(["", "---", ""])

    # Improvements
    lines.extend(["## Proposed Document Improvements", ""])
    if improvements.get("summary"):
        lines.append(f"**Summary:** {improvements['summary']}")
        lines.append("")

    for change in improvements.get("proposed_changes", []):
        review_tag = "🔒 HUMAN REVIEW" if change.get("requires_human_review") else "🤖 Auto-merge"
        lines.extend([
            f"### {change.get('id', 'EDIT-???')} [{change.get('priority', '?')}] {review_tag}",
            f"**Target:** {change.get('target_document', '?')} → {change.get('target_section', '?')}",
            f"**Type:** {change.get('change_type', '?')}",
            f"**Description:** {change.get('description', '')}",
            "",
        ])

    return "\n".join(lines)


# ═══════════════════════════════════════════════════════
# Helpers: KnowledgeStore integration
# ═══════════════════════════════════════════════════════

def _record_retrieval_feedback(store, all_evidence, all_answers):
    """Record which retrieved chunks were actually cited (Tier 2 quality feedback)."""
    if not store:
        return
    for qid, evidence_data in all_evidence.items():
        answer = all_answers.get(qid, {})
        if answer.get("tier") == 1:
            continue
        cited_chunks = set(answer.get("cited_chunks", []))
        answer_text = answer.get("answer_markdown", "")
        for chunk in evidence_data.get("evidence", []):
            chunk_id = chunk["chunk_id"]
            was_cited = (chunk_id in cited_chunks or
                         f"[[chunk:{chunk_id}]]" in answer_text or
                         chunk_id in answer_text)
            store.record_retrieval_outcome(
                question_id=qid,
                query_variant=chunk.get("query_variant", qid),
                chunk_id=chunk_id,
                was_cited=was_cited,
                relevance_score=chunk.get("relevance", 0.5),
            )


def _print_learning_summary(store, results, elapsed, tier):
    """Print a summary of what the pipeline learned this run."""
    if not store or not RICH_AVAILABLE:
        return

    summary = store.summary()
    run_num = summary["total_runs"]
    learning_lines = []

    for qid, r in results.items():
        if not r.evaluation:
            continue
        trend = store.get_score_trend(qid, last_n=5)
        if len(trend) >= 2:
            scores = [t["scores"].get("completeness", 0) for t in trend]
            direction = ("improving" if scores[-1] > scores[-2]
                         else "declining" if scores[-1] < scores[-2]
                         else "stable")
            learning_lines.append(
                f"{qid}: {direction} (completeness: "
                f"{' → '.join(f'{s:.2f}' for s in scores[-3:])})")

    persistent = store.get_persistent_gaps()
    if persistent:
        learning_lines.append("")
        learning_lines.append(f"[yellow]Persistent gaps ({len(persistent)}):[/yellow]")
        for g in persistent[:5]:
            learning_lines.append(
                f"  • {g['concept']} (x{g['occurrences']} runs, "
                f"affects {', '.join(g['question_ids'])})")

    cache_stats = summary["research_cache"]
    if cache_stats["total_entries"] > 0:
        learning_lines.append("")
        learning_lines.append(
            f"Research cache: {cache_stats['active_entries']} results cached "
            f"({cache_stats['total_hits']} total hits)")

    if tier == 2:
        effective = store.get_effective_query_variants(min_citation_rate=0.5)
        wasted = store.get_wasted_query_variants(max_citation_rate=0.1)
        if effective or wasted:
            learning_lines.append("")
            learning_lines.append(
                f"Retrieval: {len(effective)} effective query variants, "
                f"{len(wasted)} low-value variants")

    if learning_lines:
        console.print(Panel(
            "\n".join(learning_lines),
            title=f"🧠 Learning Summary (Run #{run_num})",
            border_style="yellow"
        ))
    else:
        console.print(Panel(
            f"First run — baseline established. Run again after doc updates to see trends.",
            title=f"🧠 Learning Summary (Run #{run_num})",
            border_style="yellow"
        ))


def main():
    """Run the full two-phase parallel pipeline."""
    parser = argparse.ArgumentParser(description="DDC Documentation Evaluator — Parallel Pipeline v3")
    parser.add_argument("--sequential", action="store_true", help="Run sequentially (easier debugging)")
    args = parser.parse_args()

    timestamp = datetime.now().isoformat()

    if RICH_AVAILABLE:
        console.print(Panel(
            "[bold]DDC Documentation Evaluator — Two-Phase Parallel Pipeline v3[/bold]\n\n"
            "Phase 1: Build shared context (sequential)\n"
            "Phase 2: Process all questions (parallel)\n"
            "Phase 3: Finalize and report (sequential)\n\n"
            "Features: Claim cache • Self-healing • RAGAS cross-check\n"
            "          Parallel verification • Parallel evaluation",
            title="🚀 Pipeline Starting",
            border_style="cyan"
        ))

    # Preflight
    check_prerequisites()

    # Load persistent knowledge store (optional — graceful if unavailable)
    store = None
    try:
        from agents.knowledge_store import KnowledgeStore, initialize_default_terminology
        store = KnowledgeStore.load()
        store.increment_run()
        run_number = store.data["meta"]["total_runs"]
        if run_number == 1:
            initialize_default_terminology(store)
        store_summary = store.summary()
        if RICH_AVAILABLE:
            console.print(Panel(
                f"[bold]Run #{run_number}[/bold]\n"
                f"Entities: {store_summary['entities']} | "
                f"Research cache: {store_summary['research_cache']['active_entries']} active | "
                f"Eval records: {store_summary['evaluation_records']}",
                title="🧠 Knowledge Store",
                border_style="yellow"
            ))
    except ImportError:
        if RICH_AVAILABLE:
            console.print("  [dim]KnowledgeStore not available — running without persistent memory[/dim]")

    start_time = time.time()

    # ═══ PHASE 1: Build shared context ═══
    if RICH_AVAILABLE:
        console.print(f"\n[bold cyan]═══ PHASE 1: BUILDING SHARED CONTEXT ═══[/bold cyan]")

    from agents.shared_context import build_shared_context
    ctx = build_shared_context(console=console)
    ctx._store = store  # Attach store for phase 3

    # ═══ PHASE 2: Process questions ═══
    if args.sequential:
        results = run_sequential(ctx)
    else:
        results = run_parallel(ctx)

    # ═══ PHASE 3: Finalize ═══
    improvements = phase3_finalize(ctx, results, timestamp)

    elapsed = time.time() - start_time

    # ── Record retrieval feedback (Tier 2 only) ──
    if store and ctx.tier == 2:
        _record_retrieval_feedback(store, ctx.all_evidence,
                                   {qid: r.answer for qid, r in results.items()})

    # ── Record evaluation data to knowledge store ──
    if store:
        for qid, r in results.items():
            if r.evaluation:
                missing_concepts = [
                    c.get("concept", "") for c in r.evaluation.get("required_concepts_coverage", [])
                    if c.get("status") in ["missing", "partial"]
                ]
                store.record_evaluation(
                    timestamp=timestamp,
                    question_id=qid,
                    scores=r.evaluation.get("scores", {}),
                    passed=r.evaluation.get("passed", False),
                    loop=r.loop,
                    missing_concepts=missing_concepts,
                    failures=r.evaluation.get("failures", []),
                )
                for concept in missing_concepts:
                    gap_id = f"{qid}-{concept[:30].replace(' ', '_').upper()}"
                    store.track_gap(
                        gap_id=gap_id, description=concept,
                        question_id=qid,
                        priority="P0" if concept in r.evaluation.get("failures", []) else "P1",
                    )
        store.save()

    # ── Apply doc edits (gap patches to markdown source files) ──
    all_gap_reports = {qid: r.gap_report for qid, r in results.items() if r.gap_report}
    if all_gap_reports:
        try:
            from agents.ingestion_agent import get_ingestion_result
            from agents.doc_editor_agent import apply_edits
            ingestion_result = get_ingestion_result()
            # Merge all gap reports into one
            merged_gaps = []
            for gr in all_gap_reports.values():
                merged_gaps.extend(gr.get("verified_gaps", []))
            if merged_gaps and ingestion_result:
                markdown_files = ingestion_result.get("markdown_files", {})
                if markdown_files:
                    combined_report = {"verified_gaps": merged_gaps}
                    edit_result = apply_edits(combined_report, markdown_files)
                    if edit_result.get("edit_count", 0) > 0:
                        auto = edit_result.get("auto_applied", 0)
                        flagged = edit_result.get("flagged", 0)
                        print(f"  ✓ Doc edits: {auto} auto-applied, {flagged} flagged for review")

                        # Verify edits were placed correctly
                        try:
                            from agents.edit_verifier import verify_edits, print_verification_report
                            verification = verify_edits(
                                edited_files=edit_result.get("edited_files", {}),
                                all_edits=edit_result.get("edits", []),
                                original_files=markdown_files
                            )
                            print_verification_report(verification)

                            # If edits failed verification, reject them
                            if not verification.get("verified", True):
                                failed_edits = [
                                    r for r in verification.get("edit_results", [])
                                    if r["verdict"] == "fail"
                                ]
                                if failed_edits:
                                    print(f"  ⚠ {len(failed_edits)} edits failed verification — "
                                          f"rejecting from approved edits")
                                    from agents.doc_editor_agent import load_approved_edits
                                    approved = load_approved_edits()
                                    # Remove failed edits by matching text preview
                                    failed_previews = {r["edit_text_preview"] for r in failed_edits}
                                    cleaned = [
                                        e for e in approved
                                        if e.get("new_text", "")[:100] not in failed_previews
                                    ]
                                    if len(cleaned) < len(approved):
                                        from agents.doc_editor_agent import _save_approved_edits
                                        _save_approved_edits(cleaned)
                                        print(f"  ✓ Removed {len(approved) - len(cleaned)} "
                                              f"failed edits from approved manifest")
                        except (ImportError, Exception) as e:
                            print(f"  [dim]Edit verification skipped: {e}[/dim]")
        except (ImportError, Exception) as e:
            print(f"  [dim]Doc edit application skipped: {e}[/dim]")

    # ── Final summary ──
    if RICH_AVAILABLE:
        console.print("\n")
        table = Table(title=f"Final Results (Tier {ctx.tier})", border_style="cyan")
        table.add_column("Question", style="bold")
        table.add_column("Tier", justify="center")
        table.add_column("Loop", justify="center")
        table.add_column("Score", justify="center")
        table.add_column("RAGAS", justify="center")
        table.add_column("Cache Hits", justify="center")
        table.add_column("Time", justify="center")
        table.add_column("Result", justify="center")

        for qid, r in results.items():
            score = f"{r.evaluation.get('overall_score', 0):.2f}" if r.evaluation else "ERR"
            passed = r.evaluation.get("passed", False) if r.evaluation else False
            result_str = "[green]PASS[/green]" if passed else "[red]FAIL[/red]"
            loop_color = "magenta" if r.loop == "B" else "blue"
            ragas = r.evaluation.get("ragas_faithfulness") if r.evaluation else None
            ragas_str = f"{ragas:.2f}" if ragas is not None else "—"
            cache_hits = r.verification.get("stats", {}).get("cache_hits", 0) if r.verification else 0

            tier_color = "green" if ctx.tier == 1 else "blue"

            table.add_row(
                qid,
                f"[{tier_color}]{ctx.tier}[/{tier_color}]",
                f"[{loop_color}]{r.loop}[/{loop_color}]",
                score,
                ragas_str,
                str(cache_hits),
                f"{r.elapsed:.1f}s",
                result_str
            )

        console.print(table)

        # Performance breakdown
        console.print(f"\n[dim]Phase 1 (setup): {ctx.phase1_elapsed:.1f}s[/dim]")
        if not args.sequential:
            wall_clock = max(r.elapsed for r in results.values()) if results else 0
            console.print(f"[dim]Phase 2 (parallel): {wall_clock:.1f}s wall-clock[/dim]")
        console.print(f"[dim]Total: {elapsed:.1f}s[/dim]")

        if ctx.claim_cache:
            stats = ctx.claim_cache.stats
            console.print(f"[dim]Claim cache: {stats['total_cached']} entries, "
                         f"{stats['hit_rate']:.0%} hit rate[/dim]")

        console.print(f"\n[bold]Full report:[/bold] reports/latest_report.md")
        console.print(f"[bold]Score data:[/bold] reports/latest_scores.json")
        if store:
            console.print(f"[bold]Knowledge store:[/bold] knowledge/knowledge_store.json")

        # Learning summary (uses KnowledgeStore trends)
        if store:
            _print_learning_summary(store, results, elapsed, ctx.tier)

        # Cost breakdown
        try:
            from agents.cost_tracker import get_tracker
            console.print("\n[bold cyan]═══ COST BREAKDOWN ═══[/bold cyan]")
            get_tracker().print_summary()
        except ImportError:
            pass
    else:
        print(f"\nCompleted in {elapsed:.1f}s")
        print("Reports saved to reports/")
        try:
            from agents.cost_tracker import get_tracker
            print("\n═══ COST BREAKDOWN ═══")
            get_tracker().print_summary()
        except ImportError:
            pass


if __name__ == "__main__":
    main()
