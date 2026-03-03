"""
RAGAS Integration — Faithfulness & Answer Relevancy Scoring
=============================================================

Adds calibrated, research-backed evaluation metrics from the RAGAS
framework alongside the existing GPT-5.2 evaluator.

RAGAS Faithfulness:
  - Decomposes answer into claims (similar to our claim decomposer)
  - Checks each claim against retrieved context via LLM
  - Returns: supported_claims / total_claims (0.0 - 1.0)
  - Uses GPT-4o-mini by default (cheap, fast, well-calibrated)

Why use RAGAS alongside our custom evaluator:
  - RAGAS faithfulness is the industry-standard RAG metric
  - Provides a second LLM-based evaluation signal independent of GPT-5.2
  - Better calibrated than raw GPT scoring (it's claim-count-based, not vibes-based)
  - Benchmarked on HaluBench — we know its strengths and weaknesses

Requirements:
  pip install ragas openai

Usage:
  from ragas_evaluator import compute_ragas_metrics
  metrics = compute_ragas_metrics(question, answer, contexts)
  # {"faithfulness": 0.85, "answer_relevancy": 0.91}
"""

import os
import asyncio
import threading
from typing import Optional

# RAGAS uses asyncio internally. When multiple threads call it concurrently,
# event loops can conflict. Serialize RAGAS calls with a lock.
_ragas_lock = threading.Lock()

# ============================================================
# Configuration
# ============================================================

# LLM for RAGAS evaluation — GPT-4o-mini is cheapest and well-calibrated
# Can override via RAGAS_LLM_MODEL env var
RAGAS_LLM_MODEL = os.environ.get("RAGAS_LLM_MODEL", "gpt-4o-mini")


def compute_ragas_metrics(question: str, answer: str, contexts: list[str],
                          llm_model: str = None) -> dict:
    """
    Compute RAGAS Faithfulness and Answer Relevancy for a single QA pair.

    Args:
        question: The question text
        answer: The generated answer text
        contexts: List of evidence text strings (retrieved chunks or page texts)
        llm_model: Override LLM model for RAGAS (default: gpt-4o-mini)

    Returns:
        {
            "faithfulness": float (0-1),
            "answer_relevancy": float (0-1),
            "ragas_available": True,
            "llm_model": str,
            "error": None | str
        }
    """
    model = llm_model or RAGAS_LLM_MODEL

    # Serialize RAGAS calls — asyncio event loops conflict across threads
    with _ragas_lock:
        return _compute_ragas_metrics_inner(question, answer, contexts, model)


def _compute_ragas_metrics_inner(question, answer, contexts, model):
    """Inner implementation of RAGAS metrics (called under lock)."""
    try:
        from openai import AsyncOpenAI
        from ragas.llms import llm_factory

        # Handle both RAGAS v0.3 and v0.4 import paths
        Faithfulness = None
        AnswerRelevancy = None
        try:
            # v0.4+ collections API
            from ragas.metrics.collections import Faithfulness, AnswerRelevancy
        except ImportError:
            try:
                # v0.3 legacy API
                from ragas.metrics import Faithfulness, AnswerRelevancy
            except ImportError:
                pass

        if Faithfulness is None:
            return {
                "faithfulness": None,
                "answer_relevancy": None,
                "ragas_available": False,
                "llm_model": model,
                "error": "Could not import Faithfulness from ragas.metrics or ragas.metrics.collections",
            }

        # Setup LLM — pass max_tokens to avoid truncation on long answers
        client = AsyncOpenAI(api_key=os.environ.get("OPENAI_API_KEY"))
        llm = llm_factory(model, client=client, max_tokens=6000)

        # Create scorers
        faithfulness_scorer = Faithfulness(llm=llm)

        # Run async scoring with thread-safe helper
        faithfulness_result = _run_async_safely(
            faithfulness_scorer.ascore(
                user_input=question,
                response=answer,
                retrieved_contexts=contexts,
            )
        )

        faith_value = None
        if faithfulness_result is not None:
            if hasattr(faithfulness_result, 'value'):
                faith_value = round(faithfulness_result.value, 4)
            elif isinstance(faithfulness_result, (int, float)):
                faith_value = round(float(faithfulness_result), 4)

        # Answer relevancy is optional — requires embeddings, skip if it fails
        relevancy_value = None
        if AnswerRelevancy is not None:
            try:
                from ragas.embeddings.base import embedding_factory
                embeddings = embedding_factory("openai", model="text-embedding-3-small", client=client)
                relevancy_scorer = AnswerRelevancy(llm=llm, embeddings=embeddings)
                relevancy_result = _run_async_safely(
                    relevancy_scorer.ascore(
                        user_input=question,
                        response=answer,
                        retrieved_contexts=contexts,
                    )
                )
                if relevancy_result is not None:
                    if hasattr(relevancy_result, 'value'):
                        relevancy_value = round(relevancy_result.value, 4)
                    elif isinstance(relevancy_result, (int, float)):
                        relevancy_value = round(float(relevancy_result), 4)
            except Exception:
                pass  # Relevancy is nice-to-have, faithfulness is what matters

        # Track estimated RAGAS cost (RAGAS makes ~2-4 internal LLM calls
        # for faithfulness: statement extraction + NLI verification)
        try:
            from agents.cost_tracker import track_cost
            # Estimate: input ≈ question + answer + contexts, output ≈ 1/3 of input
            est_input = (len(question) + len(answer) + sum(len(c) for c in contexts)) // 4
            est_output = est_input // 3
            # RAGAS typically makes 2-3 calls internally
            track_cost("ragas", "—", model, est_input * 2, est_output * 2)
        except ImportError:
            pass

        return {
            "faithfulness": faith_value,
            "answer_relevancy": relevancy_value,
            "ragas_available": True,
            "llm_model": model,
            "error": None,
        }

    except ImportError as e:
        return {
            "faithfulness": None,
            "answer_relevancy": None,
            "ragas_available": False,
            "llm_model": model,
            "error": f"RAGAS not installed: {e}. Install with: pip install ragas",
        }
    except Exception as e:
        return {
            "faithfulness": None,
            "answer_relevancy": None,
            "ragas_available": False,
            "llm_model": model,
            "error": f"RAGAS evaluation failed: {str(e)[:200]}",
        }


def compute_faithfulness_only(question: str, answer: str, contexts: list[str],
                              llm_model: str = None) -> Optional[float]:
    """
    Convenience: compute only faithfulness score.
    Returns float 0-1, or None if RAGAS unavailable.
    """
    result = compute_ragas_metrics(question, answer, contexts, llm_model)
    return result.get("faithfulness")


def _get_or_create_event_loop():
    """
    Create a fresh event loop for this call.

    When running inside ThreadPoolExecutor (parallel pipeline),
    threads don't have an event loop. We create a dedicated one
    per call and return it. The caller should NOT close it —
    we suppress the httpx cleanup errors that happen when the
    loop is garbage collected.
    """
    # Always create a fresh loop for thread safety
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    return loop


def _run_async_safely(coro):
    """
    Run an async coroutine safely from a sync/threaded context.
    Creates an isolated event loop that does NOT become the thread default.
    """
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        # Suppress "Event loop is closed" noise from httpx cleanup tasks.
        # These fire after loop.close() when AsyncClient tries to clean up
        # connections. They're harmless but noisy.
        try:
            loop.run_until_complete(loop.shutdown_asyncgens())
        except Exception:
            pass

        # Silence the "Task exception was never retrieved" warnings
        for task in asyncio.all_tasks(loop):
            if not task.done():
                task.cancel()
            # Suppress the exception so it doesn't print
            if task.done() and not task.cancelled():
                try:
                    task.exception()
                except (asyncio.CancelledError, asyncio.InvalidStateError):
                    pass

        loop.close()


# ============================================================
# Batch evaluation for pipeline integration
# ============================================================

def evaluate_batch(qa_pairs: list[dict]) -> list[dict]:
    """
    Evaluate a batch of QA pairs.

    Args:
        qa_pairs: List of {question, answer, contexts} dicts

    Returns:
        List of RAGAS metric dicts (same order)
    """
    results = []
    for pair in qa_pairs:
        result = compute_ragas_metrics(
            question=pair["question"],
            answer=pair["answer"],
            contexts=pair["contexts"],
        )
        results.append(result)
    return results


# ============================================================
# Test
# ============================================================

if __name__ == "__main__":
    print("=== RAGAS Integration Test ===\n")

    # Test with mock data (requires OPENAI_API_KEY)
    test_q = "How does DDC ensure data redundancy?"
    test_a = (
        "DDC ensures data redundancy through erasure coding with a 16/48 scheme. "
        "Any 16 of the 48 shares can reconstruct the original data. "
        "For smaller pieces under 16KB, simple replication is used instead."
    )
    test_contexts = [
        "Data redundancy uses replication for small pieces and erasure coding "
        "for pieces larger than 16KB. Dragon 1 cluster uses a 16/48 erasure "
        "coding scheme. Any 16 of 48 shares can reconstruct the original data.",
    ]

    result = compute_ragas_metrics(test_q, test_a, test_contexts)
    print(f"  RAGAS available: {result['ragas_available']}")
    if result["error"]:
        print(f"  Error: {result['error']}")
    else:
        print(f"  Faithfulness: {result['faithfulness']}")
        print(f"  Answer Relevancy: {result['answer_relevancy']}")
        print(f"  LLM: {result['llm_model']}")
