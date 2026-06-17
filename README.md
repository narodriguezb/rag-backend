# Course Materials RAG — Backend

FastAPI backend for the Course Materials RAG system. Serves a JSON API consumed by the React frontend (separate repo).

## Requirements

- Python 3.13+
- [uv](https://docs.astral.sh/uv/)
- A Google Cloud project with Vertex AI enabled + ADC (`gcloud auth application-default login`)

## Setup

```bash
uv sync
cp .env.example .env                      # Vertex project/region (defaults already set)
gcloud auth application-default login     # ADC for Vertex AI (local)
```

> El LLM se migró de Anthropic Claude a **Gemini (Vertex AI)** — ver [`MIGRACION-GEMINI.md`](MIGRACION-GEMINI.md).

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

## Monitoring (golden signals)

Cloud Monitoring dashboard + SLO alerts for the Cloud Run service, built from Cloud Run **native
metrics** (no app code). SLOs: availability ≥ 99%, p95 latency < 8 s, 5xx errors < 1%. Definitions
and how to apply them (`apply.sh`) live in [`monitoring/`](monitoring/README.md).

## Load testing (k6)

`K6/load-test.js` drives load against the service. Three sequenced scenarios: **warmup** (isolates
cold start) → **browse** (`GET /`, `/api/courses`; SLO thresholds p95 < 8 s, failures < 1%) →
**saturate** (hammers `GET /api/load`, a CPU-bound synthetic endpoint, to surface cold starts /
throttling).

```bash
brew install k6                                   # one-time
k6 run K6/load-test.js                            # against the live Cloud Run URL (default)
QUICK=1 BASE_URL=http://localhost:8000 k6 run K6/load-test.js   # fast local smoke
```

Env knobs: `BASE_URL`, `QUICK=1` (short run), `LOAD_ROWS` / `LOAD_ITER` (work per request).

> `GET /api/load` is gated behind `ENABLE_LOAD_ENDPOINT` (returns 404 when off). Enable it only for
> load tests; the live dashboard in `monitoring/` only moves while traffic is flowing.

## CI/CD

Pipeline de GitHub Actions (`.github/workflows/ci.yml`): en cada **PR a `master`** corren los
gates de calidad y las reviews de Gemini; al **mergear a `master`** se despliega a Cloud Run vía
Workload Identity Federation.

```
PR a master    ──► quality + code_review + security_review (Gemini, advisory)
merge a master ──► quality ──► deploy (Cloud Run)
```

📄 **Documentación completa del flujo en [`CICD.md`](CICD.md)** — cada job paso a paso, gates y
umbrales, protección de rama, autenticación WIF, secrets, despliegue cacheado y troubleshooting.
