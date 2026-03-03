FROM python:3.10-slim

WORKDIR /app

# System dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    git \
    && rm -rf /var/lib/apt/lists/*

# Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Pre-download NLI model at build time (avoids 500MB cold-start)
RUN python -c "from sentence_transformers import SentenceTransformer; SentenceTransformer('all-MiniLM-L6-v2')" 2>/dev/null || true

# Copy application
COPY . .

# Clean up any bad directories from shell brace expansion
RUN rm -rf '{agents,config,evaluation,docs' 2>/dev/null || true

# Create required directories
RUN mkdir -p docs/pdfs knowledge reports config evaluation agents

EXPOSE 8000

# Default: run FastAPI server
# Override with: docker run ... python -m docverify.graph (for CLI mode)
CMD ["uvicorn", "docverify.server:app", "--host", "0.0.0.0", "--port", "8000"]
