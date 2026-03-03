"""
Answer Agent (Dual-Mode: Full-Context or Closed-Book)
=====================================================

Two modes based on ingestion tier:

  Tier 1 (full_text provided):
    → Receives the COMPLETE document corpus as a single text block
    → Cites by document name + page (e.g., [[doc:DDC_Core_Wiki.pdf, p.12]])
    → No retrieval loss — sees everything

  Tier 2 (evidence_chunks only):
    → Receives top-K retrieved chunks from vector search
    → Cites by chunk ID (e.g., [[chunk:DDC_Core_Wiki-p012-0045]])
    → Traditional closed-book RAG mode

Uses Claude (Anthropic) for conservative, citation-heavy responses.
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
MAX_RETRIES = 3
INITIAL_BACKOFF = 30  # seconds


def _call_anthropic_with_fallback(client, model, max_tokens, system, messages,
                                   retries=MAX_RETRIES):
    """
    Call Anthropic API with retry + automatic model fallback.

    Strategy:
      1. Try the requested model (e.g. Opus 4.6)
      2. On rate limit (429): wait with exponential backoff, retry once
      3. If still rate-limited: fall back to FALLBACK_MODEL (Sonnet 4.6)
      4. On other errors: raise immediately

    Returns (response, model_actually_used)
    """
    last_error = None

    for attempt in range(retries):
        current_model = model if attempt < 2 else FALLBACK_MODEL
        try:
            response = client.messages.create(
                model=current_model,
                max_tokens=max_tokens,
                system=system,
                messages=messages,
            )
            return response, current_model
        except Exception as e:
            error_str = str(e)
            last_error = e

            # Check if it's a rate limit error
            if "429" in error_str or "rate_limit" in error_str.lower():
                if attempt < retries - 1:
                    wait = INITIAL_BACKOFF * (2 ** attempt)
                    next_model = model if attempt < 1 else FALLBACK_MODEL
                    print(f"  ⚠ Rate limited on {current_model}. "
                          f"Waiting {wait}s then trying {next_model}...")
                    time.sleep(wait)
                else:
                    raise
            else:
                raise

    raise last_error


# ============================================================
# System prompts — one per tier
# ============================================================

SYSTEM_PROMPT_TIER1 = """You are AnswerAgent in FULL-CONTEXT mode. You have the COMPLETE text of all source documents. Your job is to produce answers with PERFECT SOURCE FIDELITY — every claim must be directly stated in the documents.

YOUR PURPOSE: You are part of a documentation improvement pipeline. Your answers will be evaluated against a strict rubric, and any claim you make that goes beyond what the docs literally state will be flagged as an overclaim. This is BY DESIGN — the pipeline uses these flags to identify gaps in the source documentation that need to be fixed.

CONCISENESS RULES (CRITICAL):
- Your answer should contain 40-55 verifiable claims — this is the sweet spot for completeness without overclaiming.
- HARD UPPER BOUND: If you are generating more than 55 claims, you are overclaiming. Stop and consolidate.
- Prefer FEWER claims with STRONG citations over MANY claims with weak support.
- Each claim should be a direct statement from the docs, not a paraphrase or inference.
- Aim for at least 1 citation per 2 sentences to maintain citation density.
- QUOTE or closely paraphrase the source text. Do NOT restate the same idea in your own words.
- Do NOT repeat the same concept in different sections with different wording.

PRECISION AND RELEVANCE (CRITICAL):
- Every section and claim in your answer must DIRECTLY address the specific question asked.
- Before including a claim, ask: "Does this help answer the SPECIFIC question, or is it tangentially related background?" If tangential, omit it.
- Do NOT pad the answer with adjacent topics the docs happen to cover. For example:
  - If asked about resilience: focus on fault tolerance, recovery, redundancy. Do NOT add sections on encryption status or platform comparisons unless the question specifically asks for them.
  - If asked about security: focus on encryption, access control, audit. Do NOT add sections on erasure coding fault tolerance unless it directly relates to the security argument.
  - If asked about data wallets: focus on account creation, key management, SDK usage. Do NOT add sections on cluster architecture unless directly relevant.
- The DOC_GAPS section is exempt from this rule — gaps may reference related topics.
- HARD RULE: If a section heading would not naturally appear as a subsection of the question itself, it probably does not belong in the answer.

HEDGING AND FRAMING:
- Do NOT prefix every sentence with "The documents suggest" — this inflates your claim count.
- Instead, make direct statements with citations: "DDC uses erasure coding [[doc:X, p.4]]"
- Use "the documents suggest" ONLY when the source is genuinely ambiguous or indirect.
- HARD LIMIT: "The documents suggest" may appear NO MORE THAN 5 TIMES in your entire answer.
- Preferred patterns:
  - GOOD: "DDC uses erasure coding to distribute data [[doc:X, p.4]]"
  - GOOD: "The Data Redundancy Strategy describes a 16/48 scheme [[doc:X, p.1]]"
  - BAD: "The documents suggest that DDC uses erasure coding to distribute data"
  - BAD: "The documents suggest that the documents suggest that..."

ABSOLUTE RULES:
1. Every technical claim must cite its source as [[doc:FILENAME, p.PAGE_NUM]]
2. ZERO INFERENCE: If the documents don't literally state something, DO NOT STATE IT. Instead, put it in the DOC_GAPS section.
   - BAD: "This means there is no centralized coordinator" (if the doc doesn't use those words)
   - GOOD: "Nodes can use themselves as bootstrap nodes [[doc:X, p.5]], and discover peers through DHT [[doc:X, p.5]]"
   - Then in DOC_GAPS: "The documents do not explicitly state whether a centralized coordinator exists or not. The P2P bootstrap behavior implies coordinator-free operation, but this should be stated explicitly."
3. Use the EXACT terminology from the documents. Do not rephrase technical concepts into your own words.
4. If the documents do not cover a topic the question asks about, say: "The provided documents do not address this."
5. Do NOT use phrases like "typically", "generally", "in most systems", "fundamentally" — these indicate outside knowledge.
6. Explain MECHANISMS (how/why things work), not marketing claims.
7. When a required concept is implied but not explicitly stated, DO NOT state it as fact. Instead, note it as a doc gap.
8. CITATION DENSITY: At least 1 citation per paragraph, aim for 1 per 2 claims.
9. Do NOT cite pages that don't exist in the original documents. Only cite page numbers you can see in the document headers/markers.

PLATFORM COMPARISON RULES:
When asked to compare DDC with platforms like Databricks, Snowflake, AWS, or Azure:
- You MAY apply documented contrasts between DDC and "traditional cloud stacks" to named platforms, ONLY because those platforms are instances of the documented category.
- Frame as: "The DDC documents contrast their architecture with traditional cloud stacks [[doc:X, p.Y]]. Platforms like Databricks and Snowflake running on AWS/Azure fall into this category."
- You MUST NOT state any fact about what Databricks/Snowflake/AWS/Azure specifically do unless it appears in the DDC documents. If a comparison requires knowledge of the external platform's internals, put it in DOC_GAPS.
- CRITICAL: Do NOT make claims like "In AWS S3, encryption is managed by..." or "Snowflake retains visibility over..." — these are claims about external platforms that the DDC documents cannot support. State ONLY what DDC does differently from the generic "traditional cloud stacks" category.
- NEVER cite a DDC document page as evidence for a claim about what AWS/Databricks/Snowflake does. The DDC docs describe DDC, not other platforms.

ROADMAP AWARENESS:
- Content with "Definition of done:", "Plan:", "Milestone X", "TODO", "in development" describes PLANNED capabilities.
- Label these: "As a planned capability..." — never present as current.

BLOCKCHAIN NUANCE:
- If the docs say nodes "can function when blockchain is unavailable" due to disk-persisted indexes, state exactly that.
- Do NOT extend this to "eliminates blockchain dependency" or "no centralized coordinator" unless the docs use those words.
- NEVER say "DDC operates without a centralized coordinator" — the docs never state this. Put it in DOC_GAPS instead.

KEY LOSS:
- If the question involves security/key management, address key loss.
- If docs don't cover key loss/recovery, state: "The provided documents do not describe a key recovery mechanism."

WALLET / KEY TYPE:
- The CLI outputs key type "sr25519", NOT "Ed25519". Do NOT claim the wallet uses Ed25519 unless you can cite a document page that says Ed25519.
- The term "data wallet" is NOT formally defined in the docs. Do NOT state "your data wallet IS an X keypair" as fact. Instead, describe what the docs say about account creation and note in DOC_GAPS that "data wallet" is not defined.
- NEVER say "Ed25519 keypair" unless you are quoting a specific document passage. If the CLI output says sr25519, say sr25519.

AUDIT / VERIFICATION:
- The docs say DAC is a "verified data source" — do NOT embellish to "cryptographically verified audit trail" unless those exact words appear in the docs.
- Do NOT say "every operation is auditable" unless the docs literally say that about ALL operations.
- When discussing DAC, explicitly describe it as the "trust layer that captures real-time traffic and compute metrics" — this is a required concept for security questions.

ENCRYPTION CURRENT STATUS (CRITICAL FOR SECURITY QUESTIONS):
- The Encrypted Data Access ADR states current status is "Plaintext" — data is stored and transmitted in plaintext by default.
- Client-side encryption is "available manually" but NOT the default.
- SDK-integrated key management is "in development" — do NOT present encryption as a current default capability.
- When discussing DDC security, you MUST state the current plaintext limitation clearly. Do not imply encryption is active by default.
- BAD: "DDC applies client-side encryption by default"
- GOOD: "Client-side encryption is available manually but data is stored in plaintext by default [[doc:X, p.Y]]. SDK-integrated key management is in development."

ANSWER STRUCTURE:
1. Direct Answer (1-2 sentences, every word traceable to docs)
2. Detailed Explanation (mechanism-level, with citations throughout — use source wording)
3. Planned/Roadmap Items (clearly separated, if relevant)
4. What the Documents Do NOT Cover (topics the question asks about that the docs don't address)
5. DOC_GAPS — Documentation Improvement Recommendations (NEW — CRITICAL)
   List specific things the documents SHOULD state but currently don't, formatted as:
   - GAP: <what's missing>
   - IMPLICATION: <what the docs seem to imply but don't explicitly state>
   - RECOMMENDATION: <what text should be added to which document>
   This section is the most valuable output of your answer — it directly drives documentation improvements.
6. Citations Summary"""


SYSTEM_PROMPT_TIER2 = """You are AnswerAgent in CLOSED-BOOK mode. You answer questions STRICTLY using the provided evidence chunks. Your job is PERFECT SOURCE FIDELITY — every claim must be directly stated in the evidence.

YOUR PURPOSE: You are part of a documentation improvement pipeline. Your answers will be evaluated against a strict rubric, and any claim beyond what the evidence literally states will be flagged. This is BY DESIGN — flags identify documentation gaps that need fixing.

ABSOLUTE RULES:
1. Every technical claim must cite a chunk ID as [[chunk:CHUNK_ID]]
2. ZERO INFERENCE: If the evidence doesn't literally state something, DO NOT STATE IT. Put it in DOC_GAPS instead.
3. Use the EXACT terminology from the evidence. Do not rephrase technical concepts.
4. If the evidence does not cover a topic, say: "The provided documents do not address this."
5. Do NOT use phrases like "typically", "generally", "fundamentally" — outside knowledge indicators.
6. Explain MECHANISMS, not marketing claims.
7. CITATION DENSITY: At least 1 citation per paragraph, aim for 1 per 2 claims.
8. Do NOT cite TERMINOLOGY_MAP — it is not a document source.

PRECISION AND RELEVANCE (CRITICAL):
- Every section and claim must DIRECTLY address the specific question asked.
- Before including a claim, ask: "Does this help answer the SPECIFIC question, or is it tangentially related background?" If tangential, omit it.
- Do NOT pad the answer with adjacent topics. Only include content that a reader would expect to find under the question heading.
- The DOC_GAPS section is exempt — gaps may reference related topics.
- HARD RULE: If a section heading would not naturally appear as a subsection of the question itself, it probably does not belong in the answer.

PLATFORM COMPARISON RULES:
- You MAY apply documented "traditional cloud stacks" contrasts to Databricks/Snowflake/AWS/Azure.
- You MUST NOT state facts about external platform internals unless in the evidence.
- Missing external platform details go in DOC_GAPS.

ROADMAP AWARENESS:
- Planned capabilities must be labeled: "As a planned capability..."

BLOCKCHAIN NUANCE:
- State exactly what the docs say about blockchain dependency. Do not extend or infer.

KEY LOSS:
- Address key loss if relevant. If docs don't cover it, state that explicitly.

ANSWER STRUCTURE:
1. Direct Answer (1-2 sentences, every word traceable to evidence)
2. Detailed Explanation (mechanism-level, source wording, citations throughout)
3. Planned/Roadmap Items (clearly separated)
4. What the Documents Do NOT Cover
5. DOC_GAPS — Documentation Improvement Recommendations
   - GAP: <what's missing>
   - IMPLICATION: <what the docs imply but don't state>
   - RECOMMENDATION: <what to add to which document>
6. Citations Summary (do NOT include TERMINOLOGY_MAP)"""


# ============================================================
# Answer generation
# ============================================================

def answer_question(question_id: str, question_text: str,
                    evidence_chunks: list[dict],
                    full_text: str = "",
                    terminology_context: str = "",
                    config_path: str = "config/pipeline_config.yaml") -> dict:
    """
    Generate an answer using either full document text (Tier 1) or
    retrieved evidence chunks (Tier 2).

    Args:
        question_id: Question identifier (Q1, Q2, Q3)
        question_text: The question text
        evidence_chunks: List of evidence chunk dicts (Tier 2, or pseudo-chunks for Tier 1)
        full_text: Complete document text (Tier 1 only — if provided, overrides evidence_chunks)
        terminology_context: Optional terminology mapping text
        config_path: Path to pipeline config
    """
    with open(config_path) as f:
        config = yaml.safe_load(f)

    model_config = config["models"]["answerer"]

    # Determine mode
    use_full_text = bool(full_text and len(full_text) > 0)

    if use_full_text:
        return _answer_tier1(question_id, question_text, full_text,
                             evidence_chunks, terminology_context, model_config)
    else:
        return _answer_tier2(question_id, question_text, evidence_chunks,
                             terminology_context, model_config)


def _answer_tier1(question_id, question_text, full_text,
                  pseudo_chunks, terminology_context, model_config):
    """Tier 1: Answer with full document text in context."""

    terminology_section = ""
    if terminology_context:
        terminology_section = f"""

TERMINOLOGY REFERENCE (for understanding only — do NOT cite as a source):
{terminology_context}
"""

    user_prompt = f"""QUESTION ({question_id}):
{question_text}

COMPLETE DOCUMENT TEXT (cite as [[doc:FILENAME, p.PAGE_NUM]]):
{full_text}
{terminology_section}
Now answer the question using ONLY the documents above.
Follow the answer structure specified in your instructions.
Remember: at least 1 citation per paragraph, aim for 1 citation per 2 claims.
If the question involves comparison with named platforms (Databricks, Snowflake, AWS, Azure), remember these are "traditional cloud stacks" — apply the contrasts the documents make against that category.
Stay close to the source text when making claims.
IMPORTANT: Keep your answer thorough but focused — aim for 40-55 verifiable claims with strong citations (NEVER exceed 55). Every paragraph should have at least one citation. Prefer quoting source text directly over paraphrasing. Each claim must cite a real page number visible in the documents above."""

    client = Anthropic(api_key=os.environ.get("ANTHROPIC_API_KEY"))
    response, model_used = _call_anthropic_with_fallback(
        client,
        model=model_config["model"],
        max_tokens=model_config["max_tokens"],
        system=SYSTEM_PROMPT_TIER1,
        messages=[{"role": "user", "content": user_prompt}],
    )

    answer_text = response.content[0].text
    if model_used != model_config["model"]:
        print(f"  ℹ Fell back to {model_used} (primary model rate-limited)")

    # Extract cited documents/pages
    doc_citations = re.findall(r'\[\[doc:([^,\]]+)(?:,\s*p\.?(\d+))?\]\]', answer_text)
    cited_docs = list(set(c[0] for c in doc_citations))

    # Map doc citations back to pseudo-chunk IDs for evaluator compatibility
    cited_chunks = []
    for doc_name, page_num in doc_citations:
        if page_num:
            chunk_id = f"{doc_name.replace('.pdf','')}-p{int(page_num):03d}"
            if chunk_id not in cited_chunks:
                cited_chunks.append(chunk_id)
        else:
            # Find first chunk for this doc
            for pc in pseudo_chunks:
                if pc["pdf_file"] == doc_name and pc["chunk_id"] not in cited_chunks:
                    cited_chunks.append(pc["chunk_id"])
                    break

    # Run post-processing checks
    warnings = _post_process_checks(question_id, answer_text)

    # Extract DOC_GAPS section from the answer for the editor agent
    doc_gaps = _extract_doc_gaps(answer_text)

    return {
        "question_id": question_id,
        "question_text": question_text,
        "answer_markdown": answer_text,
        "cited_chunks": cited_chunks,
        "cited_documents": cited_docs,
        "evidence_chunks_provided": len(pseudo_chunks),
        "evidence_chunks_cited": len(cited_chunks),
        "tier": 1,
        "doc_gaps": doc_gaps,
        "warnings": warnings,
        "model_used": model_used,
        "token_usage": {
            "input_tokens": response.usage.input_tokens,
            "output_tokens": response.usage.output_tokens
        }
    }

    try:
        from agents.cost_tracker import track_cost
        track_cost("answerer", question_id, model_used,
                   response.usage.input_tokens, response.usage.output_tokens)
    except ImportError:
        pass

    return result


def _answer_tier2(question_id, question_text, evidence_chunks,
                  terminology_context, model_config):
    """Tier 2: Answer with retrieved evidence chunks (original RAG mode)."""

    # Format evidence — exclude any TERMINOLOGY_MAP chunks
    evidence_text = ""
    real_chunks = []
    for chunk in evidence_chunks:
        if chunk.get("chunk_id") == "TERMINOLOGY_MAP":
            if not terminology_context:
                terminology_context = chunk["text"]
            continue
        evidence_text += (
            f"\n--- CHUNK: {chunk['chunk_id']} "
            f"(Source: {chunk['pdf_file']}, Page {chunk['page_start']}) ---\n"
            f"{chunk['text']}\n"
        )
        real_chunks.append(chunk)

    terminology_section = ""
    if terminology_context:
        terminology_section = f"""

TERMINOLOGY REFERENCE (for understanding only — do NOT cite as [[chunk:TERMINOLOGY_MAP]]):
{terminology_context}
"""

    user_prompt = f"""QUESTION ({question_id}):
{question_text}

EVIDENCE CHUNKS (these are your ONLY citable sources — cite as [[chunk:CHUNK_ID]]):
{evidence_text}
{terminology_section}
Now answer the question using ONLY the evidence chunks above.
Follow the answer structure specified in your instructions.
Remember: no citations = no claim. If evidence is insufficient, say so explicitly.
Remember: at least 1 citation per paragraph, aim for 1 citation per 2 claims.
Remember: do NOT cite TERMINOLOGY_MAP — only cite real chunk IDs.
If the question involves comparison with named platforms (Databricks, Snowflake, AWS, Azure), remember these are "traditional cloud stacks" — apply the contrasts the DDC docs make against that category.
Stay close to the source text when making claims — do not editorialize or add implications not present in the evidence."""

    client = Anthropic(api_key=os.environ.get("ANTHROPIC_API_KEY"))
    response, model_used = _call_anthropic_with_fallback(
        client,
        model=model_config["model"],
        max_tokens=model_config["max_tokens"],
        system=SYSTEM_PROMPT_TIER2,
        messages=[{"role": "user", "content": user_prompt}],
    )

    answer_text = response.content[0].text
    if model_used != model_config["model"]:
        print(f"  ℹ Fell back to {model_used} (primary model rate-limited)")

    # Extract cited chunk IDs
    cited_chunks = list(set(re.findall(r'\[\[chunk:([^\]]+)\]\]', answer_text)))

    # Post-processing: strip TERMINOLOGY_MAP citations
    if "TERMINOLOGY_MAP" in cited_chunks:
        cited_chunks.remove("TERMINOLOGY_MAP")
    answer_text = answer_text.replace("[[chunk:TERMINOLOGY_MAP]]", "")
    answer_text = re.sub(r'  +', ' ', answer_text)

    warnings = _post_process_checks(question_id, answer_text)
    doc_gaps = _extract_doc_gaps(answer_text)

    return {
        "question_id": question_id,
        "question_text": question_text,
        "answer_markdown": answer_text,
        "cited_chunks": cited_chunks,
        "evidence_chunks_provided": len(real_chunks),
        "evidence_chunks_cited": len(cited_chunks),
        "tier": 2,
        "doc_gaps": doc_gaps,
        "warnings": warnings,
        "model_used": model_used,
        "token_usage": {
            "input_tokens": response.usage.input_tokens,
            "output_tokens": response.usage.output_tokens
        }
    }

    try:
        from agents.cost_tracker import track_cost
        track_cost("answerer", question_id, model_used,
                   response.usage.input_tokens, response.usage.output_tokens)
    except ImportError:
        pass

    return result


# ============================================================
# Doc gap extraction (feeds the editor agent)
# ============================================================

def _extract_doc_gaps(answer_text: str) -> list[dict]:
    """
    Extract the DOC_GAPS section from the answer for the editor agent.
    Parses GAP/IMPLICATION/RECOMMENDATION triplets.
    Handles both plain and bold-markdown formats:
      - GAP: ...
      - **GAP**: ...
      - **GAP:** ...
    """
    gaps = []

    # Find DOC_GAPS section
    doc_gaps_match = re.search(
        r'(?:DOC_GAPS|Documentation Improvement Recommendations?).*?\n(.*?)(?:\n##|\n\*\*Citations|\Z)',
        answer_text, re.DOTALL | re.IGNORECASE
    )
    if not doc_gaps_match:
        return gaps

    gaps_text = doc_gaps_match.group(1)

    def _strip_label(line: str, label: str) -> str:
        """Strip a label (with optional bold markdown) from the start of a line."""
        # Match patterns: "GAP:", "**GAP**:", "**GAP:**", "**GAP**:"
        pattern = rf'^\*?\*?\s*{label}\s*\*?\*?\s*:\s*'
        m = re.match(pattern, line, re.IGNORECASE)
        if m:
            return line[m.end():].strip()
        return None

    # Parse individual gaps
    current_gap = {}
    for line in gaps_text.split('\n'):
        line = line.strip().lstrip('- ')
        if not line:
            if current_gap:
                gaps.append(current_gap)
                current_gap = {}
            continue

        gap_val = _strip_label(line, 'GAP')
        if gap_val is not None:
            if current_gap:
                gaps.append(current_gap)
            current_gap = {"gap": gap_val}
            continue

        imp_val = _strip_label(line, 'IMPLICATION')
        if imp_val is not None:
            current_gap["implication"] = imp_val
            continue

        rec_val = _strip_label(line, 'RECOMMENDATION')
        if rec_val is not None:
            current_gap["recommendation"] = rec_val
            continue

        # Continuation line — append to last field
        if current_gap:
            last_key = list(current_gap.keys())[-1] if current_gap else None
            if last_key:
                current_gap[last_key] += " " + line

    if current_gap:
        gaps.append(current_gap)

    return gaps


# ============================================================
# Post-processing checks (shared by both tiers)
# ============================================================

def _post_process_checks(question_id: str, answer_text: str) -> dict:
    """Run quality checks on the generated answer."""
    warnings = {
        "outside_knowledge_flags": [],
        "uncited_paragraphs": [],
        "roadmap_flags": [],
        "key_loss_check": None,
        "blockchain_overclaim": None,
    }

    # Check for outside knowledge indicators
    warning_phrases = [
        "typically", "generally", "in most distributed systems",
        "it is common to", "industry standard", "best practice",
        "as is well known", "fundamentally",
        "in cloud computing", "traditionally"
    ]
    for phrase in warning_phrases:
        if phrase.lower() in answer_text.lower():
            warnings["outside_knowledge_flags"].append(
                f"Possible outside knowledge: '{phrase}' detected")

    # Check for uncited paragraphs
    paragraphs = [p.strip() for p in answer_text.split("\n\n")
                  if p.strip() and len(p.strip()) > 50]
    for i, para in enumerate(paragraphs):
        has_citation = ("[[chunk:" in para or "[[doc:" in para)
        is_structural = (para.startswith("#") or para.startswith("**What") or
                        para.startswith("---") or para.startswith("*"))
        if not has_citation and not is_structural:
            warnings["uncited_paragraphs"].append(f"Paragraph {i+1}")

    # Check for roadmap items presented as current
    roadmap_indicators = [
        "Definition of done:", "Plan:", "Milestone ", "AC:", "DoD:",
        "TODO", "in development", "Delivery set", "Delivery Set"
    ]
    for indicator in roadmap_indicators:
        if indicator.lower() in answer_text.lower():
            context_start = max(0, answer_text.lower().find(indicator.lower()) - 100)
            context = answer_text.lower()[context_start:context_start + 200]
            if not any(label in context for label in [
                "planned", "roadmap", "milestone", "in development",
                "not yet", "future", "upcoming"
            ]):
                warnings["roadmap_flags"].append(
                    f"Roadmap indicator '{indicator}' may not be properly labeled")

    # Q3-specific: check for key loss mention
    if question_id == "Q3":
        key_loss_terms = ["key is lost", "key loss", "lose.*key", "lost.*key",
                          "key.*lost", "documents do not.*key",
                          "documents do not.*loss", "recovery"]
        has_key_loss = any(re.search(term, answer_text, re.IGNORECASE)
                          for term in key_loss_terms)
        if not has_key_loss:
            warnings["key_loss_check"] = (
                "WARNING: Q3 answer does not address key loss scenario (required by rubric)")

    # Q1-specific: check for blockchain overclaim
    if question_id == "Q1":
        overclaim_phrases = [
            "eliminates.*blockchain.*single point",
            "eliminates.*blockchain.*spof",
            "operates independently of.*blockchain",
            "no.*depend.*on.*blockchain",
            "removes.*blockchain.*dependency",
        ]
        for phrase in overclaim_phrases:
            if re.search(phrase, answer_text, re.IGNORECASE):
                warnings["blockchain_overclaim"] = (
                    f"WARNING: Q1 may overclaim blockchain independence: '{phrase}' detected")
                break

    return warnings


if __name__ == "__main__":
    # Quick test
    test_evidence = [{
        "chunk_id": "test-doc-p1-0001",
        "text": "The DDC cluster uses a peer-to-peer architecture where each node operates independently.",
        "pdf_file": "test.pdf",
        "page_start": 1,
        "relevance": 0.85
    }]

    result = answer_question("Q1",
        "Why does the highly peer-to-peer design of the DDC clusters ensure resilience?",
        test_evidence)
    print(json.dumps(result, indent=2))
