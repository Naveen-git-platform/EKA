# syntax=docker/dockerfile:1
# EKA backend: FastAPI + LangGraph agents + hybrid retrieval (CPU-only). Build context: ./backend
FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    HF_HOME=/opt/hf

WORKDIR /app

# Dependencies first (cached layer). CPU-only PyTorch keeps the image ~2 GB smaller than the CUDA wheels.
# constraints.txt pins every transitive dependency to the versions the test suite ran against (and stops pip
# from backtracking through hundreds of releases while resolving).
COPY requirements.txt constraints.txt ./
RUN pip install torch --index-url https://download.pytorch.org/whl/cpu \
    && pip install -c constraints.txt -r requirements.txt

# Bake the embedding model into the image so the container starts fast and works offline.
RUN python -c "from sentence_transformers import SentenceTransformer; SentenceTransformer('sentence-transformers/all-MiniLM-L6-v2')" \
    && chmod -R a+rX /opt/hf

COPY app ./app
COPY data/sample_docs ./data/sample_docs
COPY data/eval ./data/eval
COPY docs/benchmark_results.json ./docs/benchmark_results.json

# Run as an unprivileged user; /data holds the registry, chunk store and evaluation DB (mounted volume).
RUN useradd --create-home --uid 10001 eka && mkdir -p /data && chown -R eka:eka /data /app
USER eka

ENV DATA_DIR=/data \
    HF_HUB_OFFLINE=1 \
    LOG_LEVEL=INFO

EXPOSE 8000
HEALTHCHECK --interval=15s --timeout=5s --start-period=60s --retries=5 \
    CMD python -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://localhost:8000/health', timeout=4).status == 200 else 1)"

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
