# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Course Materials RAG — Backend. A FastAPI service that powers a Retrieval-Augmented Generation system over course materials, using ChromaDB for vector storage and Google's Gemini (via Vertex AI) for generation. It exposes a JSON API consumed by the React frontend (separate repo: `../rag-frontend`).

> LLM provider migrated from Anthropic Claude to Gemini/Vertex AI on 2026-06-17 — see [`MIGRACION-GEMINI.md`](MIGRACION-GEMINI.md).

This repo is **API-only** — it does not serve any frontend. CORS is open for local development with the frontend dev server.

## Build & Run

```bash
uv sync                                                  # Install/lock dependencies
cp .env.example .env                                     # Vertex project/region (defaults already set)
gcloud auth application-default login                    # ADC for Vertex AI (local only)

./run.sh                                                 # Preferred: start the API
# or
cd backend && uv run uvicorn app:app --reload --port 8000
```

The API runs at `http://localhost:8000`. Always use `uv` (never `pip` directly); let `uv` manage all dependencies and run all Python.

## API

All endpoints in `backend/app.py`:
- `GET /` — health check (`{ status, service }`)
- `POST /api/query` — `{ query, session_id? }` → `{ answer, sources, session_id }`
- `GET /api/courses` — `{ total_courses, course_titles }`

## Architecture

The backend follows a modular orchestration pattern.

| Module (`backend/`) | Responsibility |
|---|---|
| `app.py` | FastAPI app, CORS, request/response models, API endpoints, startup doc loading |
| `rag_system.py` | Main orchestrator wiring all components together |
| `document_processor.py` | Chunks course documents (with overlap) |
| `vector_store.py` | ChromaDB interface for semantic search |
| `ai_generator.py` | Gemini (Vertex AI) integration with function-calling tool support |
| `session_manager.py` | Conversation history per session |
| `search_tools.py` | Tool-based search exposed to the model |
| `models.py` | Pydantic models (courses, lessons, chunks) |
| `config.py` | Configuration from environment variables |

### Key Patterns
- **Tool-based search:** the model (Gemini) calls a defined `CourseSearchTool` via function calling rather than doing direct vector similarity in the handler.
- **Sessions:** conversation context is maintained per `session_id` with configurable history (`MAX_HISTORY`).
- **Deduplication:** course documents are deduplicated by title.
- **Lean handlers:** endpoints in `app.py` delegate to `rag_system`; no business logic in HTTP handlers.

## Data Flow
1. On startup, documents in `docs/` are processed and chunked.
2. Chunks are embedded and stored in ChromaDB (`backend/chroma_db/`).
3. A user query triggers a tool-based search via Gemini (function calling).
4. Gemini uses `CourseSearchTool` to retrieve relevant content.
5. The answer is generated with sources, and session context is updated.

## Configuration

Key settings in `backend/config.py`:
- `CHUNK_SIZE: 800` — text chunk size for vector storage
- `CHUNK_OVERLAP: 100` — character overlap between chunks
- `MAX_RESULTS: 5` — maximum search results returned
- `MAX_HISTORY: 2` — conversation messages remembered
- `EMBEDDING_MODEL: "all-MiniLM-L6-v2"` — sentence-transformer model
- `GEMINI_MODEL` — Gemini model id (default `gemini-2.5-flash`)
- `VERTEX_PROJECT_ID` / `VERTEX_LOCATION` — Vertex AI project and region (default `rag-proyect-499005` / `us-central1`)

## Environment Variables
- `GEMINI_MODEL`, `VERTEX_PROJECT_ID`, `VERTEX_LOCATION` — Vertex AI config (defaults in `config.py`).
- `ENABLE_LOAD_ENDPOINT` — when truthy, exposes `GET /api/load` (synthetic CPU load for k6); off by default.
- Auth uses **ADC**, not an API key: `gcloud auth application-default login` locally; the Cloud Run service account (`roles/aiplatform.user`) in production.

## Development Guidelines

### Code Quality
- **Always remove comments at the end**: clean up explanatory comments after a change. Keep code self-documenting; only keep comments for genuinely non-obvious logic.
- Scan files you touch — remove unused imports, variables, and dead branches.

### Conventions
- Requires Python 3.13+.
- Always use `uv` to run the server and Python files; `uv` manages all dependencies.
- Keep handlers lean — delegate to `rag_system` and the modules above.

## Important Notes
- Uses tool-based search rather than direct similarity search.
- ChromaDB storage persists in `backend/chroma_db/` (gitignored; rebuilt from `docs/` on startup).
- Never edit / commit secret paths: `.env`, `.venv/`, `__pycache__/`, `backend/chroma_db/`.
