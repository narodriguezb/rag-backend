FROM python:3.13-slim AS builder

ENV UV_PYTHON_DOWNLOADS=never \
    UV_PYTHON_PREFERENCE=only-system \
    UV_LINK_MODE=copy

RUN apt-get update && apt-get install -y --no-install-recommends \
        build-essential \
    && rm -rf /var/lib/apt/lists/*

COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

WORKDIR /app

COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev


FROM python:3.13-slim

RUN apt-get update && apt-get install -y --no-install-recommends \
        libgomp1 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY --from=builder /app/.venv /app/.venv
ENV PATH="/app/.venv/bin:$PATH" \
    VIRTUAL_ENV="/app/.venv"

COPY backend/ ./backend/
COPY docs/ ./docs/

RUN for i in 1 2 3; do \
        python -c "from chromadb.utils import embedding_functions; embedding_functions.SentenceTransformerEmbeddingFunction(model_name='all-MiniLM-L6-v2')" && break || sleep 5; \
    done || echo "WARN: preload del modelo omitido (HuggingFace no disponible); se descargara en el primer arranque"

ENV PORT=8080
WORKDIR /app/backend

CMD uvicorn app:app --host 0.0.0.0 --port ${PORT}
