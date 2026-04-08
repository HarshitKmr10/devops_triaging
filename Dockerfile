# ── Builder ──────────────────────────────────────────────────────────────
FROM ghcr.io/meta-pytorch/openenv-base:latest AS builder

RUN apt-get update && apt-get install -y --no-install-recommends git && rm -rf /var/lib/apt/lists/*

ARG BUILD_MODE="standalone"
ARG ENV_NAME="devops_incident_env"

WORKDIR /app/env
COPY . /app/env/

# Install uv if not present, then sync deps
RUN if ! command -v uv > /dev/null 2>&1; then pip install uv; fi && \
    if [ -f uv.lock ]; then \
        uv sync --frozen; \
    else \
        uv sync; \
    fi

# ── Runtime ──────────────────────────────────────────────────────────────
FROM ghcr.io/meta-pytorch/openenv-base:latest

WORKDIR /app/env

COPY --from=builder /app/env/.venv /app/env/.venv
COPY . /app/env/

ENV PATH="/app/env/.venv/bin:$PATH"
ENV PYTHONPATH="/app/env"

# HuggingFace Spaces expects port 7860 by default
EXPOSE 7860

HEALTHCHECK --interval=30s --timeout=5s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:7860/health')" || exit 1

CMD ["uvicorn", "server.app:app", "--host", "0.0.0.0", "--port", "7860"]
