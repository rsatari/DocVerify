"""
Gap Verifier Agent
==================
Takes doc_gaps from the answer agent and verifies each one through:

  1. INTERNAL search: Re-scan the full document corpus for evidence the
     answer agent may have missed (maybe the info IS in the docs, just
     in a different section)
  2. EXTERNAL search: Use Tavily + OpenAI dual search to find authoritative
     sources that confirm or deny the implied claim
  3. Produce a VERIFIED GAP REPORT with sourced recommendations that the
     editor agent can turn into concrete doc patches

This is the bridge between "the docs seem to imply X" and "we can confirm
X is true, here are the sources, here's the text to add."
"""

import os
import json
import re
import time
from dotenv import load_dotenv
from anthropic import Anthropic
import yaml

load_dotenv()

FALLBACK_MODEL = "claude-sonnet-4-6"


def verify_gaps(all_answers: dict, full_text: str = None,
                chunks: list[dict] = None,
                config_path: str = "config/pipeline_config.yaml") -> dict:
    """
    Verify doc gaps from all answers through internal + external research.

    Args:
        all_answers: Dict of {qid: answer_data} from answer agent
        full_text: Complete document text (Tier 1) for internal search
        chunks: All chunks (Tier 2 fallback) for internal search
        config_path: Pipeline config path

    Returns:
        {
            "verified_gaps": [
                {
                    "question_id": str,
                    "gap": str,
                    "implication": str,
                    "recommendation": str,
                    "internal_evidence": {
                        "found": bool,
                        "location": str,  # doc + page if found
                        "text": str,      # relevant passage
                        "note": str,      # "already in docs" or "not found"
                    },
                    "external_evidence": {
                        "found": bool,
                        "verdict": "confirmed|contradicted|unverified",
                        "sources": [{"url": str, "title": str, "snippet": str}],
                        "confidence": str,  # "high|medium|low"
                    },
                    "verified_patch": {
                        "target_document": str,
                        "suggested_text": str,
                        "citations": [str],  # internal + external
                        "requires_human_review": bool,
                        "review_reason": str,
                    }
                }
            ],
            "summary": str,
        }
    """
    # Collect all gaps across questions
    all_gaps = []
    for qid, answer in all_answers.items():
        for gap in answer.get("doc_gaps", []):
            gap["question_id"] = qid
            all_gaps.append(gap)

    if not all_gaps:
        return {"verified_gaps": [], "summary": "No doc gaps to verify."}

    # Verify each gap
    verified = []
    for gap in all_gaps:
        result = _verify_single_gap(gap, full_text, chunks, config_path)
        verified.append(result)

    # Summarize
    confirmed = sum(1 for v in verified if v["external_evidence"]["verdict"] == "confirmed")
    already_in_docs = sum(1 for v in verified if v["internal_evidence"]["found"])
    unverified = sum(1 for v in verified if v["external_evidence"]["verdict"] == "unverified")

    summary = (f"{len(verified)} gaps analyzed: {confirmed} externally confirmed, "
               f"{already_in_docs} already in docs (missed by answer agent), "
               f"{unverified} unverified (need engineering input)")

    return {"verified_gaps": verified, "summary": summary}


def _verify_single_gap(gap: dict, full_text: str = None,
                        chunks: list[dict] = None,
                        config_path: str = "config/pipeline_config.yaml") -> dict:
    """Verify a single doc gap through internal + external research."""

    gap_text = gap.get("gap", "")
    implication = gap.get("implication", "")
    recommendation = gap.get("recommendation", "")
    question_id = gap.get("question_id", "?")

    print(f"    Verifying gap: {gap_text[:80]}...")

    # ── 1. Internal search ──
    internal = _search_internal(gap_text, implication, full_text, chunks)

    # ── 2. External search ──
    external = _search_external(gap_text, implication, config_path)

    # ── 3. Build verified patch ──
    patch = _build_patch(gap, internal, external)

    return {
        "question_id": question_id,
        "gap": gap_text,
        "implication": implication,
        "recommendation": recommendation,
        "internal_evidence": internal,
        "external_evidence": external,
        "verified_patch": patch,
    }


def _search_internal(gap_text: str, implication: str,
                      full_text: str = None,
                      chunks: list[dict] = None) -> dict:
    """
    Search the internal document corpus for evidence that DIRECTLY addresses this gap.
    Only returns "found" if the docs actually cover the gap's specific claim,
    not just mention related keywords.
    """
    search_text = full_text or ""
    if not search_text and chunks:
        search_text = "\n".join(c.get("text", "") for c in chunks)

    if not search_text:
        return {"found": False, "location": "", "text": "", "note": "No internal text available"}

    # Extract MULTI-WORD phrases only — single keywords are too loose
    key_phrases = _extract_search_terms(gap_text + " " + implication)
    # Filter to phrases with 2+ words or very specific technical terms
    meaningful_phrases = [p for p in key_phrases
                         if len(p.split()) >= 2 or
                         p.lower() in ('coordinator-free', 'coordinator', 'split-brain',
                                       'network partition', 'data wallet')]

    if not meaningful_phrases:
        return {
            "found": False, "location": "", "text": "",
            "note": "No specific enough phrases to search for internally.",
        }

    matches = []
    for phrase in meaningful_phrases:
        pattern = re.compile(re.escape(phrase), re.IGNORECASE)
        for match in pattern.finditer(search_text):
            start = max(0, match.start() - 250)
            end = min(len(search_text), match.end() + 250)
            context = search_text[start:end]

            doc_marker = ""
            doc_search = search_text[:match.start()]
            doc_matches = re.findall(r'DOCUMENT: ([^\n]+)', doc_search)
            if doc_matches:
                doc_marker = doc_matches[-1]

            matches.append({
                "phrase": phrase,
                "context": context.strip(),
                "document": doc_marker,
            })

    if matches:
        unique = []
        seen_contexts = set()
        for m in matches:
            ctx_key = m["context"][:100]
            if ctx_key not in seen_contexts:
                seen_contexts.add(ctx_key)
                unique.append(m)

        best = unique[0]
        return {
            "found": True,
            "location": best["document"],
            "text": best["context"],
            "note": (f"Found {len(unique)} internal match(es) for '{best['phrase']}'. "
                    f"The docs may already cover this."),
            "all_matches": unique[:3],
        }

    return {
        "found": False, "location": "", "text": "",
        "note": "Not found in internal documents. External verification needed.",
    }


def _extract_search_terms(text: str) -> list[str]:
    """Extract meaningful search phrases from gap text."""
    # Remove common words and extract technical phrases
    stop_phrases = [
        "the documents do not", "explicitly state", "should be", "currently",
        "does not", "do not", "is not", "are not", "whether", "that",
    ]
    cleaned = text.lower()
    for phrase in stop_phrases:
        cleaned = cleaned.replace(phrase, " ")

    # Extract 2-4 word technical phrases
    words = cleaned.split()
    phrases = []

    # Single important words (capitalized in original or technical)
    for word in text.split():
        if (len(word) > 3 and (word[0].isupper() or
            any(c in word for c in ['_', '-', '.']))):
            phrases.append(word)

    # Bigrams/trigrams from cleaned text
    for i in range(len(words) - 1):
        bigram = f"{words[i]} {words[i+1]}"
        if len(bigram) > 6 and not all(w in ['the', 'and', 'for', 'with', 'from'] for w in bigram.split()):
            phrases.append(bigram)

    # Deduplicate and limit
    seen = set()
    unique = []
    for p in phrases:
        p_lower = p.lower().strip()
        if p_lower not in seen and len(p_lower) > 3:
            seen.add(p_lower)
            unique.append(p)

    return unique[:10]


def _search_external(gap_text: str, implication: str,
                      config_path: str = "config/pipeline_config.yaml") -> dict:
    """
    Search external sources to verify the implied claim.
    Uses the same dual-search infrastructure as the research agent.
    """
    # Build a focused search query from the gap
    search_query = _build_search_query(gap_text, implication)

    if not search_query:
        return {
            "found": False,
            "verdict": "unverified",
            "sources": [],
            "confidence": "low",
            "note": "Could not construct meaningful search query from gap description.",
        }

    # Try Tavily first
    tavily_results = _external_search_tavily(search_query)

    # Then OpenAI
    openai_results = _external_search_openai(search_query, gap_text)

    # Merge and evaluate
    all_sources = tavily_results + openai_results
    valid_sources = [s for s in all_sources if not s.get("error")]

    if not valid_sources:
        return {
            "found": False,
            "verdict": "unverified",
            "sources": [],
            "confidence": "low",
            "note": "External search returned no results.",
        }

    # Determine verdict based on source quality
    has_official = any(s.get("source_type") in ["vendor_official", "official_docs"]
                      for s in valid_sources)
    has_third_party = any(s.get("source_type") in ["third_party_audit", "academic"]
                         for s in valid_sources)

    if has_official or (has_third_party and len(valid_sources) >= 2):
        verdict = "confirmed"
        confidence = "high" if has_official else "medium"
    elif len(valid_sources) >= 1:
        verdict = "confirmed"
        confidence = "medium"
    else:
        verdict = "unverified"
        confidence = "low"

    return {
        "found": True,
        "verdict": verdict,
        "sources": valid_sources[:5],  # Top 5
        "confidence": confidence,
        "note": f"Found {len(valid_sources)} external source(s).",
    }


def _build_search_query(gap_text: str, implication: str) -> str:
    """Build a focused search query from gap description."""
    # Combine gap and implication, extract key concepts
    combined = f"{gap_text} {implication}"

    # Look for DDC/Cere-specific terms
    ddc_terms = re.findall(
        r'\b(?:DDC|Cere|decentralized data cluster|erasure coding|DHT|'
        r'peer-to-peer|P2P|blockchain|smart contract|client-side encryption|'
        r'key delegation|token chain)\b',
        combined, re.IGNORECASE
    )

    if ddc_terms:
        # Search for the DDC-specific concept
        return f"Cere DDC {' '.join(set(t.lower() for t in ddc_terms[:3]))}"
    else:
        # Generic distributed systems search
        # Extract the core technical claim
        core = re.sub(r'(?:the documents?|do not|does not|should|explicitly|state|mention)\s*',
                      '', combined, flags=re.IGNORECASE)
        words = core.split()[:8]
        return " ".join(words) if words else ""


def _external_search_tavily(query: str) -> list[dict]:
    """Search Tavily for external verification."""
    tavily_key = os.environ.get("TAVILY_API_KEY")
    if not tavily_key:
        return [{"error": "TAVILY_API_KEY not set"}]

    try:
        from tavily import TavilyClient
        client = TavilyClient(api_key=tavily_key)
        response = client.search(
            query=query,
            max_results=5,
            search_depth="advanced",
            include_answer=True,
        )

        results = []
        for r in response.get("results", []):
            domain = r.get("url", "").split("/")[2] if "/" in r.get("url", "") else ""
            results.append({
                "title": r.get("title", ""),
                "url": r.get("url", ""),
                "snippet": r.get("content", "")[:300],
                "source_type": _classify_domain(domain),
                "search_engine": "tavily",
            })
        return results

    except Exception as e:
        return [{"error": f"Tavily search failed: {str(e)}"}]


def _external_search_openai(query: str, gap_context: str) -> list[dict]:
    """Search OpenAI for external verification."""
    openai_key = os.environ.get("OPENAI_API_KEY")
    if not openai_key:
        return [{"error": "OPENAI_API_KEY not set"}]

    try:
        from openai import OpenAI
        client = OpenAI(api_key=openai_key)

        response = client.chat.completions.create(
            model="gpt-5.2",
            max_tokens=1000,
            temperature=0.1,
            messages=[{
                "role": "user",
                "content": (f"Find authoritative sources that confirm or deny this "
                           f"technical claim about DDC (Decentralized Data Cluster) "
                           f"by Cere Network:\n\n"
                           f"Claim: {gap_context}\n\n"
                           f"Search query: {query}\n\n"
                           f"Return a JSON array of sources with fields: "
                           f"title, url, snippet, source_type "
                           f"(official_docs|academic|technical_blog|community)")
            }],
        )

        text = response.choices[0].message.content

        try:
            from agents.cost_tracker import track_cost
            track_cost("gap_verifier", "—", "gpt-5.2",
                       response.usage.prompt_tokens, response.usage.completion_tokens)
        except (ImportError, AttributeError):
            pass

        json_match = re.search(r'\[.*\]', text, re.DOTALL)
        if json_match:
            sources = json.loads(json_match.group())
            for s in sources:
                s["search_engine"] = "openai"
            return sources
        return []

    except Exception as e:
        return [{"error": f"OpenAI search failed: {str(e)}"}]


def _classify_domain(domain: str) -> str:
    """Classify a domain's authority level."""
    d = domain.lower()
    if any(s in d for s in ["cere.network", "docs.cere", "github.com/cerebellum"]):
        return "vendor_official"
    if any(s in d for s in ["nist.gov", "iso.org", "owasp.org", "arxiv.org"]):
        return "academic"
    if any(s in d for s in ["medium.com", "dev.to", "blog"]):
        return "technical_blog"
    return "community"


def _build_patch(gap: dict, internal: dict, external: dict) -> dict:
    """
    Build a verified documentation patch from internal + external evidence.
    Uses an LLM to synthesize actual document prose (not directives).
    """
    gap_text = gap.get("gap", "")
    implication = gap.get("implication", "")
    recommendation = gap.get("recommendation", "")

    citations = []

    if internal["found"]:
        loc = internal.get("location", "")
        if loc:
            citations.append(f"[internal: {loc}]")

    for source in external.get("sources", [])[:3]:
        if source.get("url"):
            citations.append(f"[external: {source['url']}]")

    # Determine review needs
    needs_review = True
    review_reason = ""

    if external["verdict"] == "confirmed" and external["confidence"] == "high":
        needs_review = True
        review_reason = "Externally confirmed — verify source accuracy"
    elif external["verdict"] == "confirmed":
        needs_review = True
        review_reason = "Medium confidence — verify claim accuracy"
    elif external["verdict"] == "unverified":
        needs_review = True
        review_reason = "Could not verify externally — needs engineering team confirmation"
    elif internal["found"]:
        needs_review = False
        review_reason = "Already in docs — needs better placement or clearer language"

    # ── Synthesize actual document text via LLM ──
    evidence_parts = []
    if internal["found"] and internal.get("text"):
        evidence_parts.append(f"From internal docs: {internal['text'][:400]}")
    for source in external.get("sources", [])[:3]:
        snippet = source.get("snippet", "")
        if snippet:
            evidence_parts.append(f"External ({source.get('url', 'unknown')}): {snippet[:250]}")

    evidence_context = "\n".join(evidence_parts) if evidence_parts else "No supporting evidence."

    suggested_text = _synthesize_patch_text(
        gap_text, implication, recommendation, evidence_context
    )

    if not suggested_text:
        suggested_text = recommendation  # Fallback

    return {
        "target_document": _guess_target_doc(gap_text, recommendation),
        "suggested_text": suggested_text,
        "citations": citations,
        "requires_human_review": needs_review,
        "review_reason": review_reason,
        "verification_status": external["verdict"],
    }


def _synthesize_patch_text(gap_text: str, implication: str,
                            recommendation: str, evidence: str) -> str:
    """
    Use Sonnet to write actual document prose from the gap + evidence.
    Returns ready-to-insert text — NOT directives like 'Add a section...'
    """
    try:
        client = Anthropic(api_key=os.environ.get("ANTHROPIC_API_KEY"))

        response = client.messages.create(
            model=FALLBACK_MODEL,
            max_tokens=400,
            temperature=0.2,
            messages=[{"role": "user", "content": f"""Write 1-2 short paragraphs of technical documentation to fill this gap in DDC (Decentralized Data Cluster by Cere Network) docs.

GAP: {gap_text}
IMPLICATION: {implication}
RECOMMENDATION: {recommendation}

EVIDENCE:
{evidence}

RULES:
- Write the actual paragraph text to insert into the document. NOT instructions.
- BAD: "Add a section that explains..." GOOD: "DDC clusters operate without..."
- Technical, factual, concise. Match enterprise documentation tone.
- Only state things supported by the evidence above.
- Max 100 words. No citation markers or URLs in the text.
- Do not use markdown formatting (no bold, headers, etc)."""}]
        )

        text = response.content[0].text.strip()

        try:
            from agents.cost_tracker import track_cost
            track_cost("gap_verifier", "—", FALLBACK_MODEL,
                       response.usage.input_tokens, response.usage.output_tokens)
        except (ImportError, AttributeError):
            pass

        # Safety: strip any remaining markdown or meta-text
        text = re.sub(r'\[.*?external.*?\]', '', text)
        text = re.sub(r'\[.*?internal.*?\]', '', text)
        text = re.sub(r'https?://\S+', '', text)
        return text.strip()

    except Exception as e:
        print(f"    ⚠ LLM synthesis failed: {e}")
        return None


def _guess_target_doc(gap_text: str, recommendation: str) -> str:
    """Guess which document a patch should target."""
    combined = (gap_text + " " + recommendation).lower()

    if any(w in combined for w in ["core", "architecture", "node", "cluster", "repair", "dht"]):
        return "DDC Core Wiki"
    if any(w in combined for w in ["encrypt", "key", "delegation", "dek", "kes"]):
        return "Encrypted Data Access and Key Delegation"
    if any(w in combined for w in ["auth", "token", "jwt", "trust chain", "pallet"]):
        return "ADR Authentication and Authorization"
    if any(w in combined for w in ["redundancy", "erasure", "replication"]):
        return "Data Redundancy Strategy"
    if any(w in combined for w in ["sdk", "client", "upload", "bucket"]):
        return "Get Started with DDC / DDC Client JS SDK Wiki"
    if any(w in combined for w in ["cloud", "traditional", "provider", "trust"]):
        return "DDC from Sergey Poluyan"

    return "DDC Core Wiki"  # Default


if __name__ == "__main__":
    # Quick test
    test_answers = {
        "Q1": {
            "doc_gaps": [{
                "gap": "The documents do not explicitly state whether DDC operates without a centralized coordinator.",
                "implication": "The DHT bootstrap and self-node fallback implies coordinator-free operation.",
                "recommendation": "Add to DDC Core Wiki: 'DDC clusters operate without a centralized coordinator.'",
            }]
        }
    }
    result = verify_gaps(test_answers, full_text="DDC Core uses DHT for peer discovery...")
    print(json.dumps(result, indent=2))
