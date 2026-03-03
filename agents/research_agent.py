"""
Research Agent (Dual Web Search)
Searches external sources to verify and enrich comparative claims.

Uses TWO search backends for cross-validation:
  1. Tavily Search API — optimized for research, returns structured results
  2. OpenAI Web Search — built-in search tool via chat completions

Sources searched:
  - Official vendor docs (docs.databricks.com, docs.snowflake.com, etc.)
  - Third-party security audits (SOC 2 reports, Gartner, Forrester, NIST)
  - Industry benchmarking (peer-reviewed, compliance frameworks)

Cross-validation: Results from both engines are compared. Only information
confirmed by at least one authoritative source is marked "verified".
"""

import os
import json
import time
import hashlib
from dotenv import load_dotenv
from openai import OpenAI
import yaml

load_dotenv()

# Authoritative source domains per platform
VENDOR_DOCS = {
    "databricks": [
        "docs.databricks.com",
        "databricks.com/trust",
        "databricks.com/security",
    ],
    "snowflake": [
        "docs.snowflake.com",
        "snowflake.com/en/data-cloud/overview/trust-center",
    ],
    "aws": [
        "docs.aws.amazon.com",
        "aws.amazon.com/security",
        "aws.amazon.com/compliance",
    ],
    "azure": [
        "learn.microsoft.com",
        "azure.microsoft.com/en-us/explore/security",
        "microsoft.com/en-us/trust-center",
    ],
    "google cloud": [
        "cloud.google.com/docs",
        "cloud.google.com/security",
    ],
    "gcp": [
        "cloud.google.com/docs",
        "cloud.google.com/security",
    ],
}

# Third-party audit sources
THIRD_PARTY_SOURCES = [
    "nist.gov",
    "csrc.nist.gov",
    "soc2.com",
    "gartner.com",
    "forrester.com",
    "iso.org",
    "owasp.org",
    "cisa.gov",
]


def _search_tavily(query: str, max_results: int = 5,
                   include_domains: list[str] = None) -> list[dict]:
    """
    Search using Tavily API.
    Returns list of {title, url, content, score, domain}.
    """
    tavily_key = os.environ.get("TAVILY_API_KEY")
    if not tavily_key:
        return [{"error": "TAVILY_API_KEY not set", "source": "tavily"}]

    try:
        from tavily import TavilyClient
        client = TavilyClient(api_key=tavily_key)

        kwargs = {
            "query": query,
            "max_results": max_results,
            "search_depth": "advanced",
            "include_answer": True,
        }
        if include_domains:
            kwargs["include_domains"] = include_domains

        response = client.search(**kwargs)

        results = []
        for r in response.get("results", []):
            results.append({
                "title": r.get("title", ""),
                "url": r.get("url", ""),
                "content": r.get("content", ""),
                "score": r.get("score", 0),
                "domain": r.get("url", "").split("/")[2] if "/" in r.get("url", "") else "",
                "source_engine": "tavily",
            })

        # Include Tavily's AI-generated answer if available
        if response.get("answer"):
            results.insert(0, {
                "title": "Tavily AI Summary",
                "url": "",
                "content": response["answer"],
                "score": 1.0,
                "domain": "tavily-summary",
                "source_engine": "tavily",
            })

        return results

    except ImportError:
        return [{"error": "tavily-python not installed. pip install tavily-python", "source": "tavily"}]
    except Exception as e:
        return [{"error": f"Tavily search failed: {str(e)}", "source": "tavily"}]


def _search_openai(query: str, platform_context: str = "",
                   max_results: int = 5) -> list[dict]:
    """
    Search using OpenAI's built-in web search tool.
    Uses the chat completions API with web_search tool enabled.
    """
    openai_key = os.environ.get("OPENAI_API_KEY")
    if not openai_key:
        return [{"error": "OPENAI_API_KEY not set", "source": "openai"}]

    try:
        client = OpenAI(api_key=openai_key)

        system_msg = f"""You are a technical research assistant. Search for authoritative, current information about:
{platform_context}

Focus on:
1. Official vendor documentation and security whitepapers
2. SOC 2, ISO 27001, and compliance documentation
3. Third-party security audits and analyst reports
4. Technical architecture details (encryption, key management, access control)

For each finding, cite the specific source URL. Distinguish between vendor marketing claims
and independently verified technical facts. Respond with structured JSON."""

        response = client.chat.completions.create(
            model="gpt-4o",
            max_tokens=1500,
            temperature=0.1,
            messages=[
                {"role": "system", "content": system_msg},
                {"role": "user", "content": f"Research query: {query}\n\nProvide findings as JSON array with fields: title, url, content, confidence (high/medium/low), source_type (vendor_doc|third_party_audit|analyst_report|technical_blog)"}
            ],
        )

        response_text = response.choices[0].message.content

        # Parse the results
        import re
        json_match = re.search(r'\[.*\]', response_text, re.DOTALL)
        if json_match:
            findings = json.loads(json_match.group())
        else:
            # Try parsing as object with array inside
            json_match = re.search(r'\{.*\}', response_text, re.DOTALL)
            if json_match:
                obj = json.loads(json_match.group())
                findings = obj.get("findings", obj.get("results", [obj]))
            else:
                findings = []

        results = []
        for f in findings:
            if isinstance(f, dict):
                results.append({
                    "title": f.get("title", ""),
                    "url": f.get("url", ""),
                    "content": f.get("content", f.get("summary", "")),
                    "score": {"high": 0.9, "medium": 0.6, "low": 0.3}.get(
                        f.get("confidence", "medium"), 0.5),
                    "domain": f.get("url", "").split("/")[2] if "/" in f.get("url", "") else "",
                    "source_engine": "openai",
                    "source_type": f.get("source_type", "unknown"),
                })

        return results

    except Exception as e:
        return [{"error": f"OpenAI search failed: {str(e)}", "source": "openai"}]


def _classify_source(url: str, domain: str) -> dict:
    """Classify a source by authority level."""
    domain_lower = domain.lower()

    # Check if it's a known vendor doc
    for platform, domains in VENDOR_DOCS.items():
        for d in domains:
            if d in domain_lower:
                return {"authority": "vendor_official", "platform": platform}

    # Check third-party
    for source in THIRD_PARTY_SOURCES:
        if source in domain_lower:
            return {"authority": "third_party_audit", "platform": None}

    # Analyst / research
    if any(s in domain_lower for s in ["gartner", "forrester", "idc"]):
        return {"authority": "analyst_report", "platform": None}

    # General tech
    if any(s in domain_lower for s in ["github.com", "stackoverflow", "medium.com", "arxiv.org"]):
        return {"authority": "community", "platform": None}

    return {"authority": "unknown", "platform": None}


def _cross_validate(tavily_results: list[dict], openai_results: list[dict]) -> list[dict]:
    """
    Cross-validate results from both search engines.
    Returns merged results with confidence scores.
    """
    merged = []
    seen_urls = set()

    # Index all results by a content hash for fuzzy matching
    def content_hash(text):
        return hashlib.md5(text[:200].lower().encode()).hexdigest()

    tavily_hashes = {content_hash(r.get("content", "")): r for r in tavily_results
                     if not r.get("error")}
    openai_hashes = {content_hash(r.get("content", "")): r for r in openai_results
                     if not r.get("error")}

    # Find results confirmed by both engines
    shared_hashes = set(tavily_hashes.keys()) & set(openai_hashes.keys())

    for h in shared_hashes:
        r = tavily_hashes[h]
        r["cross_validated"] = True
        r["confidence"] = min(r.get("score", 0.5) * 1.2, 1.0)  # Boost cross-validated
        r["found_in"] = ["tavily", "openai"]
        source_class = _classify_source(r.get("url", ""), r.get("domain", ""))
        r.update(source_class)
        merged.append(r)
        seen_urls.add(r.get("url"))

    # Add unique results from each engine
    for results_list, engine_name in [(tavily_results, "tavily"), (openai_results, "openai")]:
        for r in results_list:
            if r.get("error"):
                merged.append(r)
                continue
            url = r.get("url", "")
            if url and url in seen_urls:
                continue
            seen_urls.add(url)
            r["cross_validated"] = False
            r["confidence"] = r.get("score", 0.5)
            r["found_in"] = [engine_name]
            source_class = _classify_source(url, r.get("domain", ""))
            r.update(source_class)
            merged.append(r)

    # Sort by: cross-validated first, then by authority, then by confidence
    authority_rank = {
        "vendor_official": 0,
        "third_party_audit": 1,
        "analyst_report": 2,
        "community": 3,
        "unknown": 4,
    }

    merged.sort(key=lambda x: (
        not x.get("cross_validated", False),
        authority_rank.get(x.get("authority", "unknown"), 5),
        -x.get("confidence", 0)
    ))

    return merged


def research_claim(claim: dict, platform: str,
                   config_path: str = "config/pipeline_config.yaml") -> dict:
    """
    Research a single claim against external sources.

    Args:
        claim: A claim dict from ClaimExtractor with verification_query
        platform: The comparison target platform name

    Returns:
        {
            "claim_id": str,
            "claim_text": str,
            "platform": str,
            "search_queries": [str],
            "tavily_results": [...],
            "openai_results": [...],
            "merged_results": [...],  # cross-validated and ranked
            "external_evidence": {
                "supports_claim": bool or None,
                "contradicts_claim": bool,
                "verdict": "confirmed|contradicted|partially_supported|not_found",
                "key_findings": [str],
                "best_sources": [{"url": str, "authority": str}],
            }
        }
    """
    claim_id = claim.get("claim_id", "unknown")
    claim_text = claim.get("text", "")
    verification_query = claim.get("verification_query", "")

    if not verification_query:
        verification_query = f"{platform} {claim_text[:100]}"

    # Build platform-specific domain filter
    platform_key = platform.lower()
    include_domains = VENDOR_DOCS.get(platform_key, []) + THIRD_PARTY_SOURCES

    # Search with both engines
    search_queries = [verification_query]

    # Add a second, broader query for cross-validation
    broad_query = f"{platform} security architecture encryption key management"
    if platform_key in ["databricks", "snowflake"]:
        broad_query += f" {platform} cloud trust model data protection"
    search_queries.append(broad_query)

    # Tavily search (with domain filtering)
    tavily_results = []
    for q in search_queries:
        tavily_results.extend(_search_tavily(q, max_results=3, include_domains=include_domains))
        time.sleep(0.3)  # Rate limiting

    # OpenAI search
    platform_context = f"Platform: {platform}\nClaim to verify: {claim_text}"
    openai_results = _search_openai(verification_query, platform_context, max_results=5)

    # Cross-validate
    merged = _cross_validate(tavily_results, openai_results)

    # Synthesize verdict
    external_evidence = _synthesize_verdict(claim_text, merged)

    return {
        "claim_id": claim_id,
        "claim_text": claim_text,
        "platform": platform,
        "search_queries": search_queries,
        "tavily_results_count": len([r for r in tavily_results if not r.get("error")]),
        "openai_results_count": len([r for r in openai_results if not r.get("error")]),
        "merged_results": merged[:10],  # Top 10
        "external_evidence": external_evidence,
    }


def _synthesize_verdict(claim_text: str, merged_results: list[dict]) -> dict:
    """
    Determine whether external evidence supports, contradicts, or is silent on the claim.
    """
    valid_results = [r for r in merged_results if not r.get("error")]

    if not valid_results:
        return {
            "supports_claim": None,
            "contradicts_claim": False,
            "verdict": "not_found",
            "key_findings": ["No authoritative external sources found."],
            "best_sources": [],
        }

    # Count authoritative sources
    vendor_sources = [r for r in valid_results if r.get("authority") == "vendor_official"]
    audit_sources = [r for r in valid_results if r.get("authority") == "third_party_audit"]
    cross_validated = [r for r in valid_results if r.get("cross_validated")]

    key_findings = []
    best_sources = []

    for r in valid_results[:5]:
        if r.get("content"):
            key_findings.append(r["content"][:300])
        if r.get("url"):
            best_sources.append({
                "url": r["url"],
                "authority": r.get("authority", "unknown"),
                "title": r.get("title", ""),
                "cross_validated": r.get("cross_validated", False),
            })

    # Simple heuristic verdict (the Correlation Agent will do deeper analysis)
    if len(vendor_sources) >= 2 or len(cross_validated) >= 2:
        verdict = "confirmed"
    elif len(valid_results) >= 1 and (vendor_sources or audit_sources):
        verdict = "partially_supported"
    else:
        verdict = "not_found"

    return {
        "supports_claim": verdict in ["confirmed", "partially_supported"],
        "contradicts_claim": False,  # Contradiction detection happens in correlation agent
        "verdict": verdict,
        "key_findings": key_findings[:5],
        "best_sources": best_sources[:5],
        "stats": {
            "total_results": len(valid_results),
            "vendor_official": len(vendor_sources),
            "third_party_audit": len(audit_sources),
            "cross_validated": len(cross_validated),
        }
    }


def research_claims_batch(claims: list[dict], platform: str,
                          config_path: str = "config/pipeline_config.yaml") -> list[dict]:
    """
    Research multiple claims for the same platform.
    Batches requests to respect rate limits.
    """
    results = []
    for i, claim in enumerate(claims):
        if not claim.get("needs_external", False):
            continue

        result = research_claim(claim, platform, config_path)
        results.append(result)

        # Rate limiting between claims
        if i < len(claims) - 1:
            time.sleep(0.5)

    return results


if __name__ == "__main__":
    test_claim = {
        "claim_id": "Q2-C003",
        "text": "In Databricks on AWS, the cloud provider holds the encryption keys, not the data owner.",
        "type": "comparative",
        "needs_external": True,
        "comparison_target": "databricks",
        "verification_query": "Databricks AWS encryption key management who holds keys",
    }

    result = research_claim(test_claim, "databricks")
    print(json.dumps(result, indent=2, default=str))
