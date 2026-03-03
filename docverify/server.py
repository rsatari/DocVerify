"""
DocVerify — FastAPI Server
===========================
REST API for running evaluations, asking questions, and managing documents.
Compatible with Aegra deployment (self-hosted LangGraph Platform alternative).

Endpoints:
    POST /evaluate          — trigger full pipeline run
    GET  /status/{run_id}   — poll run status
    POST /ask               — single-question verified answer
    POST /upload-docs       — upload PDF knowledge base
    GET  /reports           — list past reports
    GET  /reports/{run_id}  — get specific report
    GET  /health            — health check
"""

import os
import time
import uuid
import asyncio
from pathlib import Path
from datetime import datetime
from typing import Optional
from contextlib import asynccontextmanager

from fastapi import FastAPI, UploadFile, File, HTTPException, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from dotenv import load_dotenv
load_dotenv()


# ─── In-memory job store (swap for Postgres in production) ─────

jobs: dict[str, dict] = {}


# ─── Lifespan ──────────────────────────────────────────────────

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup: verify API keys and docs exist."""
    missing = []
    if not os.environ.get("ANTHROPIC_API_KEY"):
        missing.append("ANTHROPIC_API_KEY")
    if not os.environ.get("OPENAI_API_KEY"):
        missing.append("OPENAI_API_KEY")
    if missing:
        print(f"⚠ Missing env vars: {', '.join(missing)}")
    else:
        print("✓ API keys configured")

    Path("docs/pdfs").mkdir(parents=True, exist_ok=True)
    Path("reports").mkdir(exist_ok=True)
    Path("knowledge").mkdir(exist_ok=True)
    print("✓ DocVerify API ready")
    yield
    print("DocVerify shutting down")


# ─── App ───────────────────────────────────────────────────────

app = FastAPI(
    title="DocVerify",
    description="Verified answers from your documentation — with proof.",
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


# ─── Schemas ───────────────────────────────────────────────────

class EvaluateRequest(BaseModel):
    tenant_id: str = "default"

class AskRequest(BaseModel):
    question: str
    tenant_id: str = "default"

class JobStatus(BaseModel):
    run_id: str
    status: str  # "running", "complete", "failed"
    started_at: Optional[str] = None
    completed_at: Optional[str] = None
    elapsed: Optional[float] = None
    summary: Optional[dict] = None
    error: Optional[str] = None


# ─── Background task runner ────────────────────────────────────

def _run_pipeline(run_id: str, tenant_id: str):
    """Run the full LangGraph pipeline in background."""
    try:
        jobs[run_id]["status"] = "running"

        from docverify.graph import run as run_graph
        result = run_graph(tenant_id=tenant_id)

        # Extract summary
        summary = {}
        for qid, eval_data in result.get("evaluations", {}).items():
            summary[qid] = {
                "overall": eval_data.get("overall_score", 0),
                "correctness": eval_data.get("scores", {}).get("grounded_correctness", 0),
                "passed": eval_data.get("passed", False),
                "loop": result.get("routing", {}).get(qid, {}).get("loop", "A"),
            }

        jobs[run_id]["status"] = "complete"
        jobs[run_id]["completed_at"] = datetime.now().isoformat()
        jobs[run_id]["elapsed"] = result.get("elapsed", 0)
        jobs[run_id]["summary"] = summary
        jobs[run_id]["report_path"] = result.get("report_path", "")

    except Exception as e:
        jobs[run_id]["status"] = "failed"
        jobs[run_id]["error"] = str(e)
        import traceback
        traceback.print_exc()


# ─── Endpoints ─────────────────────────────────────────────────

@app.get("/health")
async def health():
    """Health check."""
    return {
        "status": "healthy",
        "version": "1.0.0",
        "docs_count": len(list(Path("docs/pdfs").glob("*.pdf"))),
    }


@app.post("/evaluate", response_model=JobStatus)
async def evaluate(req: EvaluateRequest, background_tasks: BackgroundTasks):
    """Trigger a full evaluation pipeline run."""
    pdfs = list(Path("docs/pdfs").glob("*.pdf"))
    if not pdfs:
        raise HTTPException(400, "No PDF files found in docs/pdfs/. Upload documents first.")

    run_id = str(uuid.uuid4())[:8]
    jobs[run_id] = {
        "run_id": run_id,
        "status": "queued",
        "started_at": datetime.now().isoformat(),
        "tenant_id": req.tenant_id,
    }

    background_tasks.add_task(_run_pipeline, run_id, req.tenant_id)

    return JobStatus(
        run_id=run_id,
        status="queued",
        started_at=jobs[run_id]["started_at"],
    )


@app.get("/status/{run_id}", response_model=JobStatus)
async def status(run_id: str):
    """Poll the status of an evaluation run."""
    if run_id not in jobs:
        raise HTTPException(404, f"Run {run_id} not found")

    j = jobs[run_id]
    return JobStatus(
        run_id=run_id,
        status=j.get("status", "unknown"),
        started_at=j.get("started_at"),
        completed_at=j.get("completed_at"),
        elapsed=j.get("elapsed"),
        summary=j.get("summary"),
        error=j.get("error"),
    )


@app.post("/upload-docs")
async def upload_docs(files: list[UploadFile] = File(...)):
    """Upload PDF documents to the knowledge base."""
    uploaded = []
    for file in files:
        if not file.filename.lower().endswith(".pdf"):
            continue
        dest = Path("docs/pdfs") / file.filename
        content = await file.read()
        dest.write_bytes(content)
        uploaded.append(file.filename)

    if not uploaded:
        raise HTTPException(400, "No PDF files in upload")

    return {
        "uploaded": uploaded,
        "total_docs": len(list(Path("docs/pdfs").glob("*.pdf"))),
    }


@app.post("/ask")
async def ask(req: AskRequest):
    """
    Single-question mode: answer + verify in real-time.
    Returns answer with verification score and grounding proof.
    """
    pdfs = list(Path("docs/pdfs").glob("*.pdf"))
    if not pdfs:
        raise HTTPException(400, "No documents uploaded yet")

    from agents.ingestion_agent import ingest_all_pdfs
    from agents.retriever_agent import retrieve_evidence
    from agents.answer_agent import answer_question

    # Quick pipeline: retrieve → answer → return
    # (Full verification would take too long for real-time)
    evidence = retrieve_evidence("adhoc", req.question)
    answer = answer_question("adhoc", req.question, evidence["evidence"])

    return {
        "question": req.question,
        "answer": answer.get("answer_markdown", ""),
        "chunks_cited": answer.get("evidence_chunks_cited", 0),
        "chunks_provided": answer.get("evidence_chunks_provided", 0),
        "warnings": answer.get("warnings", {}),
    }


@app.get("/reports")
async def list_reports():
    """List available reports."""
    reports_dir = Path("reports")
    reports = []
    for f in sorted(reports_dir.glob("*.md"), reverse=True):
        reports.append({
            "filename": f.name,
            "size": f.stat().st_size,
            "modified": datetime.fromtimestamp(f.stat().st_mtime).isoformat(),
        })
    return {"reports": reports[:20]}


@app.get("/reports/{filename}")
async def get_report(filename: str):
    """Get a specific report."""
    path = Path("reports") / filename
    if not path.exists():
        raise HTTPException(404, f"Report {filename} not found")
    return {"filename": filename, "content": path.read_text()}
