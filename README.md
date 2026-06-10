# Course Materials RAG — Backend

FastAPI backend for the Course Materials RAG system. Serves a JSON API consumed by the React frontend (separate repo).

## Requirements

- Python 3.13+
- [uv](https://docs.astral.sh/uv/)
- Anthropic API key

## Setup

```bash
uv sync
cp .env.example .env   # then set ANTHROPIC_API_KEY
```

## Run

```bash
chmod +x run.sh
./run.sh
# or
cd backend && uv run uvicorn app:app --reload --port 8000
```

The API runs at `http://localhost:8000`.

## API

- `GET /` — health check
- `POST /api/query` — `{ query, session_id? }` → `{ answer, sources, session_id }`
- `GET /api/courses` — `{ total_courses, course_titles }`

CORS is open (`*`) for local development with the frontend dev server.

## Configuration

See `backend/config.py` (chunk size, model, embedding model, etc.). Course documents live in `docs/` and are indexed into ChromaDB (`backend/chroma_db/`) on startup.
