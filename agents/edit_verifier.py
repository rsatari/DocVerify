"""
Edit Verifier — Post-Edit Quality Assurance for Markdown Documents
===================================================================

After doc_editor_agent applies edits to markdown source files, this module
reads back the edited documents and verifies:

1. PLACEMENT: Each edit landed in the correct section (not random insertion)
2. COHERENCE: The surrounding text flows logically with the edit
3. STRUCTURE: Document headers/sections are intact, no broken formatting
4. ACCURACY: The edit text matches the approved content (no corruption)
5. CONFLICTS: Multiple edits didn't interfere with each other

Called after apply_edits() in the pipeline. Returns a verification report
with pass/fail per edit and an overall document health score.
"""

import os
import re
import json
from typing import Optional


# ============================================================
# Configuration
# ============================================================

VERIFY_MODEL = "claude-sonnet-4-5-20250929"  # Cost-efficient for verification
MAX_TOKENS_VERIFY = 4000

# Minimum coherence score to pass (0-1)
MIN_COHERENCE_SCORE = 0.6

# Maximum context window around edit for verification (chars)
CONTEXT_WINDOW = 800


# ============================================================
# Main Entry Point
# ============================================================

def verify_edits(edited_files: dict, all_edits: list[dict],
                 original_files: dict = None) -> dict:
    """
    Verify that applied edits are correctly placed and coherent.

    Args:
        edited_files: {pdf_name: edited_markdown_path} from apply_edits()
        all_edits: List of edit_metadata dicts from apply_edits()
        original_files: {pdf_name: original_markdown_path} (optional, for diff)

    Returns:
        {
            "verified": True/False,
            "total_edits": int,
            "passed": int,
            "failed": int,
            "flagged": int,
            "edit_results": [...],
            "document_health": {...},
            "summary": str
        }
    """
    if not edited_files or not all_edits:
        return {
            "verified": True,
            "total_edits": 0,
            "passed": 0,
            "failed": 0,
            "flagged": 0,
            "edit_results": [],
            "document_health": {},
            "summary": "No edits to verify."
        }

    edit_results = []
    doc_health = {}

    # Group edits by document
    edits_by_doc = {}
    for edit in all_edits:
        target = edit.get("target_doc", "")
        if target not in edits_by_doc:
            edits_by_doc[target] = []
        edits_by_doc[target].append(edit)

    # Verify each document
    for pdf_name, edited_path in edited_files.items():
        if not os.path.exists(edited_path):
            doc_health[pdf_name] = {"status": "missing", "score": 0}
            continue

        with open(edited_path, "r") as f:
            edited_text = f.read()

        # Load original for comparison if available
        original_text = None
        if original_files and pdf_name in original_files:
            orig_path = original_files[pdf_name]
            if os.path.exists(orig_path):
                with open(orig_path, "r") as f:
                    original_text = f.read()

        doc_edits = edits_by_doc.get(pdf_name, [])

        # 1. Structure check
        structure_ok = _check_document_structure(edited_text, pdf_name)

        # 2. Verify each edit's placement
        for edit in doc_edits:
            result = _verify_single_edit(edit, edited_text, original_text)
            edit_results.append(result)

        # 3. Check for edit interference
        interference = _check_edit_interference(doc_edits, edited_text)

        # 4. LLM coherence check (batch all edits for this doc)
        coherence = _llm_coherence_check(doc_edits, edited_text, pdf_name)

        doc_health[pdf_name] = {
            "status": "ok" if structure_ok else "structural_issues",
            "structure_ok": structure_ok,
            "edit_count": len(doc_edits),
            "interference_issues": interference,
            "coherence": coherence,
            "score": _compute_doc_score(structure_ok, interference, coherence, edit_results)
        }

    # Aggregate results
    passed = sum(1 for r in edit_results if r["verdict"] == "pass")
    failed = sum(1 for r in edit_results if r["verdict"] == "fail")
    flagged = sum(1 for r in edit_results if r["verdict"] == "flag")

    summary = (
        f"Edit verification: {passed}/{len(edit_results)} passed, "
        f"{failed} failed, {flagged} flagged. "
        f"Documents: {sum(1 for d in doc_health.values() if d.get('structure_ok', False))}"
        f"/{len(doc_health)} structurally intact."
    )

    return {
        "verified": failed == 0,
        "total_edits": len(edit_results),
        "passed": passed,
        "failed": failed,
        "flagged": flagged,
        "edit_results": edit_results,
        "document_health": doc_health,
        "summary": summary
    }


# ============================================================
# Individual Edit Verification
# ============================================================

def _verify_single_edit(edit: dict, edited_text: str,
                        original_text: Optional[str] = None) -> dict:
    """Verify a single edit was placed correctly."""
    edit_text = edit.get("new_text", "")
    target_doc = edit.get("target_doc", "")
    question_id = edit.get("question_id", "?")
    track = edit.get("track", "unknown")

    result = {
        "target_doc": target_doc,
        "question_id": question_id,
        "track": track,
        "edit_text_preview": edit_text[:100],
        "checks": {},
        "verdict": "pass",
        "issues": []
    }

    # Check 1: Edit text actually present in document
    # Look for the edit within EDIT-START/EDIT-END markers or as raw text
    marker_pattern = re.compile(
        r'<!-- EDIT-START:.*?-->\s*.*?' + re.escape(edit_text[:60]),
        re.DOTALL
    )
    if edit_text[:80] in edited_text:
        result["checks"]["present"] = True
    elif marker_pattern.search(edited_text):
        result["checks"]["present"] = True
    else:
        result["checks"]["present"] = False
        result["issues"].append("Edit text not found in edited document")
        result["verdict"] = "fail"
        return result

    # Check 2: Edit markers are properly paired
    start_markers = re.findall(
        rf'<!-- EDIT-START: {re.escape(question_id)}.*?-->',
        edited_text
    )
    end_markers = re.findall(
        rf'<!-- EDIT-END: {re.escape(question_id)}.*?-->',
        edited_text
    )
    markers_balanced = len(start_markers) == len(end_markers)
    result["checks"]["markers_balanced"] = markers_balanced
    if not markers_balanced:
        result["issues"].append(
            f"Unbalanced markers: {len(start_markers)} starts, {len(end_markers)} ends"
        )
        result["verdict"] = "flag"

    # Check 3: Edit is in a plausible section (not at very start or very end)
    edit_pos = edited_text.find(edit_text[:60])
    if edit_pos >= 0:
        doc_len = len(edited_text)
        relative_pos = edit_pos / doc_len if doc_len > 0 else 0

        # Check if the edit is within the body (not in first 1% or last 1%)
        # Very start/end suggests bad insertion point
        if relative_pos < 0.01:
            result["checks"]["position"] = "suspicious_start"
            result["issues"].append("Edit placed at very start of document")
            if result["verdict"] == "pass":
                result["verdict"] = "flag"
        elif relative_pos > 0.99:
            result["checks"]["position"] = "suspicious_end"
            result["issues"].append("Edit placed at very end of document")
            if result["verdict"] == "pass":
                result["verdict"] = "flag"
        else:
            result["checks"]["position"] = "ok"

        # Check 4: Context coherence — extract surrounding text
        context_start = max(0, edit_pos - CONTEXT_WINDOW)
        context_end = min(len(edited_text), edit_pos + len(edit_text) + CONTEXT_WINDOW)
        surrounding = edited_text[context_start:context_end]

        # Check if surrounding section headers relate to edit topic
        nearby_headers = re.findall(r'^#{1,4}\s+(.+)$', surrounding, re.MULTILINE)
        result["checks"]["nearby_sections"] = nearby_headers[:3]
    else:
        result["checks"]["position"] = "not_found"

    # Check 5: No duplicate insertions of the same edit
    occurrences = edited_text.count(edit_text[:80])
    if occurrences > 1:
        result["checks"]["duplicated"] = True
        result["issues"].append(f"Edit appears {occurrences} times in document")
        result["verdict"] = "fail"
    else:
        result["checks"]["duplicated"] = False

    return result


# ============================================================
# Document Structure Check
# ============================================================

def _check_document_structure(text: str, pdf_name: str) -> bool:
    """Verify document structure is intact after edits."""
    issues = []

    # Check 1: Headers still present and properly nested
    headers = re.findall(r'^(#{1,6})\s+(.+)$', text, re.MULTILINE)
    if not headers:
        issues.append("No headers found")

    # Check 2: No orphaned HTML comments (unclosed markers)
    open_comments = text.count("<!--")
    close_comments = text.count("-->")
    if open_comments != close_comments:
        issues.append(f"Unbalanced HTML comments: {open_comments} open, {close_comments} close")

    # Check 3: EDIT-START/END markers are balanced globally
    edit_starts = len(re.findall(r'<!-- EDIT-START:', text))
    edit_ends = len(re.findall(r'<!-- EDIT-END:', text))
    if edit_starts != edit_ends:
        issues.append(f"Unbalanced edit markers: {edit_starts} starts, {edit_ends} ends")

    # Check 4: No accidental code block breaks
    triple_backticks = text.count("```")
    if triple_backticks % 2 != 0:
        issues.append("Odd number of ``` markers — possible broken code block")

    # Check 5: Document isn't unexpectedly empty or truncated
    if len(text) < 500:
        issues.append(f"Document suspiciously short: {len(text)} chars")

    if issues:
        print(f"    ⚠ Structure issues in {pdf_name}: {'; '.join(issues)}")
        return False

    return True


# ============================================================
# Edit Interference Detection
# ============================================================

def _check_edit_interference(edits: list[dict], edited_text: str) -> list[str]:
    """Check if multiple edits interfered with each other."""
    issues = []

    # Check for overlapping edit markers
    edit_regions = []
    for match in re.finditer(r'<!-- EDIT-START:.*?-->(.*?)<!-- EDIT-END:.*?-->',
                              edited_text, re.DOTALL):
        edit_regions.append((match.start(), match.end()))

    # Check for nesting (one edit inside another's markers)
    for i, (s1, e1) in enumerate(edit_regions):
        for j, (s2, e2) in enumerate(edit_regions):
            if i != j and s1 < s2 < e1 and e2 > e1:
                issues.append(f"Edit regions {i} and {j} overlap")

    # Check for adjacent edits with no content between them
    for i in range(len(edit_regions) - 1):
        _, end1 = edit_regions[i]
        start2, _ = edit_regions[i + 1]
        between = edited_text[end1:start2].strip()
        if len(between) < 10:
            issues.append(f"Edits {i} and {i+1} have no content between them")

    return issues


# ============================================================
# LLM Coherence Check
# ============================================================

def _llm_coherence_check(edits: list[dict], edited_text: str,
                         pdf_name: str) -> dict:
    """Use LLM to verify edit placement and coherence."""
    if not edits:
        return {"score": 1.0, "issues": []}

    # Build edit summaries with their surrounding context
    edit_contexts = []
    for i, edit in enumerate(edits):
        edit_text = edit.get("new_text", "")[:200]
        pos = edited_text.find(edit_text[:60])
        if pos >= 0:
            ctx_start = max(0, pos - 300)
            ctx_end = min(len(edited_text), pos + len(edit_text) + 300)
            context = edited_text[ctx_start:ctx_end]
            # Mark the edit within context
            edit_contexts.append(
                f"EDIT {i+1} (Q: {edit.get('question_id', '?')}, "
                f"Track: {edit.get('track', '?')}):\n"
                f"---CONTEXT---\n{context}\n---END CONTEXT---\n"
                f"The inserted text is: \"{edit_text}\"\n"
            )

    if not edit_contexts:
        return {"score": 1.0, "issues": []}

    # Limit to avoid token overflow
    context_text = "\n\n".join(edit_contexts[:10])

    try:
        from anthropic import Anthropic
        client = Anthropic(api_key=os.environ.get("ANTHROPIC_API_KEY"))

        response = client.messages.create(
            model=VERIFY_MODEL,
            max_tokens=MAX_TOKENS_VERIFY,
            temperature=0.0,
            system="""You verify that documentation edits have been inserted correctly into technical documents. You check placement, coherence, and accuracy. Output ONLY valid JSON.""",
            messages=[{"role": "user", "content": f"""Review these edits inserted into {pdf_name}. For each edit, verify:

1. PLACEMENT: Is the edit in a relevant section? Does the surrounding content relate to the edit's topic?
2. COHERENCE: Does the document read naturally with the edit? Or does it feel jarring/out of place?
3. ACCURACY: Does the edit contain technical claims that contradict the surrounding text?

{context_text}

Respond with ONLY a JSON object:
{{
    "overall_score": 0.0-1.0,
    "edits": [
        {{
            "edit_number": 1,
            "placement": "correct|misplaced|marginal",
            "coherence": "good|acceptable|poor",
            "contradictions": true/false,
            "issue": "brief description if any problem, else null"
        }}
    ]
}}"""}]
        )

        text = response.content[0].text.strip()

        try:
            from agents.cost_tracker import track_cost
            track_cost("edit_verifier", "—", VERIFY_MODEL,
                       response.usage.input_tokens, response.usage.output_tokens)
        except (ImportError, AttributeError):
            pass

        text = re.sub(r'^```(?:json)?\s*', '', text)
        text = re.sub(r'\s*```$', '', text)
        result = json.loads(text)

        issues = []
        for edit_check in result.get("edits", []):
            if edit_check.get("placement") == "misplaced":
                issues.append(f"Edit {edit_check['edit_number']}: misplaced")
            if edit_check.get("coherence") == "poor":
                issues.append(f"Edit {edit_check['edit_number']}: poor coherence")
            if edit_check.get("contradictions"):
                issues.append(f"Edit {edit_check['edit_number']}: contradicts surrounding text")

        return {
            "score": result.get("overall_score", 0.5),
            "issues": issues,
            "details": result.get("edits", [])
        }

    except Exception as e:
        print(f"    ⚠ LLM coherence check failed: {type(e).__name__}: {e}")
        return {"score": 0.5, "issues": [f"LLM check failed: {e}"]}


# ============================================================
# Scoring
# ============================================================

def _compute_doc_score(structure_ok: bool, interference: list,
                       coherence: dict, edit_results: list) -> float:
    """Compute an overall document health score (0-1)."""
    score = 1.0

    if not structure_ok:
        score -= 0.3

    if interference:
        score -= 0.1 * len(interference)

    coherence_score = coherence.get("score", 0.5)
    score *= coherence_score

    # Factor in individual edit results
    if edit_results:
        pass_rate = sum(1 for r in edit_results if r["verdict"] == "pass") / len(edit_results)
        score *= (0.5 + 0.5 * pass_rate)  # 50% weight on pass rate

    return max(0.0, min(1.0, score))


# ============================================================
# Reporting
# ============================================================

def print_verification_report(report: dict):
    """Print a human-readable verification report."""
    print(f"\n  📋 Edit Verification Report")
    print(f"  {'='*50}")
    print(f"  Total edits: {report['total_edits']}")
    print(f"  ✅ Passed: {report['passed']}")
    print(f"  ❌ Failed: {report['failed']}")
    print(f"  🟡 Flagged: {report['flagged']}")
    print(f"  Overall: {'VERIFIED' if report['verified'] else 'ISSUES FOUND'}")

    for doc, health in report.get("document_health", {}).items():
        score = health.get("score", 0)
        status = "✅" if score > 0.7 else "🟡" if score > 0.4 else "❌"
        print(f"\n  {status} {doc}: score={score:.2f}")
        if health.get("interference_issues"):
            for issue in health["interference_issues"]:
                print(f"      ⚠ {issue}")
        coherence = health.get("coherence", {})
        if coherence.get("issues"):
            for issue in coherence["issues"]:
                print(f"      ⚠ {issue}")

    for result in report.get("edit_results", []):
        if result["verdict"] != "pass":
            icon = "❌" if result["verdict"] == "fail" else "🟡"
            print(f"\n  {icon} Edit for {result['target_doc']} (Q{result['question_id']}):")
            for issue in result.get("issues", []):
                print(f"      - {issue}")

    print(f"\n  {report.get('summary', '')}")
