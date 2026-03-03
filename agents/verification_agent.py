"""
Verification Agent — Claim-Level Answer Verification
=====================================================

Sits between answer generation and evaluation (Step 3b).
Decomposes answers into atomic claims, verifies each claim's
citation actually supports it, and rewrites the answer to
remove unsupported claims.

Three components:
  1. Claim Decomposer — splits answer into atomic claims with citations
  2. Citation Grounding Checker — verifies cited page contains the claim
  3. Answer Rewriter — strips failed claims, moves to DOC_GAPS
"""

import os
import re
import json
from anthropic import Anthropic

# ============================================================
# Configuration
# ============================================================

VERIFY_MODEL = "claude-sonnet-4-5-20250929"  # Cost-efficient for decomposition/rewriting
MAX_TOKENS_DECOMPOSE = 8000
MAX_TOKENS_REWRITE = 6000

# Citation grounding thresholds
MIN_KEY_TERM_MATCHES = 2       # Minimum key terms from claim found on cited page
FUZZY_MATCH_THRESHOLD = 0.5    # Fraction of key terms that must match

# Known problem patterns — claims that contain these AND lack doc support
# are almost certainly overclaims based on historical pipeline runs
KNOWN_OVERCLAIM_PATTERNS = [
    (r'\bEd25519\b', 'sr25519'),           # CLI outputs sr25519, not Ed25519
    (r'\bno centralized coordinator\b', None),  # Docs never state this
    (r'\bcoordinator-free\b', None),
    (r'\bcoordinator.free\b', None),
    (r'\bwithout a centralized\b', None),
    (r'\bwithout any centralized\b', None),
    (r'\bcryptographically verified audit\b', None),  # Docs say "verified data source"
    (r'\bevery (?:data )?operation is auditable\b', None),
    (r'\bno single point of failure\b', None),  # Implied but never stated
]


# ============================================================
# 1. Claim Decomposer
# ============================================================

def decompose_claims(answer_markdown: str, chunks_metadata: dict = None) -> list[dict]:
    """
    Decompose an answer into atomic, individually verifiable claims.
    Each claim preserves its citation.

    Handles BOTH citation formats:
      - [[chunk:p4-0023]]  (from answer_agent)
      - [[doc:File.pdf, p.25]]  (legacy format)

    Args:
        answer_markdown: The answer text with citations
        chunks_metadata: Optional dict mapping chunk_id → {pdf_file, page_start}
                         Used to resolve [[chunk:...]] citations to file/page.

    Returns list of:
    {
        "claim_id": "C001",
        "text": "DDC uses erasure coding with a 16/48 scheme",
        "citation_raw": "[[chunk:p4-0023]]",
        "cited_file": "DDC_from_Sergey_Poluyan.pdf",
        "cited_page": 4,
        "section": "body",
        "claim_type": "factual|definitional|comparative|procedural|inferential"
    }
    """
    try:
        client = Anthropic(api_key=os.environ.get("ANTHROPIC_API_KEY"))

        response = client.messages.create(
            model=VERIFY_MODEL,
            max_tokens=MAX_TOKENS_DECOMPOSE,
            temperature=0.0,
            system="""You extract atomic factual claims from technical documentation answers.
You output ONLY valid JSON arrays. No markdown, no backticks, no commentary.""",
            messages=[{"role": "user", "content": f"""Extract every factual claim from this answer as a JSON array.

For each claim, extract:
- "text": The atomic claim (one fact, one assertion). Keep it short and self-contained.
- "citation_raw": The exact citation string attached to this claim. This could be [[chunk:ID]] or [[doc:X.pdf, p.Y]]. If no citation, use ""
- "claim_type": One of: factual, definitional, comparative, procedural, inferential

RULES:
- Split compound claims: "DDC uses X and Y" → two claims
- SKIP section headers, transitions, meta-text ("In this section we discuss...")
- SKIP the DOC_GAPS section entirely
- SKIP the "What the Documents Do NOT Cover" section
- SKIP the "Planned/Roadmap Items" section
- SKIP the "Citations Summary" section
- SKIP sentences that say "the documents do not specify/address X" — these are NOT claims
- Include ONLY assertions of fact that can be verified against source documents
- Each claim must be independently verifiable
- Preserve the EXACT citation tag (e.g. [[chunk:p4-0023]] or [[doc:File.pdf, p.5]])
- IMPORTANT: Strip hedging prefixes like "The documents suggest that" from claims. Extract the core assertion only.
  Example: "The documents suggest that DDC uses erasure coding" → claim text: "DDC uses erasure coding"
- Do NOT create separate claims for the same fact stated with different wording. Deduplicate.
- Do NOT create claims about what external platforms (AWS, Databricks, Snowflake) do — only claims about what DDC does.
- Preserve the EXACT citation tag (e.g. [[chunk:p4-0023]] or [[doc:File.pdf, p.5]])

ANSWER TO DECOMPOSE:
{answer_markdown}"""}]
        )

        text = response.content[0].text.strip()

        # Track decomposer cost
        try:
            from agents.cost_tracker import track_cost
            track_cost("claim_decomposer", "—", VERIFY_MODEL,
                       response.usage.input_tokens, response.usage.output_tokens)
        except ImportError:
            pass

        # Strip markdown fences if present
        text = re.sub(r'^```(?:json)?\s*', '', text)
        text = re.sub(r'\s*```$', '', text)

        claims = json.loads(text)

        # Normalize and resolve citations
        for i, claim in enumerate(claims):
            claim["claim_id"] = f"C{i+1:03d}"
            claim["citation_raw"] = str(claim.get("citation_raw", "") or "")
            claim["claim_type"] = claim.get("claim_type", "factual")

            # Resolve citation to file/page
            cited_file, cited_page = _resolve_citation(
                claim["citation_raw"], chunks_metadata
            )
            claim["cited_file"] = cited_file
            claim["cited_page"] = cited_page

        print(f"      LLM decomposed {len(claims)} claims")

        # Hard cap: if decomposer extracted too many claims, keep the ones
        # with citations (strongest) and truncate. This prevents evaluation
        # timeouts and excessive verification cost.
        MAX_CLAIMS = 60
        if len(claims) > MAX_CLAIMS:
            # Prioritize claims that have citations
            cited = [c for c in claims if c.get("citation_raw", "")]
            uncited = [c for c in claims if not c.get("citation_raw", "")]
            claims = (cited + uncited)[:MAX_CLAIMS]
            # Re-number
            for i, c in enumerate(claims):
                c["claim_id"] = f"C{i+1:03d}"
            print(f"      Truncated to {MAX_CLAIMS} claims (had {len(cited)} cited)")

        return claims

    except Exception as e:
        print(f"    ⚠ LLM claim decomposition failed ({e}), using regex fallback")
        return _fallback_decompose(answer_markdown, chunks_metadata)


def _resolve_citation(citation_raw: str, chunks_metadata: dict = None) -> tuple:
    """
    Resolve a citation string to (filename, page_number).

    Handles:
      - [[chunk:p4-0023]]     → parse page from chunk ID, lookup file in metadata
      - [[chunk:DDC_Core-p5-0001]] → parse file and page from chunk ID
      - [[doc:File.pdf, p.25]] → direct extraction
    """
    if not citation_raw:
        return "", 0

    # Format 1: [[chunk:CHUNK_ID]]
    chunk_match = re.search(r'\[\[chunk:([^\]]+)\]\]', citation_raw)
    if chunk_match:
        chunk_id = chunk_match.group(1)

        # Try metadata lookup first
        if chunks_metadata and chunk_id in chunks_metadata:
            meta = chunks_metadata[chunk_id]
            return meta.get("pdf_file", ""), int(meta.get("page_start", 0))

        # Parse chunk ID format: "prefix-pN-NNNN" where N is page number
        page_match = re.search(r'-p(\d+)-', chunk_id)
        if page_match:
            page = int(page_match.group(1))
            # Try to extract filename from chunk ID prefix
            # e.g. "DDC_Core_Wiki-p5-0001" → "DDC_Core_Wiki.pdf"
            prefix = chunk_id.split(f"-p{page}")[0]
            if prefix:
                filename = prefix.replace("-", " ").replace("_", " ")
                # Try to match against known PDF files in metadata
                if chunks_metadata:
                    for cid, meta in chunks_metadata.items():
                        pdf = meta.get("pdf_file", "")
                        pdf_stem = pdf.replace(".pdf", "").replace("_", " ").replace("-", " ")
                        if pdf_stem.lower() == filename.lower():
                            return pdf, page
                # Return best guess
                return prefix + ".pdf", page
            return "", page

        return "", 0

    # Format 2: [[doc:File.pdf, p.25]]
    doc_match = re.search(r'\[\[doc:([^,\]]+)(?:,\s*p\.?(\d+))?\]\]', citation_raw)
    if doc_match:
        return doc_match.group(1), int(doc_match.group(2)) if doc_match.group(2) else 0

    return "", 0


def _fallback_decompose(answer_markdown: str, chunks_metadata: dict = None) -> list[dict]:
    """
    Regex-based fallback if LLM decomposition fails.
    Extracts sentences that contain [[chunk:...]] or [[doc:...]] citations.
    """
    claims = []

    # Split into lines
    lines = answer_markdown.split('\n')
    # Stop before non-claim sections
    stop_sections = ['DOC_GAPS', 'Documentation Improvement', 'What the Documents Do NOT Cover',
                     'Planned/Roadmap', 'Citations Summary']

    active = True
    for line in lines:
        for stop in stop_sections:
            if stop.lower() in line.lower():
                active = False
                break
        if not active:
            break

        # Find citations in this line — handle BOTH formats
        cite_matches = list(re.finditer(
            r'\[\[(?:chunk|doc):([^\]]+)\]\]', line
        ))
        if cite_matches:
            # Split line into sentences
            sentences = re.split(r'(?<=[.!?])\s+', line)
            for sent in sentences:
                # Try [[chunk:...]] format first
                cite = re.search(r'\[\[chunk:([^\]]+)\]\]', sent)
                if cite:
                    cited_file, cited_page = _resolve_citation(
                        f"[[chunk:{cite.group(1)}]]", chunks_metadata
                    )
                    claims.append({
                        "claim_id": f"C{len(claims)+1:03d}",
                        "text": sent.strip(),
                        "citation_raw": cite.group(0),
                        "cited_file": cited_file,
                        "cited_page": cited_page,
                        "claim_type": "factual",
                    })
                    continue

                # Try [[doc:...]] format
                cite = re.search(r'\[\[doc:([^,\]]+)(?:,\s*p\.?(\d+))?\]\]', sent)
                if cite:
                    claims.append({
                        "claim_id": f"C{len(claims)+1:03d}",
                        "text": sent.strip(),
                        "citation_raw": cite.group(0),
                        "cited_file": cite.group(1),
                        "cited_page": int(cite.group(2)) if cite.group(2) else 0,
                        "claim_type": "factual",
                    })

    print(f"      Regex fallback extracted {len(claims)} claims")
    return claims


# ============================================================
# 2. Citation Grounding Checker
# ============================================================

def build_page_index(pseudo_chunks: list[dict]) -> dict:
    """
    Build a fast lookup: (filename, page_num) → page_text
    from the pseudo-chunks generated by ingestion.

    Also builds a wider index covering adjacent pages (page-1, page, page+1)
    since content sometimes spans page boundaries.
    """
    index = {}
    for chunk in pseudo_chunks:
        pdf_file = chunk.get("pdf_file", "")
        page_num = chunk.get("page_start", 0)
        text = chunk.get("text", "")
        if pdf_file and page_num and text:
            index[(pdf_file, page_num)] = text
    return index


def _get_page_text(page_index: dict, cited_file: str, cited_page: int,
                   include_adjacent: bool = True) -> str:
    """
    Look up page text with fuzzy filename matching and optional adjacent pages.
    """
    # Direct lookup
    page_text = page_index.get((cited_file, cited_page), "")

    # Try without .pdf extension
    if not page_text:
        for (f, p), text in page_index.items():
            if p == cited_page and (
                cited_file in f or f in cited_file or
                cited_file.replace('.pdf', '') == f.replace('.pdf', '')
            ):
                page_text = text
                cited_file = f  # normalize for adjacent lookup
                break

    if not page_text:
        return ""

    if include_adjacent:
        # Also include adjacent pages (content spans page boundaries)
        prev_text = page_index.get((cited_file, cited_page - 1), "")
        next_text = page_index.get((cited_file, cited_page + 1), "")
        combined = "\n".join(filter(None, [prev_text, page_text, next_text]))
        return combined

    return page_text


def check_citation_grounding(claim: dict, page_index: dict) -> dict:
    """
    Verify that the cited page actually contains content supporting the claim.

    Returns:
        {
            "verdict": "grounded" | "ungrounded" | "mismatch" | "uncited",
            "confidence": float 0-1,
            "matched_terms": [...],
            "missing_terms": [...],
            "detail": "explanation"
        }
    """
    cited_file = claim.get("cited_file", "")
    cited_page = claim.get("cited_page", 0)
    claim_text = claim.get("text", "")

    # ── No citation → uncited ──
    if not cited_file or not cited_page:
        return {
            "verdict": "uncited",
            "confidence": 0.0,
            "matched_terms": [],
            "missing_terms": [],
            "detail": "Claim has no citation to verify."
        }

    # ── Look up the cited page (with adjacent pages for boundary cases) ──
    page_text = _get_page_text(page_index, cited_file, cited_page, include_adjacent=True)

    if not page_text:
        return {
            "verdict": "ungrounded",
            "confidence": 0.0,
            "matched_terms": [],
            "missing_terms": [],
            "detail": f"Page {cited_page} of {cited_file} not found in corpus."
        }

    # ── Check for known overclaim patterns ──
    for pattern, expected_term in KNOWN_OVERCLAIM_PATTERNS:
        match = re.search(pattern, claim_text, re.IGNORECASE)
        if match:
            if expected_term:
                # Claim uses wrong term — check if page has the correct one instead
                page_has_correct = expected_term.lower() in page_text.lower()
                page_has_wrong = bool(re.search(pattern, page_text, re.IGNORECASE))
                if page_has_correct and not page_has_wrong:
                    return {
                        "verdict": "mismatch",
                        "confidence": 0.95,
                        "matched_terms": [],
                        "missing_terms": [match.group()],
                        "detail": (f"Claim uses '{match.group()}' but cited page "
                                   f"uses '{expected_term}' instead.")
                    }
            else:
                # Phrase should exist on cited page but doesn't
                if not re.search(pattern, page_text, re.IGNORECASE):
                    return {
                        "verdict": "mismatch",
                        "confidence": 0.90,
                        "matched_terms": [],
                        "missing_terms": [match.group()],
                        "detail": (f"Claim asserts '{match.group()}' but this phrase "
                                   f"does not appear on the cited page (or adjacent pages).")
                    }

    # ── Extract key terms from the claim ──
    key_terms = _extract_key_terms(claim_text)

    if not key_terms:
        # Can't extract terms even with fallback — flag for review
        return {
            "verdict": "flag",
            "confidence": 0.3,
            "matched_terms": [],
            "missing_terms": [],
            "detail": "No key terms extracted — cannot verify, flagging for review."
        }

    # ── Check how many key terms appear on the cited page ──
    page_lower = page_text.lower()
    matched = []
    missing = []

    for term in key_terms:
        term_lower = term.lower()
        # Try exact match first, then partial for multi-word terms
        if term_lower in page_lower:
            matched.append(term)
        elif len(term_lower.split()) > 1:
            # For multi-word terms, check if all words appear near each other
            words = term_lower.split()
            if all(w in page_lower for w in words):
                matched.append(term)
            else:
                missing.append(term)
        else:
            missing.append(term)

    match_ratio = len(matched) / len(key_terms) if key_terms else 0

    # If ALL terms match (ratio=1.0), always grounded regardless of count
    if match_ratio >= 1.0 and len(matched) >= 1:
        return {
            "verdict": "grounded",
            "confidence": round(match_ratio, 3),
            "matched_terms": matched,
            "missing_terms": missing,
            "detail": f"Found {len(matched)}/{len(key_terms)} key terms on cited page."
        }
    elif match_ratio >= FUZZY_MATCH_THRESHOLD and len(matched) >= MIN_KEY_TERM_MATCHES:
        return {
            "verdict": "grounded",
            "confidence": round(match_ratio, 3),
            "matched_terms": matched,
            "missing_terms": missing,
            "detail": f"Found {len(matched)}/{len(key_terms)} key terms on cited page."
        }
    elif len(matched) >= 1:
        return {
            "verdict": "ungrounded",
            "confidence": round(match_ratio, 3),
            "matched_terms": matched,
            "missing_terms": missing,
            "detail": (f"Only {len(matched)}/{len(key_terms)} key terms found on cited page. "
                       f"Missing: {', '.join(missing[:5])}")
        }
    else:
        return {
            "verdict": "ungrounded",
            "confidence": 0.0,
            "matched_terms": [],
            "missing_terms": missing,
            "detail": f"None of the {len(key_terms)} key terms found on cited page {cited_page}."
        }


def _extract_key_terms(claim_text: str) -> list[str]:
    """
    Extract key technical terms from a claim for grounding verification.
    Returns multi-word phrases and significant single terms.
    """
    # Remove citation markers
    clean = re.sub(r'\[\[doc:[^\]]+\]\]', '', claim_text)
    clean = re.sub(r'\[\[chunk:[^\]]+\]\]', '', clean)
    clean = clean.strip()

    terms = []

    # 1. Quoted strings (exact doc language)
    quoted = re.findall(r'"([^"]{3,})"', clean)
    terms.extend(quoted)
    quoted_single = re.findall(r"'([^']{3,})'", clean)
    terms.extend(quoted_single)

    # 2. Ratios and numeric expressions: 16/48, k=5, 99.99%
    ratios = re.findall(r'\b\d+/\d+\b', clean)
    terms.extend(ratios)
    equations = re.findall(r'[a-zA-Z]=\d+', clean)
    terms.extend(equations)
    percentages = re.findall(r'\d+(?:\.\d+)?%', clean)
    terms.extend(percentages)

    # 3. DDC-specific technical terms
    ddc_patterns = [
        r'erasure[\s-]coding', r'replication[\s-]factor',
        r'DHT', r'Kademlia', r'peer-to-peer', r'P2P',
        r'mnemonic', r'seed[\s-]phrase', r'bucket',
        r'CID', r'content[\s-]identifier',
        r'client-side[\s-]encryption', r'trust[\s-]chain',
        r'Ed25519', r'sr25519', r'Blake2b256',
        r'JWT', r'DAC', r'DdcClient', r'UriSigner',
        r'self-bootstrap', r'disk-persisted',
        r'on-chain', r'off-chain', r'pallet',
        r'Dragon\s*1', r'FileUri', r'content[\s-]?addressed',
        r'data[\s-]?wallet', r'authentication[\s-]?gater',
        r'routing[\s-]?table', r'merkle[\s-]?tree',
        r'plaintext', r'DEK', r'keypair',
    ]
    for pat in ddc_patterns:
        found = re.findall(r'\b' + pat + r'\b', clean, re.IGNORECASE)
        terms.extend(found)

    # 4. Capitalized multi-word phrases (proper nouns, product names)
    cap_phrases = re.findall(r'[A-Z][a-z]+(?:\s+[A-Z][a-z]+)+', clean)
    terms.extend(cap_phrases)

    # 5. ALL-CAPS acronyms
    acronyms = re.findall(r'\b[A-Z]{2,}\b', clean)
    # Filter out common English words that happen to be extracted
    skip = {'THE', 'AND', 'FOR', 'NOT', 'BUT', 'WITH', 'THIS', 'THAT',
            'FROM', 'ARE', 'WAS', 'HAS', 'ITS', 'ANY', 'ALL', 'CAN'}
    terms.extend([a for a in acronyms if a not in skip])

    # Deduplicate, preserve order
    seen = set()
    unique = []
    for t in terms:
        key = t.lower().strip()
        if key and key not in seen and len(key) > 1:
            seen.add(key)
            unique.append(t)

    # 6. FALLBACK: If no terms extracted, extract significant content words
    # This prevents "No key terms extracted — defaulting to grounded" false passes
    if not unique:
        # Remove common stop words and extract remaining content words
        stop_words = {
            'the', 'a', 'an', 'is', 'are', 'was', 'were', 'be', 'been',
            'being', 'have', 'has', 'had', 'do', 'does', 'did', 'will',
            'would', 'could', 'should', 'may', 'might', 'must', 'shall',
            'can', 'to', 'of', 'in', 'for', 'on', 'with', 'at', 'by',
            'from', 'as', 'into', 'through', 'during', 'before', 'after',
            'above', 'below', 'between', 'out', 'off', 'up', 'down',
            'that', 'this', 'these', 'those', 'it', 'its', 'any', 'all',
            'each', 'every', 'both', 'few', 'more', 'most', 'other',
            'some', 'such', 'no', 'nor', 'not', 'only', 'own', 'same',
            'so', 'than', 'too', 'very', 'just', 'because', 'but', 'and',
            'or', 'if', 'when', 'while', 'where', 'how', 'what', 'which',
            'who', 'whom', 'why', 'then', 'once', 'here', 'there',
            'also', 'about', 'over', 'under', 'again', 'further',
            'documents', 'suggest', 'document', 'suggests', 'stated',
            'according', 'described', 'mentioned', 'indicates', 'notes',
        }
        words = re.findall(r'\b[a-zA-Z]{3,}\b', clean)
        content_words = [w for w in words if w.lower() not in stop_words]
        # Take the most significant words (longer = more specific)
        content_words.sort(key=lambda w: len(w), reverse=True)
        unique = content_words[:3]  # Top 3 most significant words

    return unique


# ============================================================
# 3. Answer Rewriter
# ============================================================

def rewrite_answer(answer_data: dict, verified_claims: list[dict]) -> dict:
    """
    Produce a corrected answer:
    - Remove failed claims from the answer body
    - Soften flagged claims
    - Append failed claims to DOC_GAPS
    """
    failed = [c for c in verified_claims if c.get("final_verdict") == "fail"]
    flagged = [c for c in verified_claims if c.get("final_verdict") == "flag"]

    if not failed and not flagged:
        return answer_data

    try:
        client = Anthropic(api_key=os.environ.get("ANTHROPIC_API_KEY"))

        failed_desc = "\n".join(
            f"- REMOVE: \"{c['text'][:120]}\" — Reason: {c.get('grounding', {}).get('detail', 'ungrounded')}"
            for c in failed
        ) or "None"

        flagged_desc = "\n".join(
            f"- SOFTEN: \"{c['text'][:120]}\" — Reason: {c.get('grounding', {}).get('detail', 'weak evidence')}"
            for c in flagged
        ) or "None"

        new_gaps = "\n".join(
            f"- **GAP:** \"{c['text'][:120]}\" was asserted but the cited source "
            f"({c.get('cited_file', '?')}, p.{c.get('cited_page', '?')}) does not support it. "
            f"{c.get('grounding', {}).get('detail', '')}"
            for c in failed
        )

        response = client.messages.create(
            model=VERIFY_MODEL,
            max_tokens=MAX_TOKENS_REWRITE,
            temperature=0.0,
            system="""You correct technical documentation answers by removing or softening specific claims.
You preserve all other content exactly. You output only the corrected answer.""",
            messages=[{"role": "user", "content": f"""Correct this answer with the following changes. Keep ALL other content identical — same structure, same citations, same headers.

ORIGINAL ANSWER:
{answer_data['answer_markdown']}

CLAIMS TO REMOVE (delete these sentences/phrases entirely from the answer body):
{failed_desc}

CLAIMS TO SOFTEN (reword to "The documents suggest..." or "This is implied but not explicitly stated..."):
{flagged_desc}

APPEND THESE TO THE DOC_GAPS SECTION (add after existing gaps):
{new_gaps}

RULES:
1. Keep all passing claims and their citations EXACTLY as-is
2. Do NOT add new claims or content
3. Do NOT change any citations
4. Preserve the exact section structure
5. If removing a claim leaves an awkward paragraph, clean up the flow
6. Softened claims should still cite the same source
7. Return ONLY the corrected answer text — no meta commentary"""}]
        )

        corrected_text = response.content[0].text.strip()

        # Track rewriter cost
        try:
            from agents.cost_tracker import track_cost
            track_cost("answer_rewriter", "—", VERIFY_MODEL,
                       response.usage.input_tokens, response.usage.output_tokens)
        except ImportError:
            pass

        # Update doc_gaps in the answer data structure too
        existing_gaps = answer_data.get("doc_gaps", [])
        for c in failed:
            existing_gaps.append({
                "gap": c["text"][:200],
                "implication": f"Claim cited {c.get('cited_file', '?')} p.{c.get('cited_page', '?')} but was not grounded.",
                "recommendation": c.get("grounding", {}).get("detail", ""),
                "source": "verification_agent",
            })

        return {
            **answer_data,
            "answer_markdown": corrected_text,
            "doc_gaps": existing_gaps,
            "verification_applied": True,
            "claims_removed": len(failed),
            "claims_softened": len(flagged),
        }

    except Exception as e:
        print(f"    ⚠ Answer rewrite failed: {e} — applying regex fallback")
        return _fallback_rewrite(answer_data, failed, flagged)


def _fallback_rewrite(answer_data: dict, failed: list, flagged: list) -> dict:
    """
    Regex-based fallback rewriter. Less graceful but still removes bad claims.
    """
    corrected = answer_data["answer_markdown"]

    for claim in failed:
        claim_text = claim.get("text", "")
        if len(claim_text) < 10:
            continue
        # Try to find a sentence containing the core of this claim
        # Take first 60 chars as search anchor
        anchor = re.escape(claim_text[:60])
        # Remove the sentence containing this anchor
        pattern = rf'[^.!?\n]*{anchor}[^.!?\n]*[.!?]?\s*'
        corrected = re.sub(pattern, '', corrected, count=1)

    return {
        **answer_data,
        "answer_markdown": corrected,
        "verification_applied": True,
        "claims_removed": len(failed),
        "claims_softened": 0,
    }


# ============================================================
# Main Pipeline Entry Point
# ============================================================

def verify_answer(question_id: str, answer_data: dict,
                  pseudo_chunks: list[dict],
                  full_text: str = None) -> dict:
    """
    Full triple-verification pipeline for a single answer.

    Three verification layers (all optional, graceful degradation):
      1. Citation Grounding (local, zero cost) — checks key terms on cited page
      2. NLI Entailment (local DeBERTa, zero API cost) — checks semantic entailment
      3. Cross-LLM (Gemini/GPT, low API cost) — independent provider verification

    Verdict Aggregator combines all signals via weighted majority voting.

    Args:
        question_id: e.g. "Q1"
        answer_data: Dict from answer_agent with answer_markdown, etc.
        pseudo_chunks: Pseudo-chunks from ingestion (used for page index)
        full_text: Full corpus text (unused for now, reserved for expansion)

    Returns:
        {
            "verified_answer": <corrected answer_data dict>,
            "claims": [list of claims with verdicts],
            "stats": {total, passed, failed, flagged, verifiers_active}
        }
    """
    print(f"    Decomposing {question_id} into atomic claims...")
    # Build chunks_metadata for citation resolution
    chunks_metadata = {}
    for chunk in pseudo_chunks:
        chunks_metadata[chunk.get("chunk_id", "")] = {
            "pdf_file": chunk.get("pdf_file", ""),
            "page_start": chunk.get("page_start", 0),
        }
    claims = decompose_claims(answer_data["answer_markdown"], chunks_metadata)
    print(f"    → {len(claims)} atomic claims extracted")

    # Build page index for citation grounding
    page_index = build_page_index(pseudo_chunks)
    print(f"    → Page index: {len(page_index)} pages indexed")

    # ── Initialize optional verifiers ──
    nli_available = False
    nli_verifier = None
    cross_llm_available = False
    cross_llm_checker = None

    # NLI verifier
    try:
        from agents.nli_verifier import get_nli_verifier
        nli_verifier = get_nli_verifier()
        nli_available = True
    except ImportError:
        try:
            from nli_verifier import get_nli_verifier
            nli_verifier = get_nli_verifier()
            nli_available = True
        except ImportError:
            pass
    if nli_available:
        print(f"    → NLI verifier: active")
    else:
        print(f"    → NLI verifier: not available")

    # Cross-LLM checker
    try:
        from agents.cross_llm_checker import get_cross_llm_checker
        cross_llm_checker = get_cross_llm_checker()
        cross_llm_available = cross_llm_checker.available
    except ImportError:
        try:
            from cross_llm_checker import get_cross_llm_checker
            cross_llm_checker = get_cross_llm_checker()
            cross_llm_available = cross_llm_checker.available
        except ImportError:
            pass
    if cross_llm_available:
        print(f"    → Cross-LLM checker: active")
    else:
        print(f"    → Cross-LLM checker: not available")

    # Import aggregator
    try:
        from agents.cross_llm_checker import aggregate_verdicts
    except ImportError:
        try:
            from cross_llm_checker import aggregate_verdicts
        except ImportError:
            aggregate_verdicts = None

    verifiers_active = ["grounding"]
    if nli_available:
        verifiers_active.append("nli")
    if cross_llm_available:
        verifiers_active.append("cross_llm")

    print(f"    → Active verifiers: {', '.join(verifiers_active)}")

    # ══════════════════════════════════════════════
    # Layer 1: Citation Grounding (always runs)
    # ══════════════════════════════════════════════
    for claim in claims:
        grounding = check_citation_grounding(claim, page_index)
        claim["grounding"] = grounding

    # ══════════════════════════════════════════════
    # Layer 2: NLI Verification (batch)
    # ══════════════════════════════════════════════
    if nli_available and nli_verifier:
        nli_claims = []
        nli_evidences = []
        nli_indices = []

        for i, claim in enumerate(claims):
            if claim.get("cited_file") and claim.get("cited_page"):
                evidence_text = _get_page_text(
                    page_index, claim["cited_file"], claim["cited_page"],
                    include_adjacent=True
                )
                if evidence_text:
                    nli_claims.append(claim["text"])
                    nli_evidences.append(evidence_text)
                    nli_indices.append(i)

        if nli_claims:
            print(f"    Running NLI on {len(nli_claims)} claims...")
            try:
                nli_results = nli_verifier.check_batch(nli_claims, nli_evidences)
                for idx, nli_result in zip(nli_indices, nli_results):
                    claims[idx]["nli"] = nli_result
            except Exception as e:
                print(f"    ⚠ NLI batch failed: {e}")

    # ══════════════════════════════════════════════
    # Layer 3: Cross-LLM Verification (batch)
    # ══════════════════════════════════════════════
    if cross_llm_available and cross_llm_checker:
        cited_claims = [c for c in claims if c.get("cited_file") and c.get("cited_page")]
        if cited_claims:
            print(f"    Running cross-LLM on {len(cited_claims)} claims...")
            try:
                cross_results = cross_llm_checker.check_batch(cited_claims, page_index)
                # Map results back
                cited_idx = 0
                for claim in claims:
                    if claim.get("cited_file") and claim.get("cited_page"):
                        if cited_idx < len(cross_results):
                            claim["cross_llm"] = cross_results[cited_idx]
                            cited_idx += 1
            except Exception as e:
                print(f"    ⚠ Cross-LLM batch failed: {e}")

    # ══════════════════════════════════════════════
    # Aggregate all signals into final verdicts
    # ══════════════════════════════════════════════
    passed = 0
    failed = 0
    flagged = 0

    for claim in claims:
        if aggregate_verdicts:
            result = aggregate_verdicts(claim)
            claim["final_verdict"] = result["final_verdict"]
            claim["final_confidence"] = result["final_confidence"]
            claim["aggregation"] = result
        else:
            # Fallback: use grounding only
            g = claim.get("grounding", {}).get("verdict", "uncited")
            if g == "grounded":
                claim["final_verdict"] = "pass"
            elif g in ("mismatch", "ungrounded") and claim.get("grounding", {}).get("confidence", 0) == 0:
                claim["final_verdict"] = "fail"
            elif g == "ungrounded":
                claim["final_verdict"] = "flag"
            else:
                claim["final_verdict"] = "pass"

        v = claim["final_verdict"]
        if v == "pass":
            passed += 1
        elif v == "fail":
            failed += 1
            detail = claim.get("aggregation", {}).get("reasoning", claim.get("grounding", {}).get("detail", ""))
            print(f"      ❌ {claim['claim_id']}: FAIL — {detail}")
        elif v == "flag":
            flagged += 1
            detail = claim.get("aggregation", {}).get("reasoning", "")
            print(f"      🟡 {claim['claim_id']}: FLAG — {detail}")

    print(f"    → Verdicts: ✅ {passed} passed | ❌ {failed} failed | 🟡 {flagged} flagged")

    # ══════════════════════════════════════════════
    # Rewrite answer if needed
    # ══════════════════════════════════════════════
    if failed > 0 or flagged > 0:
        print(f"    Rewriting answer (removing {failed}, softening {flagged})...")
        verified_answer = rewrite_answer(answer_data, claims)
        print(f"    → Answer corrected")
    else:
        verified_answer = answer_data
        print(f"    → Answer clean — no corrections needed")

    return {
        "verified_answer": verified_answer,
        "claims": claims,
        "stats": {
            "total": len(claims),
            "passed": passed,
            "failed": failed,
            "flagged": flagged,
            "verifiers_active": verifiers_active,
        }
    }


# ============================================================
# Test
# ============================================================

if __name__ == "__main__":
    print("=== Citation Grounding Checker Test ===\n")

    test_index = {
        ("Get Started with DDC.pdf", 3): (
            "Account creation via CLI: npx @cere-ddc-sdk/cli account --random\n"
            "Output: mnemonic, key type: sr25519, address, public key\n"
            "Store this mnemonic securely. Anyone with this phrase has full control."
        ),
        ("DDC Core Wiki.pdf", 25): (
            "Data redundancy uses replication for small pieces and erasure coding "
            "for pieces larger than 16KB. Dragon 1 cluster uses a 16/48 erasure "
            "coding scheme. Any 16 of 48 shares can reconstruct the original data."
        ),
        ("DDC Core Wiki.pdf", 12): (
            "DHT-based peer discovery with replication factor k=5. "
            "Nodes can self-bootstrap using themselves as bootstrap node. "
            "Routing table is cached on disk."
        ),
    }

    test_cases = [
        {
            "claim_id": "T1",
            "text": "Your data wallet is an Ed25519 keypair derived from the seed phrase",
            "cited_file": "Get Started with DDC.pdf",
            "cited_page": 3,
            "claim_type": "definitional",
        },
        {
            "claim_id": "T2",
            "text": "Dragon 1 uses a 16/48 erasure coding scheme",
            "cited_file": "DDC Core Wiki.pdf",
            "cited_page": 25,
            "claim_type": "factual",
        },
        {
            "claim_id": "T3",
            "text": "DDC operates without a centralized coordinator",
            "cited_file": "DDC Core Wiki.pdf",
            "cited_page": 12,
            "claim_type": "inferential",
        },
        {
            "claim_id": "T4",
            "text": "Nodes use DHT with replication factor k=5",
            "cited_file": "DDC Core Wiki.pdf",
            "cited_page": 12,
            "claim_type": "factual",
        },
    ]

    for tc in test_cases:
        result = check_citation_grounding(tc, test_index)
        status = {"grounded": "✅", "ungrounded": "❌", "mismatch": "⚠️", "uncited": "❓"}
        icon = status.get(result["verdict"], "?")
        print(f"  {icon} {tc['claim_id']}: {result['verdict']} ({result['confidence']:.0%})")
        print(f"     Claim: {tc['text'][:80]}")
        print(f"     Detail: {result['detail']}")
        if result['matched_terms']:
            print(f"     Matched: {', '.join(result['matched_terms'][:5])}")
        if result['missing_terms']:
            print(f"     Missing: {', '.join(result['missing_terms'][:5])}")
        print()
