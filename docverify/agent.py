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


# ─── Single node: route command and run pipeline ───────────────

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

            # Build summary
            evals = result.get("evaluations", {})
            lines = ["**Evaluation Complete**\n"]
            all_passed = True
            for qid in sorted(evals.keys()):
                e = evals[qid]
                score = e.get("overall_score", 0)
                passed = e.get("passed", False)
                if not passed:
                    all_passed = False
                status = "✅ PASS" if passed else "❌ FAIL"
                lines.append(f"- **{qid}**: {score:.2f} — {status}")

            elapsed = result.get("elapsed", 0)
            lines.append(f"\n⏱ Completed in {elapsed:.1f}s")

            if result.get("report_path"):
                lines.append(f"📄 Full report: {result['report_path']}")

            response_text = "\n".join(lines)

        except Exception as e:
            response_text = f"**Pipeline failed:** {str(e)}"

        return {"messages": [AIMessage(content=response_text)]}

    # ── Command: status ────────────────────────────────
    elif last_msg_lower == "status":
        from pathlib import Path
        reports = sorted(Path("reports").glob("*.json"), reverse=True)
        if reports:
            latest = json.loads(reports[0].read_text())
            response_text = f"Latest scores:\n```json\n{json.dumps(latest, indent=2)[:2000]}\n```"
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
