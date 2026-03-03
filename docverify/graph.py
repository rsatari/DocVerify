"""
DocVerify — LangGraph Agent Graph
==================================
Replaces run_pipeline.py with a LangGraph StateGraph.
Each node wraps an existing agent. The graph handles orchestration,
state passing, and conditional routing (Loop A vs Loop B).

Usage:
    from docverify.graph import build_graph
    graph = build_graph()
    result = graph.invoke({"tenant_id": "default"})
"""

from __future__ import annotations

import os
import time
from typing import Any, Optional
from typing_extensions import TypedDict

from langgraph.graph import StateGraph, START, END


# ─── State Schema ───────────────────────────────────────────────

class PipelineState(TypedDict, total=False):
    """Shared state passed between all nodes."""
    # Config
    tenant_id: str
    run_id: str
    started_at: float

    # Phase 1: Ingestion
    chunks: list[dict]
    all_pages: list[dict]

    # Phase 2: Questions & Retrieval
    questions: dict              # {qid: question_text}
    evidence: dict               # {qid: {evidence: [...], stats: {...}}}

    # Phase 3: Routing
    routing: dict                # {qid: {loop: "A"|"B", reason: ..., targets: [...]}}

    # Phase 4: Answers
    answers: dict                # {qid: answer_data}

    # Phase 5: Loop B (optional)
    claims: dict                 # {qid: claims_data}
    research: dict               # {qid: [research_results]}
    correlations: dict           # {qid: correlation}

    # Phase 6: Verification & Evaluation
    verifications: dict          # {qid: verification_result}
    evaluations: dict            # {qid: evaluation_result}

    # Phase 7: Editing & Report
    improvements: dict
    report: str
    report_path: str

    # Metadata
    errors: list[str]
    elapsed: float


# ─── Node Functions ─────────────────────────────────────────────

def ingest_node(state: PipelineState) -> dict:
    """Node 1: Ingest PDFs → chunks + pages."""
    from agents.ingestion_agent import ingest_all_pdfs
    print(f"  [ingest] Starting PDF ingestion...")
    chunks = ingest_all_pdfs()
    print(f"  [ingest] ✓ {len(chunks)} chunks produced")
    return {"chunks": chunks}


def retrieve_node(state: PipelineState) -> dict:
    """Node 2: Load questions from eval spec, retrieve evidence."""
    import yaml
    from agents.retriever_agent import retrieve_evidence

    # Load questions
    with open("evaluation/evaluation_spec.yaml") as f:
        spec = yaml.safe_load(f)
    questions = {qid: q["text"] for qid, q in spec["questions"].items()}

    # Retrieve evidence for each
    all_evidence = {}
    for qid, qtext in questions.items():
        print(f"  [retrieve] {qid}...")
        evidence = retrieve_evidence(qid, qtext)
        all_evidence[qid] = evidence
        print(f"  [retrieve] ✓ {qid}: {evidence['stats']['returned']} chunks")

    return {"questions": questions, "evidence": all_evidence}


def route_node(state: PipelineState) -> dict:
    """Node 3: Route each question to Loop A or Loop B."""
    import yaml
    from agents.router_agent import route_question

    with open("evaluation/evaluation_spec.yaml") as f:
        eval_spec = yaml.safe_load(f)

    routing = {}
    for qid, qtext in state["questions"].items():
        question_spec = eval_spec["questions"].get(qid, {})

        # Build evidence summary for router
        evidence_summary = ""
        if qid in state["evidence"]:
            for chunk in state["evidence"][qid]["evidence"][:5]:
                evidence_summary += f"[{chunk['chunk_id']}]: {chunk['text'][:150]}...\n"

        result = route_question(qid, qtext, question_spec, evidence_summary)
        routing[qid] = result
        print(f"  [route] {qid} → Loop {result['loop']}: {result['reason'][:80]}...")

    return {"routing": routing}


def answer_node(state: PipelineState) -> dict:
    """Node 4: Generate answers for all questions (closed-book)."""
    from agents.answer_agent import answer_question

    all_answers = {}
    for qid, qtext in state["questions"].items():
        print(f"  [answer] Generating {qid}...")
        evidence_chunks = state["evidence"][qid]["evidence"]
        answer = answer_question(qid, qtext, evidence_chunks)
        all_answers[qid] = answer
        print(f"  [answer] ✓ {qid}: {answer['evidence_chunks_cited']}/{answer['evidence_chunks_provided']} cited")

    return {"answers": all_answers}


def loop_b_research_node(state: PipelineState) -> dict:
    """Node 5 (conditional): Loop B research — claims, external research, correlation."""
    loop_b_qids = [qid for qid, r in state["routing"].items() if r["loop"] == "B"]

    if not loop_b_qids:
        print("  [loop_b] No Loop B questions — skipping")
        return {"claims": {}, "research": {}, "correlations": {}}

    from agents.claim_extractor_agent import extract_claims
    from agents.research_agent import research_claims_batch
    from agents.correlation_agent import build_comparison

    all_claims = {}
    all_research = {}
    all_correlations = {}

    for qid in loop_b_qids:
        answer_data = state["answers"][qid]
        evidence_chunks = state["evidence"][qid]["evidence"]
        targets = state["routing"][qid].get("comparison_targets", [])

        # Extract claims
        print(f"  [loop_b] {qid}: Extracting claims...")
        claims = extract_claims(answer_data)
        all_claims[qid] = claims

        # Research per platform
        research_results = []
        for platform in targets:
            print(f"  [loop_b] {qid}: Researching {platform}...")
            comparative_claims = [
                c for c in claims.get("claims", [])
                if c.get("needs_external") and
                (c.get("comparison_target", "").lower() == platform.lower()
                 or not c.get("comparison_target"))
            ]
            if not comparative_claims:
                comparative_claims = [{
                    "claim_id": f"{qid}-GENERAL",
                    "text": f"General security comparison with {platform}",
                    "needs_external": True,
                    "verification_query": f"{platform} security architecture encryption key management",
                }]
            results = research_claims_batch(comparative_claims, platform)
            research_results.extend(results)
        all_research[qid] = research_results

        # Correlate
        print(f"  [loop_b] {qid}: Building comparison...")
        correlation = build_comparison(
            question_id=qid,
            question_text=answer_data["question_text"],
            answer_data=answer_data,
            claims_data=claims,
            research_results=research_results,
            evidence_chunks=evidence_chunks,
        )
        all_correlations[qid] = correlation

    return {"claims": all_claims, "research": all_research, "correlations": all_correlations}


def evaluate_node(state: PipelineState) -> dict:
    """Node 6: Evaluate all answers."""
    from agents.evaluator_agent import evaluate_answer

    all_evaluations = {}
    for qid in state["questions"]:
        print(f"  [evaluate] Scoring {qid}...")
        answer_data = state["answers"][qid]
        evidence_chunks = state["evidence"][qid]["evidence"]
        evaluation = evaluate_answer(qid, answer_data, evidence_chunks)
        all_evaluations[qid] = evaluation

        score = evaluation.get("overall_score", 0)
        passed = evaluation.get("passed", False)
        status = "PASS ✅" if passed else "FAIL ❌"
        print(f"  [evaluate] ✓ {qid}: {score:.2f} — {status}")

    return {"evaluations": all_evaluations}


def edit_node(state: PipelineState) -> dict:
    """Node 7: Propose documentation improvements based on evaluation gaps."""
    from agents.editor_agent import propose_improvements

    # Gather all evidence chunks
    all_evidence_chunks = []
    for qid in state["evidence"]:
        all_evidence_chunks.extend(state["evidence"][qid]["evidence"])

    # Build evaluation reports list
    eval_reports = []
    for qid, eval_data in state["evaluations"].items():
        eval_reports.append({
            "question_id": qid,
            "question_text": state["questions"][qid],
            **eval_data,
        })

    print("  [editor] Generating improvement proposals...")
    improvements = propose_improvements(eval_reports, all_evidence_chunks)
    n_changes = len(improvements.get("proposed_changes", []))
    print(f"  [editor] ✓ {n_changes} improvements proposed")

    return {"improvements": improvements}


def report_node(state: PipelineState) -> dict:
    """Node 8: Generate final markdown report."""
    from datetime import datetime
    import json
    from pathlib import Path

    elapsed = time.time() - state.get("started_at", time.time())

    # Build summary table
    lines = [
        "# DocVerify Evaluation Report",
        f"**Generated:** {datetime.now().isoformat()}",
        f"**Tenant:** {state.get('tenant_id', 'default')}",
        "",
        "## Summary",
        "",
        "| Question | Loop | Overall | Correctness | Verdict |",
        "|----------|------|---------|-------------|---------|",
    ]

    for qid in sorted(state.get("evaluations", {}).keys()):
        eval_data = state["evaluations"][qid]
        score = eval_data.get("overall_score", 0)
        correctness = eval_data.get("scores", {}).get("grounded_correctness", 0)
        passed = eval_data.get("passed", False)
        verdict = "✅ PASS" if passed else "❌ FAIL"
        loop = state.get("routing", {}).get(qid, {}).get("loop", "A")
        lines.append(f"| {qid} | {loop} | {score:.2f} | {correctness:.2f} | {verdict} |")

    lines.extend(["", f"**Total time:** {elapsed:.1f}s", ""])

    # Per-question details
    for qid in sorted(state.get("evaluations", {}).keys()):
        eval_data = state["evaluations"][qid]
        answer_data = state["answers"][qid]
        lines.extend([
            "---",
            f"## {qid}: {state['questions'][qid][:80]}...",
            "",
            "### Answer",
            "",
            answer_data.get("answer_markdown", "*No answer*"),
            "",
            "### Scores",
            "",
        ])
        if "scores" in eval_data:
            s = eval_data["scores"]
            for key in ["grounded_correctness", "completeness", "precision", "clarity", "citation_quality"]:
                lines.append(f"- **{key}:** {s.get(key, 0):.2f}")
            lines.append(f"- **Overall:** {eval_data.get('overall_score', 0):.2f}")
        lines.append("")

    report_text = "\n".join(lines)

    # Save
    reports_dir = Path("reports")
    reports_dir.mkdir(exist_ok=True)
    report_path = str(reports_dir / "latest_report.md")
    with open(report_path, "w") as f:
        f.write(report_text)

    # Also save scores JSON
    scores_path = str(reports_dir / "latest_scores.json")
    with open(scores_path, "w") as f:
        json.dump(state.get("evaluations", {}), f, indent=2, default=str)

    print(f"  [report] ✓ Saved to {report_path}")

    return {"report": report_text, "report_path": report_path, "elapsed": elapsed}


# ─── Conditional Edges ──────────────────────────────────────────

def has_loop_b(state: PipelineState) -> str:
    """Check if any question was routed to Loop B."""
    for qid, r in state.get("routing", {}).items():
        if r.get("loop") == "B":
            return "loop_b"
    return "evaluate"


# ─── Build Graph ────────────────────────────────────────────────

def build_graph() -> StateGraph:
    """Build and compile the DocVerify LangGraph pipeline."""
    graph = StateGraph(PipelineState)

    # Add nodes
    graph.add_node("ingest", ingest_node)
    graph.add_node("retrieve", retrieve_node)
    graph.add_node("route", route_node)
    graph.add_node("answer", answer_node)
    graph.add_node("loop_b", loop_b_research_node)
    graph.add_node("evaluate", evaluate_node)
    graph.add_node("edit", edit_node)
    graph.add_node("report", report_node)

    # Wire edges
    graph.add_edge(START, "ingest")
    graph.add_edge("ingest", "retrieve")
    graph.add_edge("retrieve", "route")
    graph.add_edge("route", "answer")

    # Conditional: Loop B research or straight to evaluate
    graph.add_conditional_edges("answer", has_loop_b, {
        "loop_b": "loop_b",
        "evaluate": "evaluate",
    })
    graph.add_edge("loop_b", "evaluate")
    graph.add_edge("evaluate", "edit")
    graph.add_edge("edit", "report")
    graph.add_edge("report", END)

    return graph.compile()


# ─── Entry Point ────────────────────────────────────────────────

def run(tenant_id: str = "default") -> dict:
    """Run the full pipeline and return final state."""
    graph = build_graph()
    result = graph.invoke({
        "tenant_id": tenant_id,
        "started_at": time.time(),
        "errors": [],
    })
    return result


if __name__ == "__main__":
    result = run()
    evals = result.get("evaluations", {})
    for qid, e in sorted(evals.items()):
        score = e.get("overall_score", 0)
        passed = "PASS" if e.get("passed") else "FAIL"
        print(f"{qid}: {score:.2f} — {passed}")
