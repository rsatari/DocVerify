"""
Correlation Agent
Takes internal claims (with chunk citations) and external research results
and builds a structured comparison table.

Outputs:
  - Dual-cited comparison rows [[internal:chunk_id]] + [[external:url]]
  - Advantage / Disadvantage / Inconclusive classification per row
  - Confidence level based on source authority and cross-validation
  - Enriched answer that weaves external evidence into the original
"""

import os
import json
import re
from dotenv import load_dotenv
from anthropic import Anthropic
import yaml

load_dotenv()

SYSTEM_PROMPT = """You are CorrelationAgent. You build structured comparison tables between DDC (internal docs)
and external platforms (researched data).

Your job:
1. Identify DDC's documented security/architecture features from internal evidence chunks
2. For EACH DDC feature, find the corresponding external platform approach from the research results
3. Build a comparison row showing: "DDC does X" vs "Platform does Y"
4. Cite both sides with dual citations:
   - [[internal:CHUNK_ID]] for DDC claims from source documents
   - [[external:URL]] for external platform evidence from web research

CRITICAL APPROACH — BUILD OUTWARD FROM DDC FEATURES:
- Do NOT require DDC docs to name or mention competitors. They won't.
- Instead: take each DDC security feature (e.g., client-side encryption, key ownership, no central coordinator)
  and contrast it with how external platforms handle the SAME concern (e.g., server-side encryption, KMS-managed keys, central control plane).
- The original answer may say "the docs don't mention Databricks/Snowflake" — that's expected.
  Your job is to build the comparison anyway using DDC's features + external research findings.
- If the original answer lacks comparative claims, extract DDC's core features from the internal evidence
  chunks directly and compare each one against the external research.

CLASSIFICATION per row:
   - "ddc_advantage": DDC has a clear, documented advantage
   - "platform_advantage": The external platform has a documented advantage
   - "equivalent": Both platforms are comparable
   - "inconclusive": Evidence is insufficient or contradictory
   - "ddc_gap": DDC docs don't cover this but should

CRITICAL RULES:
- NEVER fabricate external evidence. If research didn't find it, mark as "NOT_FOUND"
- If a claim is only supported by vendor marketing (not technical docs), flag it as "low_confidence"
- If Tavily and OpenAI searches disagree, flag as "conflicting_sources"
- Preference order: cross-validated > vendor_official > third_party_audit > analyst > community
- Security claims require at least one vendor_official or third_party_audit source
- You MUST produce at least 3 comparison rows. If the answer text has no comparative claims,
  derive DDC features from the internal evidence chunks and compare each one.

Respond with ONLY valid JSON."""


def build_comparison(question_id: str,
                     question_text: str,
                     answer_data: dict,
                     claims_data: dict,
                     research_results: list[dict],
                     evidence_chunks: list[dict],
                     config_path: str = "config/pipeline_config.yaml") -> dict:
    """
    Build a comparison table for a research-augmented question.

    Returns:
        {
            "question_id": str,
            "comparison_table": [
                {
                    "aspect": str,
                    "ddc_position": str,
                    "ddc_citation": "[[internal:chunk_id]]",
                    "external_position": str,
                    "external_citation": "[[external:url]]",
                    "classification": "ddc_advantage|platform_advantage|equivalent|inconclusive|ddc_gap",
                    "confidence": "high|medium|low",
                    "notes": str
                }
            ],
            "enriched_answer": str,  # Original answer + external context
            "summary": {
                "ddc_advantages": int,
                "platform_advantages": int,
                "equivalent": int,
                "inconclusive": int,
                "ddc_gaps": int,
            },
            "source_quality": {
                "total_external_sources": int,
                "vendor_official": int,
                "third_party_audit": int,
                "cross_validated": int,
            }
        }
    """
    with open(config_path) as f:
        config = yaml.safe_load(f)

    model_config = config["models"].get("correlator", config["models"]["answerer"])

    # Format the internal evidence
    evidence_text = ""
    for chunk in evidence_chunks[:15]:
        evidence_text += f"\n[{chunk['chunk_id']}]: {chunk['text'][:300]}...\n"

    # Format claims with their research results
    claims_with_research = []
    research_by_claim = {r["claim_id"]: r for r in research_results}

    for claim in claims_data.get("claims", []):
        claim_id = claim.get("claim_id")
        research = research_by_claim.get(claim_id, {})
        claims_with_research.append({
            "claim": claim,
            "external_evidence": research.get("external_evidence", {}),
            "best_sources": research.get("external_evidence", {}).get("best_sources", []),
            "key_findings": research.get("external_evidence", {}).get("key_findings", []),
        })

    user_prompt = f"""BUILD A COMPARISON TABLE for {question_id}:

QUESTION: {question_text}

ORIGINAL ANSWER (from internal docs):
{answer_data['answer_markdown']}

INTERNAL EVIDENCE CHUNKS (DDC's actual documented features):
{evidence_text}

CLAIMS WITH EXTERNAL RESEARCH:
{json.dumps(claims_with_research, indent=2, default=str)}

Instructions:
1. FIRST, extract DDC's key security/architecture features from the INTERNAL EVIDENCE CHUNKS above.
   These are DDC's positions in the comparison — they exist even if the original answer doesn't
   explicitly compare them to external platforms.
2. For EACH DDC feature, find the corresponding external platform approach from the research results.
   Example: DDC has "client-side encryption with owner-held keys" → Databricks has "server-side encryption with KMS-managed keys"
3. Build a comparison row for each feature pair with dual citations:
   - [[internal:CHUNK_ID]] citing the DDC evidence chunk
   - [[external:URL]] citing the external research source
4. If no external evidence was found for a DDC feature, set external_citation to "NOT_FOUND"
5. Classify each row and assign confidence
6. You MUST produce at least 3 comparison rows — extract DDC features from the evidence chunks
   even if the original answer contains no comparative language.
7. Then write an ENRICHED answer that incorporates both internal and external evidence:
   - Keep all original DDC citations
   - Add external citations where research supports/refutes claims
   - Add comparative statements derived from the table

Respond with this JSON:
{{
  "question_id": "{question_id}",
  "comparison_table": [
    {{
      "aspect": "<security/architecture feature being compared>",
      "ddc_position": "<what DDC docs say about this feature>",
      "ddc_citation": "[[internal:chunk_id]]",
      "external_position": "<what external research found about how competitor handles this>",
      "external_citation": "[[external:url]] or NOT_FOUND",
      "classification": "ddc_advantage|platform_advantage|equivalent|inconclusive|ddc_gap",
      "confidence": "high|medium|low",
      "notes": "<any caveats>"
    }}
  ],
  "enriched_answer": "<full rewritten answer with both [[internal:X]] and [[external:URL]] citations>",
  "unverified_claims": [
    "<claims from original answer that couldn't be verified externally>"
  ],
  "conflicting_findings": [
    "<any contradictions between internal docs and external evidence>"
  ]
}}"""

    client = Anthropic(api_key=os.environ.get("ANTHROPIC_API_KEY"))

    response = client.messages.create(
        model=model_config["model"],
        max_tokens=config["models"].get("correlator", {}).get("max_tokens", 3000),
        system=SYSTEM_PROMPT,
        messages=[{"role": "user", "content": user_prompt}]
    )

    response_text = response.content[0].text

    try:
        from agents.cost_tracker import track_cost
        track_cost("correlator", question_id, model_config["model"],
                   response.usage.input_tokens, response.usage.output_tokens)
    except (ImportError, AttributeError):
        pass

    try:
        json_match = re.search(r'\{.*\}', response_text, re.DOTALL)
        if json_match:
            result = json.loads(json_match.group())
        else:
            result = json.loads(response_text)
    except json.JSONDecodeError:
        result = {
            "question_id": question_id,
            "comparison_table": [],
            "enriched_answer": answer_data["answer_markdown"],
            "error": "Failed to parse correlation response",
            "raw_response": response_text[:500],
        }

    # Compute summary stats
    table = result.get("comparison_table", [])
    result["summary"] = {
        "ddc_advantages": sum(1 for r in table if r.get("classification") == "ddc_advantage"),
        "platform_advantages": sum(1 for r in table if r.get("classification") == "platform_advantage"),
        "equivalent": sum(1 for r in table if r.get("classification") == "equivalent"),
        "inconclusive": sum(1 for r in table if r.get("classification") == "inconclusive"),
        "ddc_gaps": sum(1 for r in table if r.get("classification") == "ddc_gap"),
    }

    # Source quality stats
    all_sources = []
    for r in research_results:
        all_sources.extend(r.get("external_evidence", {}).get("best_sources", []))

    result["source_quality"] = {
        "total_external_sources": len(all_sources),
        "vendor_official": sum(1 for s in all_sources if s.get("authority") == "vendor_official"),
        "third_party_audit": sum(1 for s in all_sources if s.get("authority") == "third_party_audit"),
        "cross_validated": sum(1 for s in all_sources if s.get("cross_validated")),
    }

    result["token_usage"] = {
        "input_tokens": response.usage.input_tokens,
        "output_tokens": response.usage.output_tokens,
    }

    return result


if __name__ == "__main__":
    # Minimal test
    test_result = build_comparison(
        question_id="Q2",
        question_text="How is DDC more secure than Databricks?",
        answer_data={
            "question_id": "Q2",
            "answer_markdown": "DDC keeps encryption keys with the data owner [[chunk:sec-001]].",
            "cited_chunks": ["sec-001"],
        },
        claims_data={
            "claims": [{
                "claim_id": "Q2-C001",
                "text": "DDC keeps encryption keys with the data owner",
                "type": "comparative",
                "internal_citations": ["sec-001"],
                "needs_external": True,
                "comparison_target": "databricks",
            }]
        },
        research_results=[{
            "claim_id": "Q2-C001",
            "external_evidence": {
                "verdict": "partially_supported",
                "key_findings": ["Databricks uses customer-managed keys via AWS KMS"],
                "best_sources": [{"url": "https://docs.databricks.com/security/keys.html", "authority": "vendor_official"}],
            }
        }],
        evidence_chunks=[{
            "chunk_id": "sec-001",
            "text": "In DDC, encryption keys are held exclusively by the data owner.",
            "pdf_file": "security.pdf",
            "page_start": 5,
        }],
    )
    print(json.dumps(test_result, indent=2, default=str))
