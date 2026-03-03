"""
Doc Editor Agent — Inline Markdown Editing with Annotated Review
=================================================================

Takes verified doc gaps + markdown source files and produces:
  1. EDITED markdown files with insertions inline
  2. An HTML review page showing all edits with color-coded status
  3. An APPROVED edits manifest for automatic feedback into next run

Three-track confidence system:
  AUTO-APPLY     : Info already in docs (reorganization) OR externally confirmed
                   with high confidence. Edit inserted directly, marked ✅.
                   Feeds back into next pipeline run automatically.
  FLAGGED        : Externally confirmed with medium confidence. Edit inserted
                   but marked 🟡 for spot-check. Feeds back unless rejected.
  MANUAL-ONLY    : Unverified or low confidence. Shown in review HTML as
                   proposal only. Does NOT feed back until human approves.

The approved edits are written to knowledge/approved_edits.json. On the next
run, ingestion checks for this file and merges approved edits into the
full_text before sending to the answer agent.
"""

import os
import json
import re
import time
from pathlib import Path
from datetime import datetime
from dotenv import load_dotenv
import yaml

load_dotenv()

# ── Approval tracks ──
TRACK_AUTO = "auto"          # Applied + feeds back automatically
TRACK_FLAGGED = "flagged"    # Applied + feeds back, but marked for spot-check
TRACK_MANUAL = "manual"      # Proposal only — needs human approval

APPROVED_EDITS_PATH = "knowledge/approved_edits.json"


def apply_edits(gap_report: dict, markdown_files: dict,
                evaluation_reports: list[dict] = None,
                config_path: str = "config/pipeline_config.yaml") -> dict:
    """
    Apply verified gap patches to markdown source files.

    Returns:
        {
            "edited_files": {pdf_name: edited_markdown_path},
            "review_html": str,
            "edit_count": int,
            "auto_applied": int,
            "flagged": int,
            "manual_only": int,
            "edits": [...],
            "approved_edits_path": str,
        }
    """
    verified_gaps = gap_report.get("verified_gaps", [])
    if not verified_gaps:
        return {
            "edited_files": {}, "review_html": "", "edit_count": 0,
            "auto_applied": 0, "flagged": 0, "manual_only": 0,
            "edits": [], "approved_edits_path": "",
        }

    # Group gaps by target document
    gaps_by_doc = {}
    for vg in verified_gaps:
        target = vg.get("verified_patch", {}).get("target_document", "")
        matched_file = _match_doc_to_file(target, markdown_files)
        if matched_file:
            if matched_file not in gaps_by_doc:
                gaps_by_doc[matched_file] = []
            gaps_by_doc[matched_file].append(vg)

    # Apply edits to each document
    all_edits = []
    edited_files = {}
    output_dir = "knowledge/edited_markdown"
    os.makedirs(output_dir, exist_ok=True)

    for pdf_name, gaps in gaps_by_doc.items():
        md_path = markdown_files.get(pdf_name)
        if not md_path or not os.path.exists(md_path):
            continue

        # Check for existing _EDITED.md — if it exists, layer new edits on top
        edited_name = pdf_name.replace('.pdf', '_EDITED.md').replace(' ', '_')
        existing_edited = os.path.join(output_dir, edited_name)
        if os.path.exists(existing_edited):
            print(f"    Layering edits onto existing {edited_name}")
            with open(existing_edited, "r", errors="ignore") as f:
                base_text = f.read()
        else:
            with open(md_path, "r") as f:
                base_text = f.read()

        edited_text = base_text
        doc_edits = []

        for vg in gaps:
            patch = vg.get("verified_patch", {})
            # Determine approval track
            track = _determine_track(vg)

            # Dedup: skip if this gap's content is already in the document
            # Check both the new text and the gap description to catch near-duplicates
            new_text = patch.get("new_text", "")
            gap_desc = vg.get("gap", {}).get("description", "")[:100] if isinstance(vg.get("gap"), dict) else str(vg.get("gap", ""))[:100]
            
            skip = False
            if new_text and new_text[:150] in edited_text:
                print(f"    Skipping duplicate edit (text match): {new_text[:60]}...")
                skip = True
            elif gap_desc and gap_desc[:80] in edited_text:
                print(f"    Skipping duplicate edit (gap match): {gap_desc[:60]}...")
                skip = True
            if skip:
                continue

            edit_result = _apply_single_edit(edited_text, vg, patch, pdf_name, track)
            if edit_result:
                edited_text = edit_result["edited_text"]
                doc_edits.append(edit_result["edit_metadata"])

        # Save edited markdown (accumulates over runs)
        edited_path = os.path.join(output_dir, edited_name)
        with open(edited_path, "w") as f:
            f.write(edited_text)

        edited_files[pdf_name] = edited_path
        all_edits.extend(doc_edits)

    # Write approved edits manifest (auto + flagged feed back into next run)
    approved = [e for e in all_edits if e["track"] in (TRACK_AUTO, TRACK_FLAGGED)]
    _save_approved_edits(approved)

    # Generate HTML review page
    review_html_path = _generate_review_html(all_edits, edited_files, output_dir)

    auto_count = sum(1 for e in all_edits if e["track"] == TRACK_AUTO)
    flagged_count = sum(1 for e in all_edits if e["track"] == TRACK_FLAGGED)
    manual_count = sum(1 for e in all_edits if e["track"] == TRACK_MANUAL)

    return {
        "edited_files": edited_files,
        "review_html": review_html_path,
        "edit_count": len(all_edits),
        "auto_applied": auto_count,
        "flagged": flagged_count,
        "manual_only": manual_count,
        "edits": all_edits,
        "approved_edits_path": APPROVED_EDITS_PATH,
    }


def _determine_track(verified_gap: dict) -> str:
    """
    Determine which approval track an edit belongs to.

    AUTO:    Internal evidence found — info IS in docs, just needs reorganization.
             This is safe because we're not adding new claims.
    FLAGGED: Externally confirmed — new claim, but verified by outside sources.
             Feeds back but needs spot-check. Human can reject.
    MANUAL:  Unverified, contradicted, or low confidence.
             Proposal only — blocked until human approves.
    """
    internal = verified_gap.get("internal_evidence", {})
    external = verified_gap.get("external_evidence", {})

    internal_found = internal.get("found", False)
    ext_verdict = external.get("verdict", "unverified")
    ext_confidence = external.get("confidence", "low")

    # Track 1: Already in docs — ONLY case that auto-applies
    # This is safe: we're reorganizing existing content, not adding new claims
    if internal_found:
        return TRACK_AUTO

    # Track 2: Externally confirmed — new info, needs spot-check
    if ext_verdict == "confirmed":
        return TRACK_FLAGGED

    # Everything else: manual review required
    return TRACK_MANUAL


def _save_approved_edits(approved_edits: list[dict]):
    """
    Save approved edits to a manifest file.
    ACCUMULATES edits across runs — previous verified edits are kept,
    and new edits are merged in. Duplicates are detected by matching
    target_doc + new_text content. This enables the self-healing loop
    to build richer source material over time.
    """
    os.makedirs(os.path.dirname(APPROVED_EDITS_PATH), exist_ok=True)

    timestamp = datetime.now().isoformat()
    for edit in approved_edits:
        edit["approved_at"] = timestamp
        edit["status"] = "approved"

    # Load existing edits
    existing = []
    if os.path.exists(APPROVED_EDITS_PATH):
        try:
            with open(APPROVED_EDITS_PATH, "r") as f:
                existing = json.load(f)
            if not isinstance(existing, list):
                existing = []
        except (json.JSONDecodeError, Exception):
            existing = []

    # Build dedup keys from existing edits
    existing_keys = set()
    for e in existing:
        key = (e.get("target_doc", ""), e.get("new_text", "")[:150])
        existing_keys.add(key)

    # Add new edits that aren't duplicates
    added = 0
    for edit in approved_edits:
        key = (edit.get("target_doc", ""), edit.get("new_text", "")[:150])
        if key not in existing_keys:
            existing.append(edit)
            existing_keys.add(key)
            added += 1

    # Cap total edits to prevent unbounded growth
    MAX_TOTAL_EDITS = 100
    if len(existing) > MAX_TOTAL_EDITS:
        # Keep most recent edits (they're more relevant to current doc state)
        existing = existing[-MAX_TOTAL_EDITS:]

    with open(APPROVED_EDITS_PATH, "w") as f:
        json.dump(existing, f, indent=2, default=str)

    if added > 0:
        print(f"  ✓ Accumulated {added} new edits (total: {len(existing)})")


def load_approved_edits() -> list[dict]:
    """
    Load approved edits manifest for ingestion to merge.
    Called by ingestion_agent during Tier 1 full_text construction.
    """
    if not os.path.exists(APPROVED_EDITS_PATH):
        return []

    with open(APPROVED_EDITS_PATH, "r") as f:
        edits = json.load(f)

    # Only return non-rejected edits
    return [e for e in edits if e.get("status") != "rejected"]


def reject_edit(edit_index: int):
    """
    Mark an edit as rejected (won't feed back into next run).
    Called by human reviewer.
    """
    if not os.path.exists(APPROVED_EDITS_PATH):
        return

    with open(APPROVED_EDITS_PATH, "r") as f:
        edits = json.load(f)

    if 0 <= edit_index < len(edits):
        edits[edit_index]["status"] = "rejected"
        edits[edit_index]["rejected_at"] = datetime.now().isoformat()

    with open(APPROVED_EDITS_PATH, "w") as f:
        json.dump(edits, f, indent=2, default=str)


def approve_manual_edit(edit_index: int):
    """
    Manually approve a MANUAL-track edit so it feeds back.
    Called by human reviewer.
    """
    if not os.path.exists(APPROVED_EDITS_PATH):
        return

    with open(APPROVED_EDITS_PATH, "r") as f:
        edits = json.load(f)

    if 0 <= edit_index < len(edits):
        edits[edit_index]["status"] = "approved"
        edits[edit_index]["approved_at"] = datetime.now().isoformat()

    with open(APPROVED_EDITS_PATH, "w") as f:
        json.dump(edits, f, indent=2, default=str)


def _match_doc_to_file(target_name: str, markdown_files: dict) -> str:
    """Match a target document name to an actual file in markdown_files."""
    target_lower = target_name.lower().replace(" ", "").replace("_", "")

    for pdf_name in markdown_files:
        pdf_lower = pdf_name.lower().replace(" ", "").replace("_", "").replace(".pdf", "")
        if target_lower in pdf_lower or pdf_lower in target_lower:
            return pdf_name

    # Fuzzy match on key words
    target_words = set(re.findall(r'\w+', target_name.lower()))
    best_match = None
    best_overlap = 0
    for pdf_name in markdown_files:
        pdf_words = set(re.findall(r'\w+', pdf_name.lower()))
        overlap = len(target_words & pdf_words)
        if overlap > best_overlap:
            best_overlap = overlap
            best_match = pdf_name

    return best_match if best_overlap >= 2 else None


def _apply_single_edit(text: str, verified_gap: dict, patch: dict,
                        pdf_name: str, track: str) -> dict:
    """Apply a single verified gap as an inline edit."""
    gap_text = verified_gap.get("gap", "")
    implication = verified_gap.get("implication", "")
    suggested_text = patch.get("suggested_text", "")
    citations = patch.get("citations", [])
    verification_status = patch.get("verification_status", "unverified")
    question_id = verified_gap.get("question_id", "?")

    if not suggested_text or "[REORGANIZE]" in suggested_text:
        return None

    # Clean up meta-markers
    clean_text = re.sub(r'\[VERIFIED by:.*?\]', '', suggested_text).strip()
    clean_text = re.sub(r'\[TODO:.*?\]', '', clean_text).strip()
    clean_text = re.sub(r'External context:.*$', '', clean_text, flags=re.MULTILINE).strip()

    if not clean_text:
        return None

    # Find best insertion point
    insertion_point = _find_insertion_point(text, verified_gap)
    if insertion_point < 0:
        last_sep = text.rfind("\n---\n")
        insertion_point = last_sep if last_sep > 0 else len(text)

    # Build annotated insertion block
    citation_str = " | ".join(citations) if citations else "no sources"
    track_marker = {
        TRACK_AUTO: "✅ AUTO-APPLIED",
        TRACK_FLAGGED: "🟡 FLAGGED (spot-check recommended)",
        TRACK_MANUAL: "🔴 PROPOSAL ONLY (needs human approval)",
    }[track]

    annotation = (
        f"\n\n<!-- EDIT-START: {question_id} | track: {track} | {track_marker} -->\n"
        f"<!-- GAP: {gap_text[:120]} -->\n"
        f"<!-- SOURCES: {citation_str} -->\n"
        f"\n{clean_text}\n"
        f"\n<!-- EDIT-END: {question_id} -->\n"
    )

    edited_text = text[:insertion_point] + annotation + text[insertion_point:]

    # Context for review
    context_start = max(0, insertion_point - 150)
    context_end = min(len(text), insertion_point + 150)
    original_context = text[context_start:context_end].strip()

    edit_metadata = {
        "target_doc": pdf_name,
        "question_id": question_id,
        "page": _guess_page_number(text, insertion_point),
        "edit_type": "insertion",
        "original_context": original_context,
        "new_text": clean_text,
        "citations": citations,
        "rationale": f"Gap: {gap_text}",
        "implication": implication,
        "verification_status": verification_status,
        "track": track,
    }

    return {"edited_text": edited_text, "edit_metadata": edit_metadata}


def _find_insertion_point(text: str, verified_gap: dict) -> int:
    """Find the best place to insert text based on gap context."""
    gap_text = verified_gap.get("gap", "")
    internal = verified_gap.get("internal_evidence", {})

    if internal.get("found") and internal.get("text"):
        snippet = internal["text"][:80]
        idx = text.find(snippet)
        if idx >= 0:
            next_para = text.find("\n\n", idx)
            if next_para >= 0:
                return next_para

    key_terms = re.findall(r'\b[A-Z][a-z]+(?:\s+[a-z]+){0,2}\b', gap_text)
    key_terms += re.findall(r'\b(?:coordinator|DHT|bootstrap|encryption|key|blockchain|node|wallet)\b',
                            gap_text, re.IGNORECASE)

    for term in key_terms:
        idx = text.lower().find(term.lower())
        if idx >= 0:
            next_para = text.find("\n\n", idx)
            if next_para >= 0:
                return next_para

    return -1


def _guess_page_number(text: str, position: int) -> int:
    """Guess which page a position corresponds to."""
    preceding = text[:position]
    page_markers = re.findall(r'<!-- PAGE (\d+) -->', preceding)
    if page_markers:
        return int(page_markers[-1])
    page_headings = re.findall(r'## Page (\d+)', preceding)
    if page_headings:
        return int(page_headings[-1])
    return 0


def _generate_review_html(all_edits: list[dict], edited_files: dict,
                           output_dir: str) -> str:
    """Generate HTML review page with three-track color coding."""
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M")

    auto_count = sum(1 for e in all_edits if e["track"] == TRACK_AUTO)
    flagged_count = sum(1 for e in all_edits if e["track"] == TRACK_FLAGGED)
    manual_count = sum(1 for e in all_edits if e["track"] == TRACK_MANUAL)

    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>DDC Documentation — Edit Review</title>
<style>
  @import url('https://fonts.googleapis.com/css2?family=IBM+Plex+Sans:wght@400;500;600&family=IBM+Plex+Mono:wght@400;500&display=swap');
  :root {{
    --bg: #0f1117; --surface: #1a1d27; --border: #2a2d3a;
    --text: #e2e4e9; --text-muted: #8b8fa3;
    --green: #3dd68c; --green-bg: rgba(61,214,140,0.08); --green-border: rgba(61,214,140,0.25);
    --amber: #f0a83a; --amber-bg: rgba(240,168,58,0.08); --amber-border: rgba(240,168,58,0.25);
    --red: #ef5f5f; --red-bg: rgba(239,95,95,0.08); --red-border: rgba(239,95,95,0.25);
    --blue: #5b9cf5; --purple: #a78bfa; --purple-bg: rgba(167,139,250,0.08);
  }}
  * {{ margin: 0; padding: 0; box-sizing: border-box; }}
  body {{ font-family: 'IBM Plex Sans', sans-serif; background: var(--bg); color: var(--text);
         line-height: 1.6; padding: 2rem; max-width: 1000px; margin: 0 auto; }}
  .header {{ border-bottom: 1px solid var(--border); padding-bottom: 1.5rem; margin-bottom: 2rem; }}
  .header h1 {{ font-size: 1.4rem; font-weight: 600; letter-spacing: -0.02em; margin-bottom: 0.25rem; }}
  .header .meta {{ color: var(--text-muted); font-size: 0.85rem; }}
  .stats {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(160px, 1fr)); gap: 0.75rem; margin-bottom: 1.5rem; }}
  .stat {{ background: var(--surface); border: 1px solid var(--border); border-radius: 8px; padding: 0.85rem 1rem; }}
  .stat .label {{ font-size: 0.7rem; color: var(--text-muted); text-transform: uppercase; letter-spacing: 0.05em; }}
  .stat .value {{ font-size: 1.6rem; font-weight: 600; font-family: 'IBM Plex Mono', monospace; }}
  .stat.auto .value {{ color: var(--green); }}
  .stat.flagged .value {{ color: var(--amber); }}
  .stat.manual .value {{ color: var(--red); }}
  .legend {{ background: var(--surface); border: 1px solid var(--border); border-radius: 8px;
             padding: 1rem 1.25rem; margin-bottom: 2rem; font-size: 0.85rem; }}
  .legend h3 {{ font-size: 0.8rem; text-transform: uppercase; letter-spacing: 0.05em;
                color: var(--text-muted); margin-bottom: 0.6rem; }}
  .legend-item {{ display: flex; align-items: center; gap: 0.6rem; margin-bottom: 0.35rem; }}
  .legend-dot {{ width: 10px; height: 10px; border-radius: 50%; flex-shrink: 0; }}
  .legend-dot.auto {{ background: var(--green); }}
  .legend-dot.flagged {{ background: var(--amber); }}
  .legend-dot.manual {{ background: var(--red); }}
  .edit-card {{ background: var(--surface); border: 1px solid var(--border); border-radius: 10px;
               margin-bottom: 1.25rem; overflow: hidden; }}
  .edit-card.track-auto {{ border-left: 3px solid var(--green); }}
  .edit-card.track-flagged {{ border-left: 3px solid var(--amber); }}
  .edit-card.track-manual {{ border-left: 3px solid var(--red); }}
  .edit-header {{ padding: 0.75rem 1.25rem; border-bottom: 1px solid var(--border);
                 display: flex; justify-content: space-between; align-items: center; flex-wrap: wrap; gap: 0.5rem; }}
  .edit-header .doc {{ font-weight: 500; font-size: 0.9rem; }}
  .edit-header .doc .num {{ color: var(--text-muted); font-family: 'IBM Plex Mono'; font-size: 0.8rem; }}
  .badges {{ display: flex; gap: 0.4rem; flex-wrap: wrap; }}
  .badge {{ font-size: 0.65rem; padding: 0.2rem 0.55rem; border-radius: 4px; font-weight: 500;
           font-family: 'IBM Plex Mono', monospace; }}
  .badge.auto {{ background: var(--green-bg); color: var(--green); border: 1px solid var(--green-border); }}
  .badge.flagged {{ background: var(--amber-bg); color: var(--amber); border: 1px solid var(--amber-border); }}
  .badge.manual {{ background: var(--red-bg); color: var(--red); border: 1px solid var(--red-border); }}
  .badge.question {{ background: var(--purple-bg); color: var(--purple); border: 1px solid rgba(167,139,250,0.25); }}
  .edit-body {{ padding: 1.25rem; }}
  .rationale {{ font-size: 0.85rem; color: var(--text-muted); margin-bottom: 1rem;
               padding-left: 0.75rem; border-left: 2px solid var(--border); }}
  .context-label, .insertion-label {{ font-size: 0.7rem; text-transform: uppercase; letter-spacing: 0.06em;
                                     color: var(--text-muted); margin-bottom: 0.35rem; font-weight: 500; }}
  .context {{ background: var(--bg); padding: 0.85rem 1rem; border-radius: 6px;
             font-family: 'IBM Plex Mono', monospace; font-size: 0.78rem; color: var(--text-muted);
             margin-bottom: 1rem; white-space: pre-wrap; border: 1px solid var(--border); }}
  .insertion {{ padding: 0.85rem 1rem; border-radius: 6px; margin-bottom: 1rem;
              white-space: pre-wrap; font-size: 0.88rem; position: relative; padding-left: 1.5rem; }}
  .insertion.auto {{ background: var(--green-bg); border: 1px solid var(--green-border); }}
  .insertion.flagged {{ background: var(--amber-bg); border: 1px solid var(--amber-border); }}
  .insertion.manual {{ background: var(--red-bg); border: 1px solid var(--red-border); }}
  .insertion::before {{ content: "+"; position: absolute; left: 0.4rem; top: 0.85rem;
                       font-weight: 700; font-family: 'IBM Plex Mono', monospace; font-size: 0.9rem; }}
  .insertion.auto::before {{ color: var(--green); }}
  .insertion.flagged::before {{ color: var(--amber); }}
  .insertion.manual::before {{ color: var(--red); }}
  .sources {{ margin-top: 0.5rem; }}
  .sources-label {{ font-size: 0.7rem; text-transform: uppercase; letter-spacing: 0.06em;
                   color: var(--text-muted); margin-bottom: 0.35rem; }}
  .source-badge {{ display: inline-flex; align-items: center; gap: 0.3rem; background: var(--bg);
                  border: 1px solid var(--border); color: var(--text-muted); padding: 0.2rem 0.6rem;
                  border-radius: 4px; font-size: 0.75rem; margin-right: 0.35rem; margin-bottom: 0.25rem;
                  font-family: 'IBM Plex Mono', monospace; text-decoration: none; }}
  a.source-badge:hover {{ border-color: var(--blue); color: var(--blue); }}
  .footer {{ margin-top: 3rem; padding-top: 1.5rem; border-top: 1px solid var(--border);
            color: var(--text-muted); font-size: 0.8rem; text-align: center; }}
</style>
</head>
<body>
<div class="header">
  <h1>📝 DDC Documentation — Edit Review</h1>
  <div class="meta">Generated: {timestamp} · {len(all_edits)} edits across {len(edited_files)} documents</div>
</div>

<div class="stats">
  <div class="stat auto"><div class="label">Auto-Applied</div><div class="value">{auto_count}</div></div>
  <div class="stat flagged"><div class="label">Flagged (Spot-Check)</div><div class="value">{flagged_count}</div></div>
  <div class="stat manual"><div class="label">Manual Review</div><div class="value">{manual_count}</div></div>
</div>

<div class="legend">
  <h3>How edits are processed</h3>
  <div class="legend-item"><span class="legend-dot auto"></span> <strong>Auto-applied</strong> — Already in docs (reorg) or externally confirmed. Feeds into next pipeline run automatically.</div>
  <div class="legend-item"><span class="legend-dot flagged"></span> <strong>Flagged</strong> — Medium confidence. Applied automatically but review recommended. Reject via CLI if wrong.</div>
  <div class="legend-item"><span class="legend-dot manual"></span> <strong>Manual only</strong> — Unverified. Shown as proposal. Must be approved before feeding back.</div>
</div>
"""

    for i, edit in enumerate(all_edits, 1):
        track = edit.get("track", TRACK_MANUAL)
        track_badge = f'<span class="badge {track}">{track.upper()}</span>'
        q_badge = f'<span class="badge question">{edit["question_id"]}</span>'

        citations_html = ""
        for c in edit.get("citations", []):
            if c.startswith("[external:"):
                url = c.replace("[external: ", "").rstrip("]")
                citations_html += f'<a href="{url}" target="_blank" class="source-badge">🌐 {_html_escape(url[:50])}</a> '
            else:
                citations_html += f'<span class="source-badge">📄 {_html_escape(c)}</span> '

        html += f"""
<div class="edit-card track-{track}">
  <div class="edit-header">
    <span class="doc"><span class="num">#{i}</span> {_html_escape(edit['target_doc'])} · p.{edit.get('page', '?')}</span>
    <span class="badges">{q_badge} {track_badge}</span>
  </div>
  <div class="edit-body">
    <div class="rationale">{_html_escape(edit.get('rationale', ''))}</div>
    <div class="context-label">Original context</div>
    <div class="context">{_html_escape(edit.get('original_context', '')[:300])}</div>
    <div class="insertion-label">{'Applied edit' if track != TRACK_MANUAL else 'Proposed edit'}</div>
    <div class="insertion {track}">{_html_escape(edit.get('new_text', ''))}</div>
    <div class="sources"><div class="sources-label">Sources</div>{citations_html if citations_html else '<em>none</em>'}</div>
  </div>
</div>
"""

    html += """
<div class="footer">
  DDC Documentation Evaluator · Three-track edit system<br>
  Auto + flagged edits feed into next run. Use <code>reject_edit(index)</code> or <code>approve_manual_edit(index)</code> to manage.
</div>
</body></html>"""

    review_path = os.path.join(output_dir, "edit_review.html")
    with open(review_path, "w") as f:
        f.write(html)

    return review_path


def _html_escape(text: str) -> str:
    return (text.replace("&", "&amp;").replace("<", "&lt;")
                .replace(">", "&gt;").replace('"', "&quot;"))


if __name__ == "__main__":
    print("Doc editor agent ready — three-track confidence system")
    print(f"  AUTO:    Applied + auto-feedback")
    print(f"  FLAGGED: Applied + auto-feedback (spot-check)")
    print(f"  MANUAL:  Proposal only (needs approval)")

