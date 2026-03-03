"""
DocVerify — Aegra-Compatible Graph
====================================
Wraps the DocVerify pipeline as an Aegra/LangGraph SDK-compatible graph.

Aegra expects:
  - Input: {"messages": [{"type": "human", "content": "..."}]}
  - Output: {"messages": [..., {"type": "ai", "content": "..."}]}

This wrapper translates between the SDK's message format and our
pipeline's custom PipelineState.

For direct pipeline access (non-Aegra), use graph.py instead.
"""

from __future__ import annotations

import os
import time
import json
from typing import Any, Annotated
from typing_extensions import TypedDict

from langgraph.graph import StateGraph, START, END
from langgraph.graph.message import add_messages


# ─── Aegra-compatible message state ────────────────────────────

class AgentState(TypedDict):
    """Standard messages-based state for Aegra/LangGraph SDK compatibility."""
    messages: Annotated[list, add_messages]


# ─── Report formatting helpers ─────────────────────────────

def _format_score_bar(value, width=20):
    """ASCII progress bar for scores."""
    filled = round(value * width)
    bar = "█" * filled + "░" * (width - filled)
    return f"{bar} {value:.2f}"


def _format_evaluation_result(evals, elapsed=0, report_path=""):
    """Format pipeline evaluation results as a clean readable report."""
    lines = []
    lines.append("╔══════════════════════════════════════════╗")
    lines.append("║        EVALUATION COMPLETE               ║")
    lines.append("╚══════════════════════════════════════════╝")
    lines.append("")

    total_pass = 0
    total = len(evals)

    for qid in sorted(evals.keys()):
        e = evals[qid]
        score = e.get("overall_score", 0)
        passed = e.get("passed", False)
        if passed:
            total_pass += 1
        icon = "✅" if passed else "❌"
        loop = e.get("loop", "A")

        lines.append(f"{'─' * 44}")
        lines.append(f"{icon} {qid} (Loop {loop})  —  Overall: {score:.3f}  {'PASS' if passed else 'FAIL'}")
        lines.append(f"{'─' * 44}")

        # Score breakdown
        scores = e.get("scores", {})
        if scores:
            for metric, val in scores.items():
                label = metric.replace("_", " ").title()
                lines.append(f"  {label:.<24} {_format_score_bar(val)}")
        lines.append("")

        # Claim verification summary
        claims = e.get("claim_verification", [])
        if claims:
            supported = sum(1 for c in claims if c.get("status") == "supported")
            total_claims = len(claims)
            lines.append(f"  Claims: {supported}/{total_claims} supported")

            # Show failed claims
            failed = [c for c in claims if c.get("status") != "supported"]
            if failed:
                lines.append(f"  ⚠ Unsupported claims:")
                for c in failed[:5]:
                    claim_text = c.get("claim", "")[:80]
                    lines.append(f"    • {claim_text}...")
            lines.append("")

        # Improvements proposed
        improvements = e.get("improvements", [])
        if improvements:
            lines.append(f"  📝 {len(improvements)} doc improvements proposed")
            for imp in improvements[:3]:
                gap = imp.get("gap", imp.get("description", ""))[:70]
                lines.append(f"    → {gap}")
            lines.append("")

    # Summary
    lines.append("═" * 44)
    lines.append(f"  Results: {total_pass}/{total} questions passed")
    if elapsed:
        lines.append(f"  Duration: {elapsed:.1f}s")
    if report_path:
        lines.append(f"  Report: {report_path}")
    lines.append("═" * 44)

    return "\n".join(lines)


def _format_report(report_data):
    """Format a saved JSON report for the status command."""
    # Handle both flat {Q1: {...}, Q2: {...}} and nested formats
    if isinstance(report_data, dict):
        # Check if it's question-keyed
        questions = {}
        meta = {}
        for k, v in report_data.items():
            if k.startswith("Q") and isinstance(v, dict):
                questions[k] = v
            else:
                meta[k] = v

        if questions:
            return _format_evaluation_result(
                questions,
                meta.get("elapsed", 0),
                meta.get("report_path", "")
            )

    # Fallback: format whatever we have cleanly
    lines = []
    lines.append("╔══════════════════════════════════════════╗")
    lines.append("║          LATEST RESULTS                  ║")
    lines.append("╚══════════════════════════════════════════╝")
    lines.append("")

    def _walk(obj, indent=0):
        prefix = "  " * indent
        if isinstance(obj, dict):
            for k, v in obj.items():
                if isinstance(v, (dict, list)):
                    lines.append(f"{prefix}{k}:")
                    _walk(v, indent + 1)
                elif isinstance(v, float):
                    lines.append(f"{prefix}{k}: {v:.3f}")
                else:
                    lines.append(f"{prefix}{k}: {v}")
        elif isinstance(obj, list):
            for i, item in enumerate(obj[:10]):
                if isinstance(item, dict):
                    claim = item.get("claim", str(item))[:80]
                    status = item.get("status", "")
                    icon = "✅" if status == "supported" else "⚠" if status else ""
                    lines.append(f"{prefix}{icon} {claim}")
                else:
                    lines.append(f"{prefix}• {str(item)[:80]}")
            if len(obj) > 10:
                lines.append(f"{prefix}... and {len(obj) - 10} more")

    _walk(report_data)
    return "\n".join(lines)




def docverify_node(state: AgentState) -> dict:
    """
    Main agent node. Interprets the user message as a command:
      - "evaluate" or "run" → triggers full pipeline
      - "status" → returns last run status
      - anything else → treated as a question for /ask mode
    """
    from langchain_core.messages import AIMessage

    # Get the last human message
    last_msg = ""
    for msg in reversed(state["messages"]):
        if hasattr(msg, "type") and msg.type == "human":
            last_msg = msg.content
            break
        elif isinstance(msg, dict) and msg.get("type") == "human":
            last_msg = msg.get("content", "")
            break

    last_msg_lower = last_msg.strip().lower()

    # ── Command: evaluate / run ────────────────────────
    if last_msg_lower in ("evaluate", "run", "run evaluation", "start"):
        try:
            from docverify.graph import run as run_pipeline
            result = run_pipeline(tenant_id="default")

            # Build comprehensive structured response
            evals = result.get("evaluations", {})
            answers = result.get("answers", {})
            verifications = result.get("verifications", {})
            improvements = result.get("improvements", {})
            questions = result.get("questions", {})
            routing = result.get("routing", {})
            elapsed = result.get("elapsed", 0)
            report_path = result.get("report_path", "")

            # Build JSON payload for the dashboard
            payload = {
                "_type": "evaluation_result",
                "elapsed": elapsed,
                "report_path": report_path,
                "questions": {}
            }

            for qid in sorted(evals.keys()):
                e = evals[qid]
                a = answers.get(qid, {})
                v = verifications.get(qid, {})
                r = routing.get(qid, {})

                q_data = {
                    "question_text": questions.get(qid, ""),
                    "loop": r.get("loop", "A"),
                    "route_reason": r.get("reason", ""),

                    # Answer
                    "answer_markdown": a.get("answer_markdown", ""),
                    "cited_chunks": a.get("cited_chunks", []),
                    "evidence_chunks_provided": a.get("evidence_chunks_provided", 0),
                    "evidence_chunks_cited": a.get("evidence_chunks_cited", 0),
                    "outside_knowledge_flags": a.get("warnings", {}).get("outside_knowledge_flags", []),

                    # Scores
                    "overall_score": e.get("overall_score", 0),
                    "passed": e.get("passed", False),
                    "scores": e.get("scores", {}),

                    # Verification
                    "verification": {
                        "grounding": v.get("grounding", {}),
                        "nli": v.get("nli", {}),
                        "ragas": v.get("ragas", {}),
                        "claims_total": v.get("claims_total", 0),
                        "claims_supported": v.get("claims_supported", 0),
                        "claims_failed": v.get("claims_failed", 0),
                        "overrides": v.get("overrides", 0),
                        "claim_details": v.get("claim_details", [])[:20],  # Cap to prevent huge messages
                    },
                }

                payload["questions"][qid] = q_data

            # Improvements (across all questions)
            edits_list = []
            if isinstance(improvements, dict):
                proposed = improvements.get("proposed_changes", improvements.get("edits", []))
                if isinstance(proposed, list):
                    for edit in proposed:
                        edits_list.append({
                            "target_file": edit.get("target_file", edit.get("file", "")),
                            "gap_description": edit.get("gap", edit.get("description", edit.get("gap_description", ""))),
                            "edit_content": edit.get("content", edit.get("edit", edit.get("edit_content", "")))[:500],
                            "edit_type": edit.get("type", edit.get("edit_type", "addition")),
                            "question_id": edit.get("question_id", edit.get("qid", "")),
                        })
                elif isinstance(proposed, dict):
                    for qid_key, qid_edits in proposed.items():
                        if isinstance(qid_edits, list):
                            for edit in qid_edits:
                                edits_list.append({
                                    "target_file": edit.get("target_file", edit.get("file", "")),
                                    "gap_description": edit.get("gap", edit.get("description", "")),
                                    "edit_content": edit.get("content", edit.get("edit", ""))[:500],
                                    "edit_type": edit.get("type", "addition"),
                                    "question_id": qid_key,
                                })

            payload["improvements"] = edits_list

            # Encode as JSON block inside the message so dashboard can parse it
            response_text = "```json:evaluation\n" + json.dumps(payload, indent=2, default=str) + "\n```"

            # Also save full payload for status command
            from pathlib import Path
            Path("reports").mkdir(exist_ok=True)
            with open("reports/latest_dashboard.json", "w") as f:
                json.dump(payload, f, indent=2, default=str)

        except Exception as e:
            import traceback
            response_text = f"**Pipeline failed:** {str(e)}\n\n```\n{traceback.format_exc()}\n```"

        return {"messages": [AIMessage(content=response_text)]}

    # ── Command: status ────────────────────────────────
    elif last_msg_lower == "status":
        from pathlib import Path
        # Prefer the dashboard JSON (has all the rich data)
        dashboard_file = Path("reports/latest_dashboard.json")
        if dashboard_file.exists():
            payload = json.loads(dashboard_file.read_text())
            response_text = "```json:evaluation\n" + json.dumps(payload, indent=2, default=str) + "\n```"
        else:
            # Fallback to scores JSON
            reports = sorted(Path("reports").glob("*.json"), reverse=True)
            if reports:
                latest = json.loads(reports[0].read_text())
                response_text = _format_report(latest)
            else:
                response_text = "No evaluation runs found yet. Send 'evaluate' to start one."

        return {"messages": [AIMessage(content=response_text)]}

    # ── Default: single question (ask mode) ────────────
    else:
        try:
            from agents.retriever_agent import retrieve_evidence
            from agents.answer_agent import answer_question

            evidence = retrieve_evidence("adhoc", last_msg)
            answer = answer_question("adhoc", last_msg, evidence["evidence"])

            response_text = answer.get("answer_markdown", "I couldn't generate an answer.")
            cited = answer.get("evidence_chunks_cited", 0)
            provided = answer.get("evidence_chunks_provided", 0)
            response_text += f"\n\n---\n*{cited}/{provided} chunks cited*"

        except Exception as e:
            response_text = f"Error answering question: {str(e)}"

        return {"messages": [AIMessage(content=response_text)]}


# ─── Build graph ───────────────────────────────────────────────

def build_graph():
    """Build Aegra/LangGraph SDK-compatible graph."""
    graph = StateGraph(AgentState)
    graph.add_node("docverify", docverify_node)
    graph.add_edge(START, "docverify")
    graph.add_edge("docverify", END)
    return graph.compile()


# Expose for langgraph.json
graph = build_graph()
