FROM python:3.13-slim

RUN apt-get update && apt-get install -y --no-install-recommends \
        build-essential \
    && rm -rf /var/lib/apt/lists/*

COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

WORKDIR /app

COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev

COPY backend/ ./backend/
COPY docs/ ./docs/

RUN uv run python -c "from chromadb.utils import embedding_functions; embedding_functions.SentenceTransformerEmbeddingFunction(model_name='all-MiniLM-L6-v2')"

ENV PORT=8080
WORKDIR /app/backend

CMD uv run uvicorn app:app --host 0.0.0.0 --port ${PORT}
