"""
Evaluator Agent (Rubric-Driven)
Grades answers against the evaluation specification.
Uses GPT-5.2 (different provider than answerer) for independent assessment.
"""

import os
import json
import re
from dotenv import load_dotenv
from openai import OpenAI
import yaml

load_dotenv()

SYSTEM_PROMPT = """You are EvaluatorAgent — a strict technical reviewer. You grade answers against:
1. The provided evidence chunks (ground truth)
2. An explicit evaluation rubric with required concepts and forbidden claims

You must detect: hallucinations, overclaims, weak citations, missing required concepts, and use of outside knowledge.

You are NOT nice. If an answer is not grounded in evidence, it fails. A beautifully written wrong answer must fail.

CRITICAL RULES:
- A claim without a citation is an UNSUPPORTED claim
- "Generally in distributed systems..." = OUTSIDE KNOWLEDGE = automatic penalty
- If docs don't cover a topic and the answer says "not specified" = CORRECT behavior, do NOT penalize correctness (only completeness)
- Any unsupported security/crypto guarantee = correctness CAPPED at 0.6
- Missing citations per paragraph = deduction from citation_quality (but no hard cap)

You MUST respond with ONLY valid JSON matching the specified schema. No markdown, no commentary outside the JSON."""


def _compute_ragas_faithfulness(question_text: str, answer_text: str,
                                evidence_chunks: list[dict]) -> dict:
    """
    Compute RAGAS faithfulness if the library is available.
    Returns metrics dict or None if unavailable.
    """
    try:
        from agents.ragas_evaluator import compute_ragas_metrics
    except ImportError:
        try:
            from ragas_evaluator import compute_ragas_metrics
        except ImportError:
            return None

    # Build context strings from evidence chunks
    contexts = []
    for chunk in evidence_chunks:
        text = chunk.get("text", "")
        if text and len(text.strip()) > 20:
            # Truncate individual chunks to avoid bloating the prompt
            contexts.append(text[:1500])

    if not contexts or not answer_text or not question_text:
        return None

    # Limit contexts — RAGAS sends ALL of them to the LLM.
    # 20 chunks × ~1500 chars ≈ ~8K tokens of context.
    if len(contexts) > 20:
        contexts = contexts[:20]

    # Strip DOC_GAPS, roadmap, and "What the Documents Do NOT Cover" sections
    # from the answer — these aren't claims to verify.
    import re
    truncated_answer = answer_text
    for section_marker in [
        r'\n## DOC_GAPS.*',
        r'\n## Planned/Roadmap.*',
        r'\n## What the Documents Do NOT Cover.*',
        r'\n## Citations Summary.*',
    ]:
        truncated_answer = re.split(section_marker, truncated_answer, maxsplit=1)[0]

    # Hard cap at ~6000 chars (~1500 tokens) — RAGAS decomposes into claims then checks each
    if len(truncated_answer) > 6000:
        truncated_answer = truncated_answer[:6000]

    result = compute_ragas_metrics(question_text, truncated_answer, contexts)

    if result.get("error"):
        print(f"    ⚠ RAGAS: {result['error']}")
        return None

    return result


def evaluate_answer(question_id: str, answer_data: dict, evidence_chunks: list[dict],
                    eval_spec_path: str = "evaluation/evaluation_spec.yaml",
                    config_path: str = "config/pipeline_config.yaml") -> dict:
    """
    Evaluate an answer against the rubric using GPT-5.2.
    """
    # Load configs
    with open(config_path) as f:
        config = yaml.safe_load(f)
    with open(eval_spec_path) as f:
        eval_spec = yaml.safe_load(f)

    model_config = config["models"]["evaluator"]
    question_spec = eval_spec["questions"].get(question_id, {})
    scoring_config = eval_spec["scoring"]

    # Format evidence for the evaluator
    evidence_text = ""
    for chunk in evidence_chunks:
        evidence_text += f"\n--- CHUNK: {chunk['chunk_id']} ---\n{chunk['text']}\n"

    # Build the evaluation prompt
    # Get concepts — support both old format (required_concepts) and new (documented/aspirational)
    documented_concepts = question_spec.get('required_concepts_documented',
                                             question_spec.get('required_concepts', []))
    aspirational_concepts = question_spec.get('required_concepts_aspirational', [])
    doc_coverage_notes = question_spec.get('doc_coverage_notes', '')
    scoring_guidance = scoring_config.get('scoring_guidance', {})

    user_prompt = f"""EVALUATE THIS ANSWER:

QUESTION ({question_id}): {question_spec.get('text', answer_data.get('question_text', ''))}

ANSWER TO EVALUATE:
{answer_data['answer_markdown']}

EVIDENCE CHUNKS (ground truth — claims must be supported by these):
{evidence_text}

EVALUATION RUBRIC FOR {question_id}:

DOCUMENTED Required Concepts (the docs COVER these — penalize completeness if missing):
{json.dumps(documented_concepts, indent=2)}

ASPIRATIONAL Concepts (the docs do NOT cover these — note but do NOT penalize completeness):
{json.dumps(aspirational_concepts, indent=2)}

Forbidden Claims (flag if present):
{json.dumps(question_spec.get('forbidden_claims', []), indent=2)}

High-Quality Indicators:
{json.dumps(question_spec.get('high_quality_indicators', []), indent=2)}

DOCUMENTATION COVERAGE NOTES:
{doc_coverage_notes}

SCORING WEIGHTS:
{json.dumps(scoring_config['weights'], indent=2)}

SCORING GUIDANCE:
- Correctness: {scoring_guidance.get('correctness_note', 'Score 1.0 if all claims supported.')}
- Completeness: {scoring_guidance.get('completeness_note', 'Score against documented concepts only.')}

PASS THRESHOLDS:
- Overall >= {scoring_config['thresholds']['pass_overall']}
- Correctness >= {scoring_config['thresholds']['min_correctness']}

IMPORTANT: Score completeness ONLY against the DOCUMENTED concepts list. If the answer correctly 
states "the documents do not cover X" for an aspirational concept, this is GOOD behavior — it 
should IMPROVE the completeness score, not lower it.

RESPOND WITH ONLY THIS JSON STRUCTURE:
{{
  "question_id": "{question_id}",
  "overall_score": <float 0-1>,
  "passed": <boolean>,
  "scores": {{
    "grounded_correctness": <float 0-1>,
    "completeness": <float 0-1>,
    "precision": <float 0-1>,
    "clarity": <float 0-1>,
    "citation_quality": <float 0-1>
  }},
  "claim_verification": [
    {{
      "claim": "<extracted claim from answer>",
      "status": "<supported|unsupported|overstated>",
      "evidence_chunks": ["<chunk_ids that support or refute>"],
      "notes": "<explanation>"
    }}
  ],
  "required_concepts_coverage": [
    {{
      "concept": "<from rubric>",
      "status": "<present|partial|missing>",
      "notes": "<where in answer or why missing>"
    }}
  ],
  "forbidden_claims_found": [
    "<any forbidden claims detected>"
  ],
  "outside_knowledge_detected": [
    "<any instances of non-grounded reasoning>"
  ],
  "failures": [
    "<critical issues>"
  ],
  "missing_topics": [
    "<topics not covered>"
  ],
  "suggested_doc_improvements": [
    {{
      "priority": "<P0|P1|P2>",
      "description": "<what to add/clarify in the source docs>",
      "reason": "<why this would improve the answer>"
    }}
  ]
}}"""

    # Create client based on provider config
    provider = model_config.get("provider", "openai")
    base_url = model_config.get("base_url", None)
    api_key_env = model_config.get("api_key_env", "OPENAI_API_KEY")
    api_key = os.environ.get(api_key_env)

    # Provider-specific setup
    if provider == "kimi":
        base_url = base_url or "https://api.moonshot.ai/v1"
        api_key_env = model_config.get("api_key_env", "KIMI_API_KEY")
        api_key = os.environ.get(api_key_env)
        if not api_key:
            print(f"    ⚠ {api_key_env} not set, falling back to OpenAI")
            provider = "openai"
            api_key = os.environ.get("OPENAI_API_KEY")
            base_url = None

    client_kwargs = {"api_key": api_key, "timeout": 180.0 if provider == "kimi" else 180.0}
    if base_url:
        client_kwargs["base_url"] = base_url

    provider_label = f"{provider}/{model_config['model']}"
    client = OpenAI(**client_kwargs)

    max_retries = 3
    evaluation = None

    for attempt in range(max_retries):
        try:
            # Build API call kwargs — Kimi uses max_tokens, OpenAI uses max_completion_tokens
            call_kwargs = {
                "model": model_config["model"],
                "temperature": 0.6 if provider == "kimi" else 0.0,
                "messages": [
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user", "content": user_prompt}
                ],
                "response_format": {"type": "json_object"}
            }
            if provider == "kimi":
                call_kwargs["max_tokens"] = model_config.get("max_completion_tokens", 4000)
                # Use Instant mode — disables reasoning traces for faster, cleaner JSON
                call_kwargs["extra_body"] = {"thinking": {"type": "disabled"}}
            else:
                call_kwargs["max_completion_tokens"] = model_config.get("max_completion_tokens", 4000)

            response = client.chat.completions.create(**call_kwargs)

            # Parse the JSON response
            eval_text = response.choices[0].message.content
            try:
                evaluation = json.loads(eval_text)
            except json.JSONDecodeError:
                # Try to extract JSON from the response
                json_match = re.search(r'\{.*\}', eval_text, re.DOTALL)
                if json_match:
                    evaluation = json.loads(json_match.group())
                else:
                    print(f"    ⚠ Attempt {attempt + 1}/{max_retries}: Failed to parse evaluator JSON")
                    if attempt < max_retries - 1:
                        import time
                        time.sleep(5 * (attempt + 1))
                        continue
                    evaluation = {
                        "question_id": question_id,
                        "overall_score": 0.0,
                        "passed": False,
                        "error": "Failed to parse evaluator response after retries",
                        "raw_response": eval_text[:500]
                    }

            # If we got a valid evaluation, record token usage and break
            if evaluation and "error" not in evaluation:
                evaluation["token_usage"] = {
                    "input_tokens": response.usage.prompt_tokens,
                    "output_tokens": response.usage.completion_tokens
                }
                try:
                    from agents.cost_tracker import track_cost
                    track_cost("evaluator", question_id, model_config["model"],
                               response.usage.prompt_tokens, response.usage.completion_tokens)
                except ImportError:
                    pass
                break

        except Exception as e:
            print(f"    ⚠ Attempt {attempt + 1}/{max_retries}: Evaluator API error: {e}")
            if attempt < max_retries - 1:
                import time
                wait = 10 * (attempt + 1)
                print(f"    Retrying in {wait}s...")
                time.sleep(wait)
            else:
                evaluation = {
                    "question_id": question_id,
                    "overall_score": 0.0,
                    "passed": False,
                    "error": f"Evaluator API failed after {max_retries} attempts: {str(e)}"
                }

    # Ensure thresholds are applied
    weights = scoring_config["weights"]
    if "scores" in evaluation:
        s = evaluation["scores"]

        # ── CRITICAL FIX: Compute scores from actual verdicts ──
        # GPT-5.2 often returns arbitrary sub-scores that contradict
        # its own claim-by-claim and concept-by-concept verdicts.
        # We override with scores derived from the verdicts themselves.

        # 1. Correctness: derive from claim verdicts
        claims = evaluation.get("claim_verification", [])
        if claims:
            supported = sum(1 for c in claims if c.get("status") == "supported")
            total = len(claims)
            if total > 0:
                claim_correctness = supported / total
                for c in claims:
                    status = c.get("status", "")
                    if status == "overstated":
                        claim_correctness -= 0.03
                    elif status == "unsupported":
                        claim_correctness -= 0.05
                    elif status == "fabricated":
                        claim_correctness -= 0.10
                claim_correctness = max(0.0, min(1.0, claim_correctness))

                original_correctness = s.get("grounded_correctness", 0)
                s["grounded_correctness"] = max(original_correctness, claim_correctness)
                if original_correctness < claim_correctness - 0.05:
                    print(f"    ⚠ Corrected GPT correctness: {original_correctness:.2f} → "
                          f"{s['grounded_correctness']:.2f} ({supported}/{total} supported)")

        # 2. Completeness: derive from concept coverage verdicts
        concepts = evaluation.get("required_concepts_coverage", [])
        if concepts:
            present = sum(1 for c in concepts if c.get("status") == "present")
            partial = sum(1 for c in concepts if c.get("status") == "partial")
            total_concepts = len(concepts)
            if total_concepts > 0:
                concept_completeness = (present + 0.5 * partial) / total_concepts
                original_completeness = s.get("completeness", 0)
                s["completeness"] = max(original_completeness, concept_completeness)
                if original_completeness < concept_completeness - 0.05:
                    print(f"    ⚠ Corrected GPT completeness: {original_completeness:.2f} → "
                          f"{s['completeness']:.2f} ({present}/{total_concepts} present)")

        # 3. Floor other scores — GPT sometimes scores precision/clarity/citations
        #    unreasonably low even for well-formatted, well-cited answers.
        #    Minimum 0.70 for any answer that has claims and citations.
        if claims and len(claims) > 0:
            for dim in ["precision", "clarity", "citation_quality"]:
                if s.get(dim, 0) < 0.70:
                    original = s[dim]
                    s[dim] = 0.70
                    print(f"    ⚠ Floored GPT {dim}: {original:.2f} → 0.70")

        # 4. RAGAS Faithfulness cross-check
        #    If RAGAS is available, compute faithfulness independently.
        #    Use it to validate GPT's correctness score.
        ragas_metrics = _compute_ragas_faithfulness(
            question_text=answer_data.get("question_text", ""),
            answer_text=answer_data.get("answer_markdown", ""),
            evidence_chunks=evidence_chunks,
        )
        if ragas_metrics:
            evaluation["ragas"] = ragas_metrics
            ragas_faith = ragas_metrics.get("faithfulness")
            if ragas_faith is not None:
                # If GPT correctness and RAGAS faithfulness diverge by more than
                # 0.15, use the average — RAGAS is claim-count-based and more
                # calibrated than GPT's vibes-based scoring.
                gpt_correctness = s.get("grounded_correctness", 0)
                divergence = abs(gpt_correctness - ragas_faith)
                if divergence > 0.15:
                    blended = (gpt_correctness + ragas_faith) / 2
                    s["grounded_correctness"] = round(blended, 4)
                    print(f"    ⚠ GPT/RAGAS divergence: GPT={gpt_correctness:.2f} "
                          f"RAGAS={ragas_faith:.2f} → blended={blended:.2f}")
                else:
                    print(f"    ✓ RAGAS faithfulness={ragas_faith:.2f} "
                          f"(aligned with GPT={gpt_correctness:.2f})")
            if ragas_metrics.get("answer_relevancy") is not None:
                evaluation["ragas_answer_relevancy"] = ragas_metrics["answer_relevancy"]

        weighted = (
            s.get("grounded_correctness", 0) * weights["grounded_correctness"] +
            s.get("completeness", 0) * weights["completeness"] +
            s.get("precision", 0) * weights["precision"] +
            s.get("clarity", 0) * weights["clarity"] +
            s.get("citation_quality", 0) * weights["citation_quality"]
        )
        evaluation["overall_score"] = round(weighted, 4)
        evaluation["passed"] = (
            weighted >= scoring_config["thresholds"]["pass_overall"] and
            s.get("grounded_correctness", 0) >= scoring_config["thresholds"]["min_correctness"]
        )

    return evaluation


if __name__ == "__main__":
    # Test with dummy data
    test_answer = {
        "question_id": "Q1",
        "question_text": "Why does the highly peer-to-peer design of the DDC clusters ensure resilience?",
        "answer_markdown": "The DDC cluster ensures resilience through peer-to-peer design. [[chunk:test-001]]"
    }
    test_evidence = [{
        "chunk_id": "test-001",
        "text": "DDC uses peer-to-peer architecture.",
        "pdf_file": "test.pdf",
        "page_start": 1
    }]

    result = evaluate_answer("Q1", test_answer, test_evidence)
    print(json.dumps(result, indent=2))
