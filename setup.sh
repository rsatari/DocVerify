#!/bin/bash
# DocVerify — Setup Script
# Copies your existing DDC Evaluator agents into the DocVerify project structure.
#
# Usage:
#   cd /path/to/docverify
#   bash setup.sh /path/to/ddc-doc-evaluator
#
# This script:
# 1. Copies agent files into agents/
# 2. Copies config files
# 3. Copies PDFs
# 4. Creates .env from template if needed

set -e

SOURCE_DIR="${1:-.}"
DEST_DIR="$(pwd)"

echo "╔══════════════════════════════════════╗"
echo "║     DocVerify — Project Setup        ║"
echo "╚══════════════════════════════════════╝"
echo ""
echo "Source: $SOURCE_DIR"
echo "Dest:   $DEST_DIR"
echo ""

# Clean up bad directory from previous run (shell brace expansion issue)
if [ -d '{agents,config,evaluation,docs' ]; then
    rm -rf '{agents,config,evaluation,docs'
    echo "✓ Cleaned up malformed directory from previous run"
fi

# Create directories
mkdir -p agents config evaluation docs/pdfs knowledge reports

# ─── Copy agents ────────────────────────────────────
echo "Copying agents..."
AGENT_FILES=(
    "__init__.py"
    "answer_agent.py"
    "claim_cache.py"
    "claim_extractor_agent.py"
    "correlation_agent.py"
    "cost_tracker.py"
    "cross_llm_checker.py"
    "doc_editor_agent.py"
    "edit_verifier.py"
    "editor_agent.py"
    "evaluator_agent.py"
    "failure_ledger.py"
    "gap_verifier_agent.py"
    "ingestion_agent.py"
    "knowledge_store.py"
    "nli_verifier.py"
    "question_worker.py"
    "ragas_evaluator.py"
    "research_agent.py"
    "retriever_agent.py"
    "router_agent.py"
    "shared_context.py"
    "verification_agent.py"
)

COPIED=0
MISSING=0
for f in "${AGENT_FILES[@]}"; do
    if [ -f "$SOURCE_DIR/agents/$f" ]; then
        cp "$SOURCE_DIR/agents/$f" "agents/$f"
        echo "  ✓ agents/$f"
        COPIED=$((COPIED + 1))
    else
        echo "  ✗ agents/$f NOT FOUND"
        MISSING=$((MISSING + 1))
    fi
done
echo "  $COPIED copied, $MISSING missing"

# Also catch any .py files in agents/ not in the list above
for f in "$SOURCE_DIR"/agents/*.py; do
    if [ -f "$f" ]; then
        fname=$(basename "$f")
        if [ ! -f "agents/$fname" ]; then
            cp "$f" "agents/$fname"
            echo "  ✓ agents/$fname (extra)"
            COPIED=$((COPIED + 1))
        fi
    fi
done

# Copy run_pipeline.py (the original orchestrator, kept as reference)
if [ -f "$SOURCE_DIR/run_pipeline.py" ]; then
    cp "$SOURCE_DIR/run_pipeline.py" run_pipeline_original.py
    echo "  ✓ run_pipeline_original.py (reference copy)"
fi

# ─── Copy config ────────────────────────────────────
echo ""
echo "Copying config..."
if [ -f "$SOURCE_DIR/config/pipeline_config.yaml" ]; then
    cp "$SOURCE_DIR/config/pipeline_config.yaml" config/
    echo "  ✓ config/pipeline_config.yaml"
elif [ -f "$SOURCE_DIR/pipeline_config.yaml" ]; then
    cp "$SOURCE_DIR/pipeline_config.yaml" config/
    echo "  ✓ config/pipeline_config.yaml"
fi

if [ -f "$SOURCE_DIR/evaluation/evaluation_spec.yaml" ]; then
    cp "$SOURCE_DIR/evaluation/evaluation_spec.yaml" evaluation/
    echo "  ✓ evaluation/evaluation_spec.yaml"
elif [ -f "$SOURCE_DIR/evaluation_spec.yaml" ]; then
    cp "$SOURCE_DIR/evaluation_spec.yaml" evaluation/
    echo "  ✓ evaluation/evaluation_spec.yaml"
fi

# ─── Copy PDFs ──────────────────────────────────────
echo ""
echo "Copying PDFs..."
PDF_COUNT=0
for pdf in "$SOURCE_DIR"/docs/pdfs/*.pdf "$SOURCE_DIR"/*.pdf; do
    if [ -f "$pdf" ]; then
        cp "$pdf" docs/pdfs/
        echo "  ✓ $(basename $pdf)"
        PDF_COUNT=$((PDF_COUNT + 1))
    fi
done
echo "  $PDF_COUNT PDFs copied"

# ─── Copy knowledge (edited MDs, caches) ────────────
echo ""
echo "Copying knowledge..."
if [ -d "$SOURCE_DIR/knowledge" ]; then
    cp -r "$SOURCE_DIR/knowledge/"* knowledge/ 2>/dev/null || true
    echo "  ✓ knowledge/ synced"
fi

# ─── Create .env if needed ──────────────────────────
echo ""
if [ ! -f ".env" ]; then
    if [ -f "$SOURCE_DIR/.env" ]; then
        cp "$SOURCE_DIR/.env" .env
        echo "✓ Copied .env from source"
    elif [ -f ".env.example" ]; then
        cp .env.example .env
        echo "⚠ Created .env from template — please add your API keys"
    fi
else
    echo "✓ .env already exists"
fi

# ─── Summary ────────────────────────────────────────
echo ""
echo "════════════════════════════════════════"
echo "Setup complete! Next steps:"
echo ""
echo "  1. Verify .env has your API keys"
echo "  2. Run locally:"
echo "     pip install -r requirements.txt"
echo "     python -m docverify.graph"
echo ""
echo "  3. Or run with Docker:"
echo "     docker compose up"
echo ""
echo "  4. API will be at http://localhost:8000"
echo "  5. Docs: http://localhost:8000/docs"
echo "════════════════════════════════════════"
