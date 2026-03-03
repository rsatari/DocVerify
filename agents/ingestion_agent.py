"""
Ingestion Agent — Two-Tier Architecture
========================================

Automatically selects the optimal ingestion strategy based on total corpus size:

  Tier 1 (Full-Context): Total text fits in model context window
    → Concatenates all document text with source markers
    → Answer agent sees EVERYTHING — zero retrieval loss
    → No chunking, no embeddings, no vector DB needed
    → Best for: ≤ ~500 pages / ~150K tokens

  Tier 2 (RAG): Total text exceeds context window
    → Chunks documents with overlap
    → Builds ChromaDB vector index for semantic retrieval
    → Best for: 500+ pages, large wikis, knowledge bases

The tier threshold accounts for the answer agent's context window
minus space for prompt, rubric, terminology, and response tokens.
"""

import os
import json
import hashlib
import re
from pathlib import Path
from typing import Optional

import pdfplumber
import yaml


# ============================================================
# Configuration
# ============================================================

# Claude Opus 4.6 context: ~200K tokens
# Reserve ~40K for: system prompt (~3K) + question/rubric (~2K)
#                   + terminology (~2K) + response (~4K)
#                   + safety margin (~29K)
# That leaves ~160K usable for document text
CONTEXT_THRESHOLD_TOKENS = 150_000

# Approximate chars-per-token for English technical text
CHARS_PER_TOKEN = 3.5


def _estimate_tokens(text_or_charcount) -> int:
    """Fast token estimate without loading tiktoken.
    Accepts either a string or an integer character count."""
    char_count = text_or_charcount if isinstance(text_or_charcount, int) else len(text_or_charcount)
    return int(char_count / CHARS_PER_TOKEN)


def _count_tokens_precise(text: str) -> int:
    """Precise token count using tiktoken (slower, optional)."""
    try:
        import tiktoken
        enc = tiktoken.get_encoding("cl100k_base")
        return len(enc.encode(text))
    except ImportError:
        return _estimate_tokens(text)


# ============================================================
# PDF Text Extraction (shared by both tiers)
# ============================================================

def detect_format(pdf_path: str) -> str:
    """Detect whether a file is a real PDF or a Claude ZIP bundle."""
    import zipfile
    if zipfile.is_zipfile(pdf_path):
        return "zip_bundle"
    return "pdf"


def extract_text_from_pdf(pdf_path: str) -> list[dict]:
    """Extract text from a PDF file (auto-detects format)."""
    fmt = detect_format(pdf_path)
    if fmt == "zip_bundle":
        return _extract_from_zip_bundle(pdf_path)
    return _extract_from_real_pdf(pdf_path)


def _extract_from_real_pdf(pdf_path: str) -> list[dict]:
    """Extract text from a real PDF using pdfplumber."""
    pages = []
    try:
        with pdfplumber.open(pdf_path) as pdf:
            for i, page in enumerate(pdf.pages):
                text = page.extract_text()
                if text and text.strip():
                    pages.append({
                        "pdf_file": os.path.basename(pdf_path),
                        "page_number": i + 1,
                        "text": text.strip()
                    })
    except Exception as e:
        print(f"  Warning: pdfplumber failed on {pdf_path}: {e}")
    return pages


def _extract_from_zip_bundle(pdf_path: str) -> list[dict]:
    """Extract text from a Claude ZIP bundle (.pdf that's actually a ZIP)."""
    import zipfile
    pages = []
    try:
        with zipfile.ZipFile(pdf_path, 'r') as zf:
            txt_files = sorted(
                [f for f in zf.namelist() if f.endswith('.txt')],
                key=lambda x: int(re.sub(r'[^\d]', '', x) or '0')
            )
            for txt_file in txt_files:
                text = zf.read(txt_file).decode('utf-8', errors='replace').strip()
                if text:
                    page_num = int(re.sub(r'[^\d]', '', txt_file) or '0')
                    pages.append({
                        "pdf_file": os.path.basename(pdf_path),
                        "page_number": page_num,
                        "text": text
                    })
    except Exception as e:
        print(f"  Error extracting ZIP bundle {pdf_path}: {e}")
    return pages


def _strip_edit_markers(text: str) -> str:
    """
    Strip EDIT markers and metadata comments while keeping the actual
    edit content. The answerer should see clean prose, not HTML comments
    with gap descriptions, source URLs, and tracking info.

    Removes:
        <!-- EDIT-START: Q1 | track: auto | ✅ AUTO-APPLIED -->
        <!-- GAP: ... -->
        <!-- SOURCES: [...] -->
        <!-- EDIT-END: Q1 -->

    Keeps: The actual paragraph content between the markers.
    """
    # Remove EDIT-START lines
    text = re.sub(r'<!-- EDIT-START:.*?-->\s*', '', text)
    # Remove EDIT-END lines
    text = re.sub(r'<!-- EDIT-END:.*?-->\s*', '', text)
    # Remove GAP comment lines
    text = re.sub(r'<!-- GAP:.*?-->\s*', '', text)
    # Remove SOURCES comment lines
    text = re.sub(r'<!-- SOURCES:.*?-->\s*', '', text)
    # Collapse runs of 3+ blank lines into 2
    text = re.sub(r'\n{3,}', '\n\n', text)
    return text


def _parse_pages_from_markdown(md_path: str, pdf_filename: str) -> list[dict]:
    """
    Parse an _EDITED.md file back into the same page-dict format that
    extract_text_from_pdf produces.

    The MD format is:
        <!-- PAGE N -->
        ## Page N
        [page text]
        ---

    Edit content is preserved but EDIT markers (<!-- EDIT-START -->,
    <!-- GAP -->, <!-- SOURCES -->, <!-- EDIT-END -->) are stripped
    so the answerer sees clean prose without noise.
    """
    with open(md_path, "r", errors="ignore") as f:
        content = f.read()

    pages = []
    # Split on page markers
    page_splits = re.split(r'<!-- PAGE (\d+) -->', content)

    # page_splits = [header, "1", page1_text, "2", page2_text, ...]
    for i in range(1, len(page_splits), 2):
        page_num = int(page_splits[i])
        page_text = page_splits[i + 1] if (i + 1) < len(page_splits) else ""

        # Clean: remove the "## Page N" header and trailing ---
        page_text = re.sub(r'^##\s+Page\s+\d+\s*\n', '', page_text.strip())
        page_text = re.sub(r'\n---\s*$', '', page_text.strip())

        # Strip EDIT markers but keep edit content
        page_text = _strip_edit_markers(page_text)

        pages.append({
            "pdf_file": pdf_filename,
            "page_number": page_num,
            "text": page_text.strip(),
        })

    return pages


EDITED_MD_DIR = "knowledge/edited_markdown"


def extract_all_pdfs(pdf_dir: str = "docs/pdfs") -> list[dict]:
    """
    Extract text from all PDFs in a directory.

    If an _EDITED.md file exists for a PDF (from a previous pipeline run),
    use that as the source instead of re-extracting from the PDF. This
    ensures that accumulated documentation edits are preserved across runs.
    """
    pdf_path = Path(pdf_dir)
    if not pdf_path.exists():
        print(f"  PDF directory {pdf_dir} not found")
        return []

    all_pages = []
    for pdf_file in sorted(pdf_path.glob("*.pdf")):
        # Check for an _EDITED.md from a previous run
        edited_name = pdf_file.name.replace('.pdf', '_EDITED.md').replace(' ', '_')
        edited_path = os.path.join(EDITED_MD_DIR, edited_name)

        if os.path.exists(edited_path):
            print(f"  Using edited: {edited_name} (accumulated edits from previous runs)")
            pages = _parse_pages_from_markdown(edited_path, pdf_file.name)
            if pages:
                all_pages.extend(pages)
                print(f"    -> {len(pages)} pages, {sum(len(p['text']) for p in pages):,} chars")
            else:
                # Fallback to PDF if parsing failed
                print(f"    -> Parse failed, falling back to PDF extraction")
                pages = extract_text_from_pdf(str(pdf_file))
                all_pages.extend(pages)
                print(f"    -> {len(pages)} pages, {sum(len(p['text']) for p in pages):,} chars")
        else:
            print(f"  Extracting: {pdf_file.name}...")
            pages = extract_text_from_pdf(str(pdf_file))
            all_pages.extend(pages)
            print(f"    -> {len(pages)} pages, {sum(len(p['text']) for p in pages):,} chars")
    return all_pages


# ============================================================
# Section / content detection (used by both tiers)
# ============================================================

def detect_sections(text: str) -> list[str]:
    """Detect section headings from text."""
    lines = text.split("\n")
    sections = []
    for line in lines:
        line = line.strip()
        if not line:
            continue
        if re.match(r'^\d+(?:\.\d+)*[.\s]+.+$', line) and len(line) < 100:
            sections.append(line)
            continue
        if (len(line) < 100 and not line.endswith('.') and
            not line.endswith(',') and len(line.split()) <= 12 and
            (line[0].isupper() or line[0].isdigit())):
            sections.append(line)
    return sections


def detect_content_type(text: str) -> str:
    """Classify a chunk's content type."""
    if re.search(r'message\s+\w+\s*\{|enum\s+\w+\s*\{|syntax\s*=', text):
        return "protobuf_spec"
    if re.search(r'```|def\s+\w+|function\s+\w+|class\s+\w+', text):
        return "code_example"
    if re.search(r'(?:AC|Definition of done|Scenario|Execution|Result):', text):
        return "acceptance_criteria"
    return "prose"


def extract_key_entities(text: str) -> list[str]:
    """Extract key technical entities from text."""
    entities = set()
    entities.update(re.findall(r'\b[A-Z][a-z]+(?:[A-Z][a-z]+)+\b', text))
    entities.update(re.findall(r'\b[A-Z][A-Z_]{2,}\b', text))
    entities.update(re.findall(r'`([^`]+)`', text))
    return sorted(entities)[:20]


# ============================================================
# Tier Selection
# ============================================================

def select_tier(all_pages: list[dict]) -> dict:
    """
    Determine which ingestion tier to use based on total document size.
    """
    total_chars = sum(len(p["text"]) for p in all_pages)
    estimated_tokens = _estimate_tokens(total_chars)
    doc_names = set(p["pdf_file"] for p in all_pages)

    tier = 1 if estimated_tokens < CONTEXT_THRESHOLD_TOKENS else 2

    if tier == 1:
        reason = (f"Corpus ~{estimated_tokens:,} tokens fits in context window "
                  f"(threshold: {CONTEXT_THRESHOLD_TOKENS:,}). "
                  f"Using FULL-CONTEXT mode — zero information loss.")
    else:
        reason = (f"Corpus ~{estimated_tokens:,} tokens exceeds context window "
                  f"(threshold: {CONTEXT_THRESHOLD_TOKENS:,}). "
                  f"Using RAG mode — chunking + vector retrieval.")

    return {
        "tier": tier,
        "reason": reason,
        "total_chars": total_chars,
        "estimated_tokens": estimated_tokens,
        "threshold_tokens": CONTEXT_THRESHOLD_TOKENS,
        "doc_count": len(doc_names),
        "page_count": len(all_pages),
        "doc_names": sorted(doc_names),
    }


# ============================================================
# Tier 1: Full-Context Ingestion
# ============================================================

def ingest_tier1(all_pages: list[dict]) -> dict:
    """
    Tier 1: Concatenate all documents with source markers.

    Also merges any approved edits from previous pipeline runs
    (from knowledge/approved_edits.json) into the full text,
    so the answer agent sees the improved documentation.

    Returns full_text with document/page markers for citation,
    plus pseudo-chunks (one per page) for evaluator compatibility.
    """
    docs = {}
    for page in all_pages:
        pdf = page["pdf_file"]
        if pdf not in docs:
            docs[pdf] = []
        docs[pdf].append(page)

    full_text_parts = []
    documents = []
    pseudo_chunks = []
    chunk_id = 0

    for pdf_file in sorted(docs.keys()):
        pages = sorted(docs[pdf_file], key=lambda p: p["page_number"])
        doc_text_parts = []
        for page in pages:
            doc_text_parts.append(page["text"])

        doc_text = "\n\n".join(doc_text_parts)

        full_text_parts.append(
            f"\n{'='*80}\n"
            f"DOCUMENT: {pdf_file} ({len(pages)} pages)\n"
            f"{'='*80}\n\n"
            f"{doc_text}"
        )

        documents.append({
            "pdf_file": pdf_file,
            "page_count": len(pages),
            "char_count": len(doc_text),
        })

        # Pseudo-chunks for evaluator/citation compatibility
        for page in pages:
            pseudo_chunks.append({
                "chunk_id": f"{pdf_file.replace('.pdf','')}-p{page['page_number']:03d}",
                "pdf_file": pdf_file,
                "page_start": page["page_number"],
                "page_end": page["page_number"],
                "text": page["text"],
                "token_count": _estimate_tokens(page["text"]),
                "sections": detect_sections(page["text"]),
                "content_type": detect_content_type(page["text"]),
                "key_entities": extract_key_entities(page["text"]),
            })
            chunk_id += 1

    full_text = "\n".join(full_text_parts)

    # ── Merge approved edits INLINE into their target pages ──
    # Instead of appending edits as a separate supplement section,
    # inject each edit directly into the page it targets.
    # This way Claude cites them as [[doc:File.pdf, p.N]] (normal format)
    # and all verification layers (grounding, NLI, cross-LLM, GPT evaluator)
    # can find the text in the page_index.
    merged_count = 0
    try:
        from agents.doc_editor_agent import load_approved_edits
        approved = load_approved_edits()
        if approved:
            # Build lookup: (pdf_file, page) → list of pseudo_chunk indices
            chunk_index = {}
            for idx, chunk in enumerate(pseudo_chunks):
                key = (chunk.get("pdf_file", ""), chunk.get("page_start", 0))
                if key not in chunk_index:
                    chunk_index[key] = []
                chunk_index[key].append(idx)

            # Also build doc → last page lookup for edits with page=0
            doc_last_page = {}
            for chunk in pseudo_chunks:
                pdf = chunk.get("pdf_file", "")
                page = chunk.get("page_start", 0)
                if pdf not in doc_last_page or page > doc_last_page[pdf]:
                    doc_last_page[pdf] = page

            for edit in approved:
                target = edit.get("target_doc", "")
                new_text = edit.get("new_text", "")
                edit_page = edit.get("page", 0)
                if not target or not new_text:
                    continue

                # Find the best page to attach this edit to
                # Strategy: extract page refs from the edit's citations,
                # then from the gap text. Only fall back to first page as last resort.
                if edit_page == 0:
                    # Try to extract page from citations
                    edit_citations = edit.get("citations", [])
                    rationale = edit.get("rationale", "")
                    all_text = " ".join(edit_citations) + " " + rationale
                    page_refs = re.findall(r'p\.?(\d+)', all_text)
                    if page_refs:
                        edit_page = int(page_refs[0])
                    else:
                        # Distribute across document pages to avoid mega-chunks
                        # Use a round-robin across the doc's pages
                        doc_pages = sorted(set(
                            chunk.get("page_start", 1)
                            for chunk in pseudo_chunks
                            if chunk.get("pdf_file") == target and chunk.get("page_start", 0) > 0
                        ))
                        if doc_pages:
                            edit_page = doc_pages[merged_count % len(doc_pages)]
                        else:
                            edit_page = 1

                # Format the edit text (no special markers — just content)
                edit_addition = f"\n\n{new_text}"

                # Inject into pseudo_chunk(s) for this page
                key = (target, edit_page)
                if key in chunk_index:
                    for idx in chunk_index[key]:
                        pseudo_chunks[idx]["text"] += edit_addition
                        pseudo_chunks[idx]["token_count"] = _estimate_tokens(
                            pseudo_chunks[idx]["text"]
                        )
                    merged_count += 1
                else:
                    # No exact page match — try appending to last page of doc
                    fallback_key = (target, doc_last_page.get(target, 0))
                    if fallback_key in chunk_index:
                        for idx in chunk_index[fallback_key]:
                            pseudo_chunks[idx]["text"] += edit_addition
                            pseudo_chunks[idx]["token_count"] = _estimate_tokens(
                                pseudo_chunks[idx]["text"]
                            )
                        merged_count += 1
                    else:
                        # Create a new chunk for this edit
                        pseudo_chunks.append({
                            "chunk_id": f"{target.replace('.pdf','').replace(' ','_')}-edit-{merged_count:03d}",
                            "pdf_file": target,
                            "page_start": edit_page or 1,
                            "page_end": edit_page or 1,
                            "text": new_text,
                            "token_count": _estimate_tokens(new_text),
                            "sections": [],
                            "content_type": "approved_edit",
                            "key_entities": extract_key_entities(new_text),
                        })
                        merged_count += 1

            # Rebuild full_text from the updated pseudo_chunks
            # so Claude sees the edits inline within document pages
            if merged_count > 0:
                new_full_text_parts = []
                current_doc = None
                doc_chunks = {}
                for chunk in pseudo_chunks:
                    pdf = chunk.get("pdf_file", "")
                    if pdf not in doc_chunks:
                        doc_chunks[pdf] = []
                    doc_chunks[pdf].append(chunk)

                for pdf_file in sorted(doc_chunks.keys()):
                    chunks = sorted(doc_chunks[pdf_file],
                                    key=lambda c: c.get("page_start", 0))
                    doc_text = "\n\n".join(c["text"] for c in chunks)
                    new_full_text_parts.append(
                        f"\n{'='*80}\n"
                        f"DOCUMENT: {pdf_file} ({len(chunks)} pages)\n"
                        f"{'='*80}\n\n"
                        f"{doc_text}"
                    )

                full_text = "\n".join(new_full_text_parts)
                print(f"  ✅ Merged {merged_count} approved edits inline into source pages")

    except ImportError:
        pass  # doc_editor_agent not available yet
    except Exception as e:
        print(f"  ⚠ Could not load approved edits: {e}")

    return {
        "tier": 1,
        "full_text": full_text,
        "documents": documents,
        "chunks": pseudo_chunks,
        "total_tokens": _estimate_tokens(full_text),
        "merged_edits": merged_count,
    }


# ============================================================
# Tier 2: RAG Ingestion (chunking + vector index)
# ============================================================

def ingest_tier2(all_pages: list[dict],
                 config_path: str = "config/pipeline_config.yaml") -> dict:
    """Tier 2: Chunk documents and build ChromaDB vector index."""
    with open(config_path) as f:
        config = yaml.safe_load(f)

    retrieval_config = config.get("retrieval", {})
    chunk_size = retrieval_config.get("chunk_size", 1000)
    chunk_overlap = retrieval_config.get("chunk_overlap", 150)

    chunks = _chunk_pages(all_pages, chunk_size, chunk_overlap)
    _build_vector_index(chunks)

    docs = {}
    for page in all_pages:
        pdf = page["pdf_file"]
        if pdf not in docs:
            docs[pdf] = {"pages": 0, "chars": 0}
        docs[pdf]["pages"] += 1
        docs[pdf]["chars"] += len(page["text"])

    documents = [
        {"pdf_file": pdf, "page_count": info["pages"], "char_count": info["chars"]}
        for pdf, info in sorted(docs.items())
    ]

    return {
        "tier": 2,
        "full_text": None,
        "documents": documents,
        "chunks": chunks,
        "total_tokens": sum(c.get("token_count", 0) for c in chunks),
        "index_collection": "doc_chunks",
    }


# ============================================================
# Tier 2 helpers
# ============================================================

def _chunk_pages(pages: list[dict], chunk_size: int = 1000,
                 overlap: int = 150) -> list[dict]:
    """Chunk pages with overlap. Groups by document for cross-page context."""
    chunks = []
    chunk_id = 0

    docs = {}
    for page in pages:
        pdf = page["pdf_file"]
        if pdf not in docs:
            docs[pdf] = []
        docs[pdf].append(page)

    for pdf_file, doc_pages in docs.items():
        full_doc = "\n\n".join(
            p["text"] for p in sorted(doc_pages, key=lambda p: p["page_number"])
        )
        paragraphs = re.split(r'\n\s*\n', full_doc)

        current_chunk = ""
        current_tokens = 0
        first_page = doc_pages[0]["page_number"] if doc_pages else 1

        for para in paragraphs:
            para = para.strip()
            if not para:
                continue
            para_tokens = _estimate_tokens(para)

            if para_tokens > chunk_size:
                sentences = re.split(r'(?<=[.!?])\s+', para)
                for sent in sentences:
                    sent_tokens = _estimate_tokens(sent)
                    if current_tokens + sent_tokens > chunk_size and current_chunk:
                        chunks.append(_make_chunk(
                            chunk_id, pdf_file, first_page, current_chunk, current_tokens
                        ))
                        chunk_id += 1
                        overlap_text = current_chunk[-overlap * 4:]
                        current_chunk = overlap_text + " " + sent
                        current_tokens = _estimate_tokens(current_chunk)
                    else:
                        current_chunk += " " + sent
                        current_tokens += sent_tokens

            elif current_tokens + para_tokens > chunk_size and current_chunk:
                chunks.append(_make_chunk(
                    chunk_id, pdf_file, first_page, current_chunk, current_tokens
                ))
                chunk_id += 1
                overlap_text = current_chunk[-overlap * 4:]
                current_chunk = overlap_text + "\n\n" + para
                current_tokens = _estimate_tokens(current_chunk)
            else:
                current_chunk += "\n\n" + para
                current_tokens += para_tokens

        if current_chunk.strip():
            chunks.append(_make_chunk(
                chunk_id, pdf_file, first_page, current_chunk, current_tokens
            ))
            chunk_id += 1

    return chunks


def _make_chunk(chunk_id: int, pdf_file: str, page: int,
                text: str, token_count: int) -> dict:
    """Create a chunk dict with metadata."""
    return {
        "chunk_id": f"{pdf_file.replace('.pdf','')}-p{page:03d}-{chunk_id:04d}",
        "pdf_file": pdf_file,
        "page_start": page,
        "page_end": page,
        "text": text.strip(),
        "token_count": token_count,
        "sections": detect_sections(text),
        "content_type": detect_content_type(text),
        "key_entities": extract_key_entities(text),
    }


def _build_vector_index(chunks: list[dict],
                        persist_dir: str = "knowledge/chroma_db"):
    """Build ChromaDB vector index from chunks."""
    import chromadb
    from sentence_transformers import SentenceTransformer

    print(f"  Building vector index with {len(chunks)} chunks...")
    model = SentenceTransformer("all-MiniLM-L6-v2")
    client = chromadb.PersistentClient(path=persist_dir)

    try:
        client.delete_collection("doc_chunks")
    except Exception:
        pass

    collection = client.create_collection(
        name="doc_chunks",
        metadata={"hnsw:space": "cosine"}
    )

    batch_size = 50
    for i in range(0, len(chunks), batch_size):
        batch = chunks[i:i + batch_size]
        texts = [c["text"] for c in batch]
        ids = [c["chunk_id"] for c in batch]
        metadatas = [{
            "pdf_file": c["pdf_file"],
            "page_start": c["page_start"],
            "page_end": c.get("page_end", c["page_start"]),
            "token_count": c.get("token_count", 0),
            "sections": json.dumps(c.get("sections", [])),
            "content_type": c.get("content_type", "prose"),
            "key_entities": json.dumps(c.get("key_entities", [])),
        } for c in batch]
        embeddings = model.encode(texts).tolist()
        collection.add(ids=ids, documents=texts,
                       embeddings=embeddings, metadatas=metadatas)
        print(f"  Indexed {min(i + batch_size, len(chunks))}/{len(chunks)} chunks")

    return collection


# ============================================================
# Markdown export (for human review + editor agent input)
# ============================================================

def export_to_markdown(all_pages: list[dict],
                       output_dir: str = "knowledge/markdown_sources") -> dict:
    """
    Export each document as a separate Markdown file.

    These files serve dual purpose:
      1. Human-readable version of the source docs
      2. Editable input for the editor agent (patches applied inline)

    Returns:
        {
            "output_dir": str,
            "files": {
                "DDC_Core_Wiki.pdf": "knowledge/markdown_sources/DDC_Core_Wiki.md",
                ...
            }
        }
    """
    os.makedirs(output_dir, exist_ok=True)

    docs = {}
    for page in all_pages:
        pdf = page["pdf_file"]
        if pdf not in docs:
            docs[pdf] = []
        docs[pdf].append(page)

    files = {}
    for pdf_file in sorted(docs.keys()):
        pages = sorted(docs[pdf_file], key=lambda p: p["page_number"])
        md_name = pdf_file.replace('.pdf', '.md').replace(' ', '_')
        md_path = os.path.join(output_dir, md_name)

        with open(md_path, "w") as f:
            f.write(f"# {pdf_file.replace('.pdf', '')}\n\n")
            f.write(f"*Source: {pdf_file} | {len(pages)} pages | "
                    f"Extracted for DDC Documentation Evaluator*\n\n")
            f.write("---\n\n")

            for page in pages:
                f.write(f"<!-- PAGE {page['page_number']} -->\n")
                f.write(f"## Page {page['page_number']}\n\n")
                f.write(page["text"])
                f.write("\n\n---\n\n")

        files[pdf_file] = md_path
        print(f"    {md_name} ({len(pages)} pages)")

    # Also write combined file for backward compat
    combined_path = os.path.join(output_dir, "_combined.md")
    with open(combined_path, "w") as f:
        for pdf_file in sorted(docs.keys()):
            pages = sorted(docs[pdf_file], key=lambda p: p["page_number"])
            f.write(f"\n# {pdf_file}\n\n")
            for page in pages:
                f.write(f"## Page {page['page_number']}\n\n")
                f.write(page["text"])
                f.write("\n\n---\n\n")

    return {
        "output_dir": output_dir,
        "files": files,
        "combined": combined_path,
    }


# ============================================================
# Main Entry Point
# ============================================================

_ingestion_result = None


def ingest_all_pdfs(pdf_dir: str = "docs/pdfs",
                    config_path: str = "config/pipeline_config.yaml") -> list[dict]:
    """
    Main ingestion entry point. Auto-selects tier based on corpus size.

    Returns list of chunks (for pipeline compatibility).
    Sets module-level _ingestion_result accessible via get_ingestion_result().
    """
    global _ingestion_result

    all_pages = extract_all_pdfs(pdf_dir)
    if not all_pages:
        return []

    tier_info = select_tier(all_pages)
    print(f"\n  ┌─ Tier Decision ─────────────────────────────────")
    print(f"  │ {tier_info['reason']}")
    print(f"  │ Documents: {tier_info['doc_count']} | "
          f"Pages: {tier_info['page_count']} | "
          f"Est. tokens: {tier_info['estimated_tokens']:,}")
    print(f"  └────────────────────────────────────────────────")

    os.makedirs("knowledge", exist_ok=True)
    md_export = export_to_markdown(all_pages, "knowledge/markdown_sources")
    print(f"  Markdown sources exported to {md_export['output_dir']}/")
    print(f"  Individual files: {len(md_export['files'])}")

    if tier_info["tier"] == 1:
        result = ingest_tier1(all_pages)
        print(f"\n  [Tier 1 — FULL-CONTEXT]")
        print(f"  Full text: {result['total_tokens']:,} tokens ({len(result['full_text']):,} chars)")
        print(f"  Pseudo-chunks: {len(result['chunks'])} (one per page, for citation compat)")
        print(f"  Vector index: SKIPPED (not needed)")
        print(f"  → Answer agent will receive complete document text")
    else:
        result = ingest_tier2(all_pages, config_path)
        print(f"\n  [Tier 2 — RAG]")
        print(f"  Chunks: {len(result['chunks'])} | Tokens indexed: {result['total_tokens']:,}")
        print(f"  Vector index: knowledge/chroma_db/")
        print(f"  → Answer agent will receive top-K retrieved chunks per question")

    with open("knowledge/parsed_chunks.jsonl", "w") as f:
        for chunk in result["chunks"]:
            f.write(json.dumps(chunk) + "\n")
    print(f"  Chunks saved to knowledge/parsed_chunks.jsonl")

    # Store markdown file paths for editor agent
    result["markdown_files"] = md_export["files"]
    result["markdown_dir"] = md_export["output_dir"]

    _ingestion_result = result
    return result["chunks"]


def get_ingestion_result() -> Optional[dict]:
    """Get the result of the last ingestion.

    Pipeline reads:
      result["tier"]      → 1 or 2
      result["full_text"] → complete text (Tier 1) or None (Tier 2)
      result["documents"] → per-doc metadata
      result["chunks"]    → chunk list
    """
    return _ingestion_result


if __name__ == "__main__":
    chunks = ingest_all_pdfs()
    result = get_ingestion_result()
    if result:
        print(f"\nTier: {result['tier']}")
        print(f"Chunks: {len(result['chunks'])}")
        if result.get("full_text"):
            print(f"Full text: {len(result['full_text']):,} chars")
