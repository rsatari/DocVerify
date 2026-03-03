"""
Claim Extractor Agent
Breaks a generated answer into atomic, verifiable claims.
Each claim is tagged with its internal citation (chunk ID) and categorized
by type (factual, comparative, mechanism, security guarantee).

This is the bridge between Loop A's answer and Loop B's research stage.
"""

import os
import json
import re
from dotenv import load_dotenv
from anthropic import Anthropic
import yaml

load_dotenv()

SYSTEM_PROMPT = """You are ClaimExtractor. You decompose a technical answer into individual, atomic claims.

For each claim, extract:
1. The exact claim text (1-2 sentences max)
2. The claim TYPE:
   - "factual": A stated fact about DDC architecture or behavior
   - "comparative": A comparison with another platform (Databricks, Snowflake, AWS, Azure, etc.)
   - "mechanism": How something works technically
   - "security_guarantee": A security or trust claim
   - "gap_acknowledgment": The answer says "docs don't specify" — this is NOT a claim to verify
3. The internal citation chunk IDs referenced (from [[chunk:XXX]] tags)
4. Whether this claim could be VERIFIED or COMPARED against external sources
5. The comparison target platform (if comparative)

RULES:
- Split compound claims: "DDC does X and Y" → two separate claims
- Preserve the original meaning — don't paraphrase
- "gap_acknowledgment" claims should NOT be sent for external research
- Mark claims as "needs_external" = true if they assert DDC is better/different than an external platform

Respond with ONLY valid JSON."""


def extract_claims(answer_data: dict,
                   config_path: str = "config/pipeline_config.yaml") -> dict:
    """
    Extract atomic claims from a generated answer.

    Returns:
        {
            "question_id": str,
            "total_claims": int,
            "claims": [
                {
                    "claim_id": "Q2-C001",
                    "text": str,
                    "type": "factual|comparative|mechanism|security_guarantee|gap_acknowledgment",
                    "internal_citations": ["chunk_id_1", ...],
                    "needs_external": bool,
                    "comparison_target": str or null,
                    "verification_query": str  # what to search for externally
                }
            ],
            "comparative_claims_count": int,
            "claims_needing_research": int,
        }
    """
    with open(config_path) as f:
        config = yaml.safe_load(f)

    model_config = config["models"].get("claim_extractor", config["models"]["answerer"])
    question_id = answer_data["question_id"]

    user_prompt = f"""ANSWER TO DECOMPOSE (for {question_id}):

{answer_data['answer_markdown']}

CITED CHUNKS: {json.dumps(answer_data.get('cited_chunks', []))}

Extract every individual claim from this answer. For comparative claims, include what platform
is being compared and what specific search query would verify the external platform's behavior.

Respond with this JSON:
{{
  "question_id": "{question_id}",
  "claims": [
    {{
      "claim_id": "{question_id}-C001",
      "text": "<the atomic claim>",
      "type": "<factual|comparative|mechanism|security_guarantee|gap_acknowledgment>",
      "internal_citations": ["<chunk_ids from [[chunk:X]] tags>"],
      "needs_external": true/false,
      "comparison_target": "<platform name or null>",
      "verification_query": "<search query to verify this claim externally, or null>"
    }}
  ]
}}"""

    client = Anthropic(api_key=os.environ.get("ANTHROPIC_API_KEY"))

    response = client.messages.create(
        model=model_config["model"],
        max_tokens=model_config.get("max_tokens", 2000),
        system=SYSTEM_PROMPT,
        messages=[{"role": "user", "content": user_prompt}]
    )

    response_text = response.content[0].text

    try:
        json_match = re.search(r'\{.*\}', response_text, re.DOTALL)
        if json_match:
            result = json.loads(json_match.group())
        else:
            result = json.loads(response_text)
    except json.JSONDecodeError:
        result = {
            "question_id": question_id,
            "claims": [],
            "error": "Failed to parse claim extraction response",
            "raw_response": response_text
        }

    # Add computed summaries
    claims = result.get("claims", [])
    result["total_claims"] = len(claims)
    result["comparative_claims_count"] = sum(1 for c in claims if c.get("type") == "comparative")
    result["claims_needing_research"] = sum(1 for c in claims if c.get("needs_external"))

    result["token_usage"] = {
        "input_tokens": response.usage.input_tokens,
        "output_tokens": response.usage.output_tokens
    }

    return result


if __name__ == "__main__":
    test_answer = {
        "question_id": "Q2",
        "answer_markdown": """The DDC cluster provides stronger data locality guarantees than typical cloud stacks [[chunk:sec-001]].
In a Databricks or Snowflake deployment on AWS, data at rest is encrypted by the cloud provider,
meaning the provider holds the encryption keys [[chunk:sec-002]]. In DDC, key custody remains
with the data owner [[chunk:sec-003]]. The provided documents do not specify whether DDC supports
hardware security modules (HSMs).""",
        "cited_chunks": ["sec-001", "sec-002", "sec-003"]
    }

    result = extract_claims(test_answer)
    print(json.dumps(result, indent=2))
