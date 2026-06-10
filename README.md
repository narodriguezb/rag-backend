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

## CI/CD

GitHub Actions pipeline en `.github/workflows/ci.yml`.

- **PR a `master`** → corren los gates de calidad y las reviews de Claude.
- **Push/merge a `master`** → corren los gates y, si pasan, el **deploy** a Cloud Run.

```
PR a master    ──► quality + code_review (Claude) + security_review (Claude)
merge a master ──► quality ──► deploy (Cloud Run vía WIF)
```

### Jobs

| Job | Cuándo | Qué hace |
|-----|--------|----------|
| `quality` | PR + push | ruff (lint) → pytest + coverage → mutation testing (mutmut, gate ≥50% vía `scripts/mutation_gate.py`) → Trivy (CRITICAL) → SonarQube (no bloqueante) |
| `code_review` | PR | Claude revisa el diff y comenta (`anthropics/claude-code-action`, advisory) |
| `security_review` | PR | Claude revisa seguridad; **falla el check si encuentra hallazgos** (`claude-code-security-review`) |
| `deploy` | push a `master` | build con `buildx` + **caché de capas (GHA)** → push a Artifact Registry → `gcloud run deploy --image`. Inyecta `BUILD_VERSION` (visible en logs: `=== rag-backend startup OK | build=<sha> ===`) |

### Gate del deploy

`master` está protegida por un **ruleset** que exige PR + que pasen los checks `quality` y
`security_review`. Si la revisión de seguridad de Claude encuentra algo, no se puede mergear →
no hay deploy. El deploy autentica a GCP con **Workload Identity Federation** (sin claves JSON).

### Secrets (GitHub → Settings → Secrets and variables → Actions)

| Nombre | Para qué |
|--------|----------|
| `ANTHROPIC_API_KEY` | Reviews de Claude (code + security) |
| `SONAR_TOKEN` | SonarQube Cloud (opcional; el step se salta si falta) |

> Para que `code_review` (Claude) pueda comentar, hay que instalar la **GitHub App de Claude**
> (https://github.com/apps/claude) en el repo.

### Reproducir los gates en local

```bash
uv run ruff check backend/
uv run pytest --cov=backend --cov-report=term-missing -q
uv run mutmut run && uv run mutmut export-cicd-stats && uv run python scripts/mutation_gate.py 50
```

Infra: Cloud Run service `rag-backend` (proyecto `rag-proyect-499005`, región `us-central1`),
con `ANTHROPIC_API_KEY` desde Secret Manager.
