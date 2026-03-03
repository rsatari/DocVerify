"""
Editor Agent (Doc Patcher)
Takes evaluation reports and proposes specific improvements to source documentation.
Uses Claude for generating targeted, minimal edits.
"""

import os
import json
import re
from dotenv import load_dotenv
from anthropic import Anthropic
import yaml

load_dotenv()

SYSTEM_PROMPT = """You are EditorAgent. Your job is to improve source documentation so that a closed-book QA system can answer FAQ questions correctly and completely.

RULES:
1. Propose MINIMAL, TARGETED edits — not rewrites
2. Do NOT invent technical claims. If you're unsure whether something is true about DDC, mark it as: [TODO: VERIFY WITH ENGINEERING TEAM]
3. Every addition must be either:
   - Directly supported by existing document content (reorganize/clarify)
   - Explicitly marked as TODO if it requires outside verification
4. Focus on GAPS identified by the evaluator — things the docs should say but don't
5. Keep edits small: aim for 1-3 specific additions per iteration
6. Never change security guarantees, cryptographic claims, or architecture assertions without marking for human review

OUTPUT FORMAT:
For each proposed change, provide:
- WHERE: Which document/section to edit
- WHAT: The specific text to add or modify
- WHY: Which evaluation gap this addresses
- RISK: Whether this needs human review

Respond with ONLY valid JSON."""


def _extract_json(text: str) -> dict | None:
    """
    Attempt to extract valid JSON from model output using multiple strategies.
    Returns parsed dict on success, None on failure.
    """

    # Strategy 1: Direct parse (cleanest case)
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass

    # Strategy 2: Strip markdown code fences (```json ... ``` or ``` ... ```)
    fenced = re.search(r'```(?:json)?\s*(\{.*?\})\s*```', text, re.DOTALL)
    if fenced:
        try:
            return json.loads(fenced.group(1))
        except json.JSONDecodeError:
            pass

    # Strategy 3: Find the outermost { ... } block (greedy)
    brace_match = re.search(r'\{.*\}', text, re.DOTALL)
    if brace_match:
        try:
            return json.loads(brace_match.group())
        except json.JSONDecodeError:
            pass

    # Strategy 4: Find by balanced braces (handles nested objects better)
    start = text.find('{')
    if start != -1:
        depth = 0
        for i in range(start, len(text)):
            if text[i] == '{':
                depth += 1
            elif text[i] == '}':
                depth -= 1
                if depth == 0:
                    try:
                        return json.loads(text[start:i + 1])
                    except json.JSONDecodeError:
                        break

    return None


def propose_improvements(evaluation_reports: list[dict], evidence_chunks: list[dict],
                         config_path: str = "config/pipeline_config.yaml") -> dict:
    """
    Analyze evaluation reports and propose document improvements.
    """
    with open(config_path) as f:
        config = yaml.safe_load(f)

    model_config = config["models"]["editor"]

    # Collect all gaps and failures across questions
    all_gaps = []
    all_failures = []
    all_suggestions = []

    for report in evaluation_reports:
        qid = report.get("question_id", "?")
        all_gaps.extend([{
            "question": qid,
            "topic": t
        } for t in report.get("missing_topics", [])])
        all_failures.extend([{
            "question": qid,
            "failure": f
        } for f in report.get("failures", [])])
        all_suggestions.extend([{
            "question": qid,
            **s
        } for s in report.get("suggested_doc_improvements", [])])

        # Also check required concepts coverage
        for concept in report.get("required_concepts_coverage", []):
            if concept.get("status") in ["missing", "partial"]:
                all_gaps.append({
                    "question": qid,
                    "topic": concept.get("concept", ""),
                    "status": concept.get("status", ""),
                    "notes": concept.get("notes", "")
                })

    if not all_gaps and not all_failures and not all_suggestions:
        return {
            "status": "no_improvements_needed",
            "message": "All evaluations passed with no significant gaps.",
            "proposed_changes": []
        }

    # Format evidence context (so editor knows what's already in docs)
    evidence_summary = ""
    for chunk in evidence_chunks[:20]:  # Limit to avoid token overflow
        evidence_summary += f"\n[{chunk['chunk_id']}] ({chunk['pdf_file']}, p{chunk['page_start']}): {chunk['text'][:200]}...\n"

    user_prompt = f"""Based on the evaluation of 3 FAQ questions about DDC (Decentralized Data Cluster) documentation, the following gaps were identified:

MISSING TOPICS / GAPS:
{json.dumps(all_gaps, indent=2)}

CRITICAL FAILURES:
{json.dumps(all_failures, indent=2)}

EVALUATOR'S SUGGESTIONS:
{json.dumps(all_suggestions, indent=2)}

EXISTING DOCUMENT CONTENT (summary of what's already there):
{evidence_summary}

PROPOSE SPECIFIC DOCUMENT IMPROVEMENTS.

Respond with this JSON structure:
{{
  "summary": "<1-2 sentence overview of what needs to change>",
  "proposed_changes": [
    {{
      "id": "EDIT-001",
      "priority": "P0|P1|P2",
      "target_document": "<best guess of which PDF/section>",
      "target_section": "<section heading or 'NEW SECTION'>",
      "change_type": "add_content|clarify_existing|add_section|add_example",
      "description": "<what to add or change>",
      "suggested_text": "<the actual text to add, with [TODO: VERIFY] markers where needed>",
      "addresses_gap": "<which gap/failure this fixes>",
      "requires_human_review": true|false,
      "review_reason": "<why human review is needed, if applicable>"
    }}
  ],
  "questions_for_engineering_team": [
    "<specific questions that need answers to fill gaps>"
  ]
}}"""

    # Call Claude with retry logic for JSON parsing failures
    client = Anthropic(api_key=os.environ.get("ANTHROPIC_API_KEY"))

    max_retries = 3
    last_response_text = ""
    last_usage = None

    for attempt in range(max_retries):
        messages = [{"role": "user", "content": user_prompt}]

        # On retry, append the failed response and ask for valid JSON
        if attempt > 0:
            messages = [
                {"role": "user", "content": user_prompt},
                {"role": "assistant", "content": last_response_text},
                {"role": "user", "content": (
                    "Your previous response was not valid JSON and could not be parsed. "
                    "Please respond with ONLY a valid JSON object — no markdown fences, "
                    "no explanation text before or after the JSON. Start with { and end with }."
                )}
            ]

        response = client.messages.create(
            model=model_config["model"],
            max_tokens=model_config["max_tokens"],
            system=SYSTEM_PROMPT,
            messages=messages
        )

        last_response_text = response.content[0].text
        last_usage = response.usage

        # Attempt to parse JSON with multiple strategies
        improvements = _extract_json(last_response_text)
        if improvements is not None:
            break
    else:
        # All retries exhausted — return graceful fallback
        improvements = {
            "summary": "Editor produced non-JSON output after 3 attempts",
            "proposed_changes": [],
            "raw_response": last_response_text[:2000]
        }

    improvements["token_usage"] = {
        "input_tokens": last_usage.input_tokens if last_usage else 0,
        "output_tokens": last_usage.output_tokens if last_usage else 0
    }

    try:
        from agents.cost_tracker import track_cost
        if last_usage:
            track_cost("editor", "—", model_config["model"],
                       last_usage.input_tokens, last_usage.output_tokens)
    except (ImportError, AttributeError):
        pass

    return improvements


if __name__ == "__main__":
    test_reports = [{
        "question_id": "Q1",
        "missing_topics": ["node failure tolerance", "network partition recovery"],
        "failures": ["No explanation of what happens when nodes disappear"],
        "suggested_doc_improvements": [{
            "priority": "P0",
            "description": "Add section explaining node failure handling"
        }]
    }]

    result = propose_improvements(test_reports, [])
    print(json.dumps(result, indent=2))
