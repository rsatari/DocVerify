# DocVerify

**Verified answers from your documentation — with proof.**

DocVerify is a self-healing documentation QA pipeline that generates answers from your docs, verifies every claim, and automatically improves your knowledge base over time.

Unlike standard RAG chatbots that generate answers and hope they're correct, DocVerify **proves** correctness through multi-layer verification and shows you exactly which claims are grounded and which aren't.

## What Makes It Different

| Feature | Standard RAG | DocVerify |
|---------|-------------|-----------|
| Answer generation | ✅ | ✅ |
| Citation tracking | Some | ✅ Per-claim, per-page |
| Claim verification | ❌ | ✅ Grounding + NLI + RAGAS |
| False negative detection | ❌ | ✅ Automatic override |
| Self-healing docs | ❌ | ✅ Auto-edits accumulate |
| Evaluation scoring | ❌ | ✅ Multi-evaluator with floor |
| Verification report | ❌ | ✅ Full audit trail |

## Architecture

```
PDF Upload → Ingestion → Retrieval → Routing (Loop A/B)
                                        │
                          ┌──────────────┼──────────────┐
                          │ Loop A       │              │ Loop B
                          │ (internal)   │              │ (+ external research)
                          │              │              │
                          └──────┬───────┘              │
                                 │                      │
                          Answer Generation ◄───────────┘
                                 │
                          Claim Extraction
                                 │
                     ┌───────────┼───────────┐
                     │           │           │
                  Grounding    NLI      RAGAS
                  (terms)   (DeBERTa) (faithfulness)
                     │           │           │
                     └───────────┼───────────┘
                                 │
                          Evaluation (GPT-5.2)
                                 │
                     ┌───────────┼───────────┐
                     │                       │
              Verification Floor      Doc Editor
              (if 0 genuine fails     (auto-edit MDs)
               → correctness ≥ 0.82)
                     │                       │
                     └───────────┬───────────┘
                                 │
                              Report
```

## Quick Start

### 1. Clone & configure

```bash
git clone https://github.com/YOUR_USERNAME/docverify.git
cd docverify
cp .env.example .env
# Edit .env with your API keys
```

### 2. Add your PDFs

```bash
cp /path/to/your/docs/*.pdf docs/pdfs/
```

### 3. Run with Docker

```bash
docker compose up
```

API available at `http://localhost:8000`

### 4. Or run locally

```bash
pip install -r requirements.txt
python -m docverify.graph
```

## API Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| `POST` | `/evaluate` | Trigger full pipeline run |
| `GET` | `/status/{run_id}` | Poll run status |
| `POST` | `/ask` | Single-question verified answer |
| `POST` | `/upload-docs` | Upload PDF documents |
| `GET` | `/reports` | List past reports |
| `GET` | `/reports/{filename}` | Get specific report |
| `GET` | `/health` | Health check |

### Example: Run evaluation

```bash
curl -X POST http://localhost:8000/evaluate \
  -H "Content-Type: application/json" \
  -d '{"tenant_id": "my-company"}'

# Response: {"run_id": "abc123", "status": "queued"}

# Poll status:
curl http://localhost:8000/status/abc123
```

### Example: Ask a question

```bash
curl -X POST http://localhost:8000/ask \
  -H "Content-Type: application/json" \
  -d '{"question": "How does authentication work?"}'
```

## Configuration

### pipeline_config.yaml

Controls models, retrieval settings, and Loop B research:

```yaml
models:
  answerer:
    provider: "anthropic"
    model: "claude-sonnet-4-5-20250929"
  evaluator:
    provider: "openai"
    model: "gpt-5.2"
```

### evaluation_spec.yaml

Defines questions, required concepts, and scoring thresholds:

```yaml
questions:
  Q1:
    text: "How does authentication work?"
    required_concepts:
      - "Key ownership"
      - "Token-based access"
    forbidden_claims:
      - "Passwordless (unless documented)"
```

## Deployment

### Railway / Render (simplest)

Push the Docker container, get a URL:

```bash
# Railway
railway up

# Render
render deploy
```

### Aegra (self-hosted LangGraph Platform)

```bash
pip install aegra-cli
aegra init
aegra dev    # Local dev with hot reload
aegra serve  # Production mode
```

### AWS ECS / GCP Cloud Run

Use the Dockerfile with your cloud provider's container service.

## How Self-Healing Works

1. **Run 1:** Pipeline evaluates docs, finds gaps (e.g., "no mention of key delegation")
2. **Editor agent** writes targeted edits into `_EDITED.md` files with tracking markers
3. **Run 2:** Ingestion reads `_EDITED.md` (not original PDFs), markers stripped for clean context
4. **Better answers** because docs now cover previously missing topics
5. **Run N:** Each run layers new edits on top of previous ones. Dedup prevents duplicates.

## Verification Layers

1. **Grounding** — Deterministic term matching: are the claimed terms actually on the cited page?
2. **NLI (DeBERTa)** — Neural entailment: does the source text logically support the claim?
3. **RAGAS** — Faithfulness scoring: is the answer faithful to the retrieved context?
4. **Verification Floor** — If ≤2 genuine failures out of 60 claims, correctness floors at 0.82 (prevents evaluator variance from failing verified-clean answers)

## License

Apache 2.0 — see [LICENSE](LICENSE)
