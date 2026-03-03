"""
Router Agent (Dynamic Loop Selection — Tier-Aware)
====================================================
Evaluates each question to determine processing loop:
  - Loop A: Closed-book answering (internal docs only)
  - Loop B: Research-augmented comparison (internal + external sources)

Two-tier awareness:
  - Tier 1 (full-context): Biases toward Loop A because the answer agent
    has complete document text and can make category-level comparisons.
    Only routes to Loop B if platform-SPECIFIC details are genuinely needed
    beyond what the docs cover.
  - Tier 2 (RAG): Standard routing — uses evidence preview to decide.

Also scans evidence for category-comparison phrases ("traditional cloud stacks",
"provider infrastructure", etc.) to avoid unnecessary Loop B routing when the
docs already make the comparison the question asks about.
"""

import os
import json
import re
import time
from dotenv import load_dotenv
from anthropic import Anthropic
import yaml

load_dotenv()

# Fallback model when primary hits rate limits
FALLBACK_MODEL = "claude-sonnet-4-6"

# Platforms we can research externally
KNOWN_PLATFORMS = [
    "databricks", "snowflake", "aws", "amazon", "azure", "microsoft",
    "google cloud", "gcp", "bigquery", "redshift", "synapse",
    "confluent", "cloudera", "palantir", "oracle", "ibm",
]

# Phrases in DDC docs that indicate category-level comparison against
# traditional/centralized cloud stacks (i.e., the category Databricks,
# Snowflake, AWS, Azure belong to)
CATEGORY_COMPARISON_PHRASES = [
    "traditional cloud",
    "centralized cloud",
    "provider infrastructure",
    "provider's infrastructure",
    "traditional stack",
    "typical stack",
    "cloud provider",
    "trust the provider",
    "trust a provider",
    "aws equivalent",
    "s3, cloudfront",
    "unlike centralized",
    "unlike traditional",
    "compared to centralized",
    "single custodian",
    "custodial model",
    "shared responsibility model",
]

SYSTEM_PROMPT = """You are a routing agent. Your job is to classify a question into one of two processing loops:

LOOP A (closed-book):
- Question can be fully answered from internal DDC documentation alone
- No comparison to external platforms is needed
- Question asks about DDC mechanisms, architecture, or features in isolation
- The internal docs already make category-level comparisons against "traditional cloud stacks" / "centralized cloud" — and the named platforms belong to that category

LOOP B (research-augmented comparison):
- Question compares DDC against external platforms AND the internal docs do NOT contain sufficient category-level contrasts to address the comparison
- External platform-SPECIFIC technical details (exact encryption algorithms, specific API methods, audit reports) are genuinely needed to answer well
- Question asks about industry-standard benchmarks or compliance that DDC docs don't cover

IMPORTANT: If the internal docs already contrast DDC against "traditional cloud stacks", "centralized cloud", or "provider infrastructure", and the question asks about platforms that ARE traditional cloud stacks (Databricks, Snowflake, AWS, Azure), then the docs ALREADY provide the comparison. Route to Loop A unless platform-specific internals are truly needed.

Respond with ONLY this JSON:
{
  "loop": "A" or "B",
  "reason": "<1 sentence explaining why>",
  "comparison_targets": ["<platform names to research, if Loop B>"],
  "research_topics": ["<specific technical topics to research externally, if Loop B>"]
}"""

SYSTEM_PROMPT_TIER1 = """You are a routing agent. The answer agent is operating in FULL-CONTEXT mode — it has the COMPLETE text of all source documents in its context window. This means it can find and use ANY information in the documents, including category-level comparisons.

Your job is to classify a question into one of two processing loops:

LOOP A (closed-book — PREFERRED for full-context mode):
- Question can be answered from the documents alone
- The documents make category-level comparisons (e.g., DDC vs "traditional cloud stacks") that apply to the named platforms
- The answer agent already has complete access to all relevant text

LOOP B (research-augmented — use ONLY when genuinely needed):
- The question requires platform-SPECIFIC technical details that the DDC documents cannot possibly contain (e.g., "What exact encryption algorithm does Snowflake use for data at rest?")
- External audit reports or compliance certifications are needed
- General category-level comparison is NOT sufficient to answer well

BIAS: In full-context mode, strongly prefer Loop A. The answer agent has complete documents and can make category-level comparisons itself. Only choose Loop B if external platform-specific facts would materially improve the answer beyond what category-level reasoning provides.

Respond with ONLY this JSON:
{
  "loop": "A" or "B",
  "reason": "<1 sentence explaining why>",
  "comparison_targets": ["<platform names to research, if Loop B>"],
  "research_topics": ["<specific technical topics to research externally, if Loop B>"]
}"""


def detect_platforms(text: str) -> list[str]:
    """Quick heuristic: find platform names mentioned in a question."""
    text_lower = text.lower()
    found = []
    for platform in KNOWN_PLATFORMS:
        if platform in text_lower:
            found.append(platform)
    return list(set(found))


def check_internal_comparison(evidence_chunks: list[dict],
                               max_chunks: int = 0) -> dict:
    """
    Scan evidence chunks for category-comparison phrases that indicate
    the DDC docs already make comparisons against traditional cloud stacks.

    Args:
        evidence_chunks: All available evidence (or a representative sample)
        max_chunks: If > 0, only scan this many chunks (0 = scan all)

    Returns:
        {
            "has_comparison": bool,
            "phrases_found": list[str],
            "example_chunks": list[str],  # chunk_ids with comparison language
        }
    """
    chunks_to_scan = evidence_chunks
    if max_chunks > 0:
        chunks_to_scan = evidence_chunks[:max_chunks]

    phrases_found = []
    example_chunks = []

    for chunk in chunks_to_scan:
        text_lower = chunk.get("text", "").lower()
        for phrase in CATEGORY_COMPARISON_PHRASES:
            if phrase in text_lower:
                if phrase not in phrases_found:
                    phrases_found.append(phrase)
                chunk_id = chunk.get("chunk_id", "unknown")
                if chunk_id not in example_chunks:
                    example_chunks.append(chunk_id)

    return {
        "has_comparison": len(phrases_found) > 0,
        "phrases_found": phrases_found,
        "example_chunks": example_chunks[:5],  # Cap at 5 examples
    }


def build_smart_evidence_summary(question_text: str,
                                  evidence_chunks: list[dict],
                                  max_summary_chars: int = 4000) -> str:
    """
    Build an evidence summary for the router that includes:
    1. Chunks containing category-comparison phrases (highest priority)
    2. Chunks containing platform-related keywords
    3. First N chunks as general context

    This ensures the router sees the comparison language even if it's
    buried deep in the document set.
    """
    question_lower = question_text.lower()

    # Bucket 1: chunks with category-comparison phrases
    comparison_chunks = []
    # Bucket 2: chunks mentioning platforms or security/trust
    relevant_chunks = []
    # Bucket 3: everything else
    other_chunks = []

    security_keywords = [
        "security", "encryption", "key management", "trust",
        "access control", "custody", "ownership", "decentralize",
    ]

    for chunk in evidence_chunks:
        text_lower = chunk.get("text", "").lower()

        has_comparison = any(p in text_lower for p in CATEGORY_COMPARISON_PHRASES)
        has_relevance = any(k in text_lower for k in security_keywords)

        if has_comparison:
            comparison_chunks.append(chunk)
        elif has_relevance:
            relevant_chunks.append(chunk)
        else:
            other_chunks.append(chunk)

    # Build summary: prioritize comparison chunks, then relevant, then general
    summary_parts = []
    char_budget = max_summary_chars

    for label, bucket in [
        ("COMPARISON", comparison_chunks),
        ("RELEVANT", relevant_chunks),
        ("CONTEXT", other_chunks),
    ]:
        for chunk in bucket:
            if char_budget <= 0:
                break
            snippet = chunk["text"][:400]
            entry = f"[{chunk['chunk_id']}] ({label}): {snippet}...\n"
            summary_parts.append(entry)
            char_budget -= len(entry)

    return "".join(summary_parts)


def route_question(question_id: str, question_text: str,
                   question_spec: dict = None,
                   evidence_summary: str = "",
                   config_path: str = "config/pipeline_config.yaml",
                   tier: int = 2,
                   evidence_chunks: list[dict] = None) -> dict:
    """
    Decide whether a question should go through Loop A or Loop B.

    Args:
        question_id: e.g. "Q1", "Q2", "Q3"
        question_text: The question
        question_spec: Evaluation rubric for this question
        evidence_summary: Pre-built evidence summary string (Tier 2 fallback)
        config_path: Pipeline config path
        tier: 1 (full-context) or 2 (RAG) — affects routing bias
        evidence_chunks: Full evidence list (for smart sampling)

    Returns:
        {
            "loop": "A" or "B",
            "reason": str,
            "comparison_targets": list[str],
            "research_topics": list[str],
            "internal_comparison_available": bool,
        }
    """
    with open(config_path) as f:
        config = yaml.safe_load(f)

    # Detect platforms in question/rubric
    platforms_in_question = detect_platforms(question_text)
    rubric_text = ""
    if question_spec:
        rubric_text = json.dumps(question_spec, indent=2)
        platforms_in_rubric = detect_platforms(rubric_text)
        platforms_in_question = list(set(platforms_in_question + platforms_in_rubric))

    # Check for comparison language in the question
    comparison_keywords = [
        "compared to", "versus", "vs", "better than", "higher level",
        "relative to", "unlike", "competitor", "alternative",
        "typical stack", "existing solutions", "industry",
    ]
    has_comparison_language = any(kw in question_text.lower() for kw in comparison_keywords)

    # ── Fast path: no platforms, no comparison language → Loop A ──
    if not platforms_in_question and not has_comparison_language:
        return {
            "loop": "A",
            "reason": (f"Question {question_id} asks about DDC in isolation — "
                      f"no external comparison needed."),
            "comparison_targets": [],
            "research_topics": [],
            "internal_comparison_available": False,
        }

    # ── Check if internal docs already make category-level comparisons ──
    internal_comparison = {"has_comparison": False, "phrases_found": []}
    if evidence_chunks:
        internal_comparison = check_internal_comparison(evidence_chunks)

    # ── Build smart evidence summary if we have chunks ──
    if evidence_chunks and not evidence_summary:
        evidence_summary = build_smart_evidence_summary(
            question_text, evidence_chunks)

    # ── Tier 1 + internal comparison available → strong bias to Loop A ──
    if (tier == 1 and internal_comparison["has_comparison"]
            and platforms_in_question):
        # The docs already contrast against the category these platforms belong to,
        # AND the answer agent has full text. Loop A is sufficient.
        platform_names = ", ".join(p.title() for p in platforms_in_question)
        phrases = ", ".join(f'"{p}"' for p in internal_comparison["phrases_found"][:3])
        return {
            "loop": "A",
            "reason": (f"Tier 1 full-context mode: DDC docs contain category-level "
                      f"comparisons ({phrases}) that apply to {platform_names}. "
                      f"Answer agent has complete text and can make the comparison."),
            "comparison_targets": [],
            "research_topics": [],
            "internal_comparison_available": True,
        }

    # ── Tier 2 + internal comparison available → still bias to Loop A ──
    if internal_comparison["has_comparison"] and platforms_in_question:
        # Even in Tier 2, if the retrieved chunks contain comparison language,
        # we should prefer Loop A unless the LLM disagrees
        pass  # Let the LLM make the call with this context

    # ── For borderline cases, use Claude to decide ──
    router_config = config.get("models", {}).get("router", config["models"]["answerer"])
    router_provider = router_config.get("provider", "anthropic")

    if router_provider == "kimi":
        from openai import OpenAI as _OpenAI
        kimi_key = os.environ.get(router_config.get("api_key_env", "KIMI_API_KEY"))
        if not kimi_key:
            print("  ⚠ KIMI_API_KEY not set, falling back to Anthropic router")
            router_provider = "anthropic"
        else:
            kimi_client = _OpenAI(
                api_key=kimi_key,
                base_url=router_config.get("base_url", "https://api.moonshot.ai/v1"),
                timeout=60.0
            )

    if router_provider != "kimi":
        client = Anthropic(api_key=os.environ.get("ANTHROPIC_API_KEY"))

    # Select system prompt based on tier
    system_prompt = SYSTEM_PROMPT_TIER1 if tier == 1 else SYSTEM_PROMPT

    # Build comparison context for the LLM
    comparison_context = ""
    if internal_comparison["has_comparison"]:
        comparison_context = (
            f"\n\nINTERNAL COMPARISON DETECTED: The DDC documents contain "
            f"category-level comparison phrases: "
            f"{', '.join(f'«{p}»' for p in internal_comparison['phrases_found'][:5])}. "
            f"These contrasts apply to the platforms mentioned in the question "
            f"({', '.join(platforms_in_question)}) since they are traditional "
            f"cloud stacks."
        )

    tier_context = ""
    if tier == 1:
        tier_context = (
            "\n\nTIER INFO: The answer agent is in FULL-CONTEXT mode — it has "
            "the COMPLETE text of all documents. It will see every comparison "
            "the docs make, not just retrieved chunks."
        )

    user_prompt = f"""QUESTION ({question_id}):
{question_text}

EVALUATION RUBRIC CONTEXT:
{rubric_text}

PLATFORMS DETECTED IN QUESTION/RUBRIC: {platforms_in_question or "None explicitly named"}
{comparison_context}
{tier_context}

EVIDENCE PREVIEW (what our internal docs cover):
{evidence_summary[:2000] if evidence_summary else "Not yet retrieved."}

Classify this question as Loop A or Loop B."""

    # Call with retry + fallback
    last_error = None
    response_text = None
    for attempt in range(3):
        try:
            if router_provider == "kimi":
                kimi_response = kimi_client.chat.completions.create(
                    model=router_config["model"],
                    max_tokens=500,
                    temperature=0.6,
                    messages=[
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": user_prompt}
                    ],
                    extra_body={"thinking": {"type": "disabled"}}
                )
                response_text = kimi_response.choices[0].message.content
                _router_usage = {"input_tokens": getattr(kimi_response.usage, 'prompt_tokens', 0),
                                 "output_tokens": getattr(kimi_response.usage, 'completion_tokens', 0)}
                try:
                    from agents.cost_tracker import track_cost
                    track_cost("router", question_id, router_config["model"],
                               _router_usage["input_tokens"], _router_usage["output_tokens"])
                except ImportError:
                    pass
            else:
                current_model = router_config["model"] if attempt < 2 else FALLBACK_MODEL
                response = client.messages.create(
                    model=current_model,
                    max_tokens=500,
                    system=system_prompt,
                    messages=[{"role": "user", "content": user_prompt}]
                )
                response_text = response.content[0].text
                _router_usage = {"input_tokens": getattr(response.usage, 'input_tokens', 0),
                                 "output_tokens": getattr(response.usage, 'output_tokens', 0)}
                try:
                    from agents.cost_tracker import track_cost
                    track_cost("router", question_id, current_model,
                               _router_usage["input_tokens"], _router_usage["output_tokens"])
                except ImportError:
                    pass
            break
        except Exception as e:
            last_error = e
            if "429" in str(e) or "rate_limit" in str(e).lower():
                wait = 30 * (2 ** attempt)
                next_model = router_config["model"] if attempt < 1 else FALLBACK_MODEL
                print(f"  ⚠ Router rate limited on {current_model}. "
                      f"Waiting {wait}s then trying {next_model}...")
                time.sleep(wait)
            else:
                raise
    else:
        raise last_error

    try:
        json_match = re.search(r'\{.*\}', response_text, re.DOTALL)
        if json_match:
            result = json.loads(json_match.group())
        else:
            result = json.loads(response_text)
    except json.JSONDecodeError:
        if platforms_in_question or has_comparison_language:
            # If internal comparison available AND tier 1, default to A
            if internal_comparison["has_comparison"] and tier == 1:
                result = {
                    "loop": "A",
                    "reason": ("Internal docs have category-level comparisons; "
                              "full-context mode (router parse failed)."),
                    "comparison_targets": [],
                    "research_topics": [],
                }
            else:
                result = {
                    "loop": "B",
                    "reason": "Platforms or comparison language detected (router parse failed).",
                    "comparison_targets": platforms_in_question,
                    "research_topics": [],
                }
        else:
            result = {
                "loop": "A",
                "reason": "No comparison signals detected (router parse failed).",
                "comparison_targets": [],
                "research_topics": [],
            }

    # Ensure comparison_targets includes detected platforms if Loop B
    if result.get("loop") == "B":
        existing_targets = [t.lower() for t in result.get("comparison_targets", [])]
        for p in platforms_in_question:
            if p not in existing_targets:
                result.setdefault("comparison_targets", []).append(p)

    result["internal_comparison_available"] = internal_comparison["has_comparison"]
    result["token_usage"] = _router_usage if '_router_usage' in dir() else {}

    return result


if __name__ == "__main__":
    print("--- Q1 (should be Loop A) ---")
    r1 = route_question("Q1",
        "Why does the highly peer-to-peer design of the DDC clusters ensure resilience?",
        tier=1)
    print(json.dumps(r1, indent=2))

    print("\n--- Q2 Tier 1 (should be Loop A with internal comparison) ---")
    r2 = route_question("Q2",
        "How can a DDC cluster provide a higher level of security compared to "
        "a typical stack from Databricks or Snowflake running on top of AWS/Azure?",
        tier=1,
        evidence_chunks=[{
            "chunk_id": "test-001",
            "text": "Where traditional cloud stacks require you to trust the provider's "
                    "infrastructure, DDC ensures data sovereignty through client-side encryption.",
            "pdf_file": "test.pdf",
            "page_start": 1,
        }])
    print(json.dumps(r2, indent=2))

    print("\n--- Q2 Tier 2 (may be Loop B without comparison chunks) ---")
    r3 = route_question("Q2",
        "How can a DDC cluster provide a higher level of security compared to "
        "a typical stack from Databricks or Snowflake running on top of AWS/Azure?",
        tier=2)
    print(json.dumps(r3, indent=2))
