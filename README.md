# Course Materials RAG — Backend

Backend FastAPI del sistema RAG sobre materiales de curso. Expone una API JSON que consume el
frontend React (repo aparte). Recupera contenido relevante con búsqueda semántica (ChromaDB) y
genera las respuestas con **Gemini (Vertex AI)**.

## Requisitos

- Python 3.13+
- [uv](https://docs.astral.sh/uv/)
- Un proyecto de Google Cloud con Vertex AI habilitado + ADC (`gcloud auth application-default login`)

## Instalación

```bash
uv sync
cp .env.example .env                      # proyecto/región de Vertex (defaults ya puestos)
gcloud auth application-default login     # ADC para Vertex AI (local)
```

## Ejecutar

```bash
chmod +x run.sh
./run.sh
# o
cd backend && uv run uvicorn app:app --reload --port 8000
```

La API corre en `http://localhost:8000`.

## API

- `GET /` — health check
- `POST /api/query` — `{ query, session_id? }` → `{ answer, sources, session_id }`
- `GET /api/courses` — `{ total_courses, course_titles }`

CORS abierto (`*`) para desarrollo local con el dev server del frontend.

## Configuración

Ver `backend/config.py` (tamaño de chunk, modelo, modelo de embeddings, etc.). Los documentos de
curso viven en `docs/` y se indexan en ChromaDB (`backend/chroma_db/`) al arrancar.

## Generación (Gemini / Vertex AI)

La generación usa **`gemini-2.5-flash`** vía el SDK `google-genai` sobre Vertex AI, con **búsqueda
basada en herramientas** (function calling): el modelo invoca `CourseSearchTool` para recuperar el
contenido relevante antes de responder. La autenticación es por **ADC** (sin API key): en Cloud Run
usa la service account de runtime (`roles/aiplatform.user`); en local, `gcloud auth
application-default login`.

## Monitoreo (golden signals)

Dashboard de Cloud Monitoring + alertas de SLO para el servicio de Cloud Run, construidas sobre las
**métricas nativas de Cloud Run** (`run.googleapis.com/*`), sin tocar código de la app. SLOs:
disponibilidad ≥ 99%, latencia p95 < 8 s, errores 5xx < 1%. Las definiciones y cómo aplicarlas
(`apply.sh`) están en [`monitoring/`](monitoring/README.md).

## Pruebas de carga (k6)

`K6/load-test.js` genera tráfico contra el servicio. Tres escenarios secuenciados:

- **warmup** — aísla el cold start (`GET /`).
- **browse** — tráfico normal (`GET /`, `GET /api/courses`) con thresholds de SLO (p95 < 8 s, fallos < 1%).
- **breach** — golpea `GET /api/load` (endpoint sintético) con `ms` y `fail` para violar los SLOs a
  propósito y disparar las alertas: el 90% de los requests tarda ~12 s (latencia p95 > 8 s) y el 10%
  devuelve 500 (errores 5xx > 1% y disponibilidad < 99%).

```bash
brew install k6                                   # una vez
k6 run K6/load-test.js                            # contra la URL de Cloud Run (default)
QUICK=1 BASE_URL=http://localhost:8000 k6 run K6/load-test.js   # smoke local rápido
```

Variables: `BASE_URL`, `QUICK=1` (corrida corta), `LOAD_ROWS` / `LOAD_ITER` (trabajo por request),
`LOAD_MS` (delay server-side, default 12000), `LOAD_FAIL` (% de 500, default 10).

> `GET /api/load` está protegido por `ENABLE_LOAD_ENDPOINT` (devuelve 404 si está apagado). Se activa
> solo para las pruebas de carga; el dashboard de `monitoring/` solo se mueve mientras hay tráfico.

## CI/CD

Pipeline de GitHub Actions (`.github/workflows/ci.yml`): en cada **PR a `master`** corren los gates
de calidad y las reviews de Gemini; al **mergear a `master`** se despliega a Cloud Run vía Workload
Identity Federation.

```
PR a master    ──► quality + code_review + security_review (Gemini, advisory)
merge a master ──► quality ──► deploy (Cloud Run)
```

📄 **Documentación completa del flujo en [`CICD.md`](CICD.md)** — cada job paso a paso, gates y
umbrales, protección de rama, autenticación WIF, secrets y troubleshooting.
