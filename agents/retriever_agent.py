"""
Retriever Agent
Finds the most relevant evidence chunks for a given question.
Uses vector similarity search with the ChromaDB index.
"""

import json
from pathlib import Path

import chromadb
from sentence_transformers import SentenceTransformer
import yaml


def load_index(persist_dir: str = "knowledge/chroma_db") -> chromadb.Collection:
    """Load the existing ChromaDB index."""
    client = chromadb.PersistentClient(path=persist_dir)
    return client.get_collection("doc_chunks")


def generate_query_variants(question: str) -> list[str]:
    """
    Generate multiple query variants for better retrieval coverage.
    This is a simple keyword-expansion approach; DSPy can optimize this later.
    """
    variants = [question]

    # Add keyword-focused variants
    # Strip question words and create keyword queries
    keywords = question.lower()
    for word in ["why does", "why is", "how can", "how does", "what makes", "what is",
                 "and why", "and how", "compared to", "the", "a ", "an "]:
        keywords = keywords.replace(word, " ")
    keywords = " ".join(keywords.split())
    if keywords != question.lower():
        variants.append(keywords)

    # Add concept-focused variants based on known topics
    if "resilience" in question.lower() or "peer-to-peer" in question.lower():
        variants.extend([
            "peer to peer cluster node failure recovery",
            "edge deployment autonomous operation disconnected",
            "data replication fragmentation distributed nodes",
            "network partition tolerance resilience"
        ])
    if "security" in question.lower() and ("snowflake" in question.lower() or "databricks" in question.lower()):
        variants.extend([
            "security architecture trust boundary attack surface",
            "data locality encryption key ownership custody",
            "cloud provider trust assumptions data exposure",
            "compared centralized cloud security model"
        ])
    if "wallet" in question.lower() or "key" in question.lower():
        variants.extend([
            "data wallet key storage authentication",
            "encryption access control authorization",
            "key loss recovery unauthorized access prevention",
            "data storage security mechanism",
            # Bug 6.5 fix: Ensure ADR Auth token spec is retrieved for wallet/key questions
            "authentication token delegation JWT trust chain",
            "token based access control pallet delegation identity",
            "AuthToken Payload Signature proto specification",
            "DdcClient buildAndConnect createBucket upload delegateAccess",
            "recursive token signed delegation hierarchy",
            "PolicyGrant DEK HKDF key derivation encryption grant",
            "sequence diagram access control authorization flow",
        ])

    return variants


def retrieve_evidence(question_id: str, question_text: str,
                      config_path: str = "config/pipeline_config.yaml") -> dict:
    """
    Retrieve the best evidence chunks for a question.
    Returns a structured evidence set.
    """
    # Load config
    with open(config_path) as f:
        config = yaml.safe_load(f)

    top_k = config["retrieval"]["top_k"]

    # Load index and model
    collection = load_index()
    model = SentenceTransformer("all-MiniLM-L6-v2")

    # Generate query variants
    variants = generate_query_variants(question_text)

    # Search with each variant and collect unique results
    seen_ids = set()
    all_results = []

    for variant in variants:
        embedding = model.encode(variant).tolist()
        results = collection.query(
            query_embeddings=[embedding],
            n_results=min(top_k, collection.count()),
            include=["documents", "metadatas", "distances"]
        )

        for i in range(len(results["ids"][0])):
            chunk_id = results["ids"][0][i]
            if chunk_id not in seen_ids:
                seen_ids.add(chunk_id)
                all_results.append({
                    "chunk_id": chunk_id,
                    "text": results["documents"][0][i],
                    "metadata": results["metadatas"][0][i],
                    "distance": results["distances"][0][i],
                    "relevance": 1 - results["distances"][0][i],  # cosine similarity
                    "query_variant": variant
                })

    # Sort by relevance and take top_k
    all_results.sort(key=lambda x: x["relevance"], reverse=True)
    evidence = all_results[:top_k]

    # Check for diversity - prefer chunks from different sections/pages
    seen_pages = {}
    diverse_evidence = []
    remaining = []

    for e in evidence:
        page_key = f"{e['metadata']['pdf_file']}-p{e['metadata']['page_start']}"
        if page_key not in seen_pages or len(seen_pages) < 3:
            diverse_evidence.append(e)
            seen_pages[page_key] = True
        else:
            remaining.append(e)

    # Fill remaining slots
    final_evidence = diverse_evidence + remaining
    final_evidence = final_evidence[:top_k]

    # Coverage analysis
    coverage_notes = []
    if len(final_evidence) < 5:
        coverage_notes.append("WARNING: Very few relevant chunks found. Documents may not adequately cover this topic.")
    if len(set(e["metadata"]["pdf_file"] for e in final_evidence)) == 1:
        coverage_notes.append("NOTE: All evidence comes from a single document.")

    avg_relevance = sum(e["relevance"] for e in final_evidence) / len(final_evidence) if final_evidence else 0
    if avg_relevance < 0.3:
        coverage_notes.append("WARNING: Low average relevance scores. Documents may not cover this topic well.")

    return {
        "question_id": question_id,
        "question_text": question_text,
        "query_variants": variants,
        "evidence": [{
            "chunk_id": e["chunk_id"],
            "text": e["text"],
            "pdf_file": e["metadata"]["pdf_file"],
            "page_start": e["metadata"]["page_start"],
            "relevance": round(e["relevance"], 4),
        } for e in final_evidence],
        "coverage_notes": coverage_notes,
        "stats": {
            "total_unique_results": len(all_results),
            "returned": len(final_evidence),
            "avg_relevance": round(avg_relevance, 4),
            "source_documents": list(set(e["metadata"]["pdf_file"] for e in final_evidence))
        }
    }


if __name__ == "__main__":
    # Quick test
    questions = {
        "Q1": "Why does the highly peer-to-peer design of the DDC clusters ensure resilience? And why is it suitable for a fully autonomous edge or hybrid cluster for an enterprise?",
        "Q2": "How can a DDC cluster provide a higher level of security compared to a typical stack from Databricks or Snowflake running on top of AWS/Azure?",
        "Q3": "How can I store my data on this data cluster with my data wallet and key? What makes it secure?"
    }

    for qid, qtext in questions.items():
        print(f"\n{'='*60}")
        print(f"Retrieving evidence for {qid}...")
        result = retrieve_evidence(qid, qtext)
        print(f"  Found {result['stats']['returned']} chunks (avg relevance: {result['stats']['avg_relevance']})")
        print(f"  Sources: {result['stats']['source_documents']}")
        if result['coverage_notes']:
            for note in result['coverage_notes']:
                print(f"  {note}")
