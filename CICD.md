# CI/CD — Backend (`rag-backend`)

Documentación del pipeline de integración y despliegue continuo.
Resumen y enlace en el [README](README.md#cicd). Definición: [`.github/workflows/ci.yml`](.github/workflows/ci.yml).

---

## Tabla de contenidos

- [Stack y herramientas](#stack-y-herramientas)

1. [Visión general](#1-visión-general)
2. [Disparadores](#2-disparadores)
3. [Job `quality`](#3-job-quality)
4. [Reviews con Gemini](#4-reviews-con-gemini)
5. [Job `deploy`](#5-job-deploy)
6. [Protección de rama (ruleset)](#6-protección-de-rama-ruleset)
7. [Autenticación: Workload Identity Federation](#7-autenticación-workload-identity-federation)
8. [Secrets y variables](#8-secrets-y-variables)
9. [Reproducir los gates en local](#9-reproducir-los-gates-en-local)
10. [Infraestructura (GCP)](#10-infraestructura-gcp)
11. [Troubleshooting](#11-troubleshooting)

---

## 1. Visión general

El pipeline tiene dos fases: **gates** (calidad + seguridad) y **deploy**. Los gates corren en cada
Pull Request a `master`; el deploy corre solo cuando los cambios aterrizan en `master` (merge), y
únicamente si la fase de gates pasó.

```
                    ┌─────────────────────── PR a master ───────────────────────┐
                    │                                                            │
   commit  ─────►   │  quality            code_review (Gemini)   security_review │
   en una rama      │  (lint, tests,      (comenta el diff,      (Gemini;        │
                    │   mutation, scan)    advisory)             advisory)        │
                    └────────────────────────────┬───────────────────────────────┘
                                                  │  (ruleset exige quality + security_review)
                                                  ▼
                                            merge a master
                                                  │
                                                  ▼
                                   quality ──► deploy (Cloud Run vía WIF)
```

| Job | Evento | ¿Bloquea el merge? |
|-----|--------|--------------------|
| `quality` | `pull_request` + `push` a master | **Sí** (check requerido) |
| `code_review` | `pull_request` | No (advisory) |
| `security_review` | `pull_request` | No (advisory) |
| `security_report` | `pull_request` | No (informativo; comentario sticky) |
| `deploy` | `push` a master | — (corre post-merge) |

---

## Stack y herramientas

### Aplicación
| Herramienta | Rol |
|---|---|
| Python 3.13 | runtime |
| FastAPI + uvicorn | API HTTP |
| ChromaDB | vector store |
| sentence-transformers (`all-MiniLM-L6-v2`) | embeddings |
| Google Gemini `gemini-2.5-flash` (SDK `google-genai`, Vertex AI, auth ADC) | generación RAG |
| `uv` | gestión de dependencias y entorno |

### Calidad y seguridad (en CI)
| Herramienta | Versión / ref | Rol |
|---|---|---|
| ruff | dev dep | lint + orden de imports |
| pytest + pytest-cov | dev dep | tests unitarios + cobertura (`coverage.xml`) |
| mutmut | `>=3,<4` | mutation testing (gate ≥50%, `scripts/mutation_gate.py`) |
| Gitleaks | `gitleaks/gitleaks-action@v2` | escaneo de secretos (**gate pre-merge**, en `quality`) |
| Trivy | `aquasecurity/trivy-action@master` | escaneo de vulnerabilidades (filesystem/deps) |
| SonarQube Cloud | `SonarSource/sonarqube-scan-action@v6` | análisis estático + cobertura (advisory) |
| Gemini code review | `google-github-actions/run-gemini-cli@v0.1.22` (Vertex AI vía WIF) | revisión de código (advisory) |
| Gemini security review | `google-github-actions/run-gemini-cli@v0.1.22` (Vertex AI vía WIF) | revisión de seguridad (advisory) |

### Build y deploy
| Herramienta | Versión / ref (pin) | Rol |
|---|---|---|
| `astral-sh/setup-uv` | `@v5` | instala `uv` + Python 3.13 |
| Docker Buildx | `docker/setup-buildx-action@8d2750c…` | builder |
| build-push-action | `docker/build-push-action@10e90e3…` | build + push de la imagen |
| login-action | `docker/login-action@c94ce9f…` | login a Artifact Registry |
| `google-github-actions/auth` | `@v2` | WIF (OIDC → GCP), `token_format: access_token` |
| `google-github-actions/setup-gcloud` | `@v2` | CLI `gcloud` |

> Las actions de Docker están **fijadas a commit SHA** (no a tags mutables) porque manejan el access
> token del registry — mitigación de cadena de suministro.

### Plataforma
| Servicio | Rol |
|---|---|
| GitHub Actions | orquestación CI/CD |
| GitHub Rulesets | protección de rama (gate del merge/deploy) |
| Google Cloud Run | hosting del backend |
| Artifact Registry | registro de imágenes Docker |
| Vertex AI | LLM (Gemini) en runtime y en las reviews, vía ADC/WIF |
| Workload Identity Federation | autenticación sin claves JSON (deploy + reviews + Vertex) |

---

## 2. Disparadores

```yaml
on:
  push:
    branches: [master]   # merge a master -> quality + deploy
  pull_request:
    branches: [master]   # PR -> quality + reviews de Gemini
  workflow_dispatch:     # ejecución manual
```

Permisos del `GITHUB_TOKEN`: `contents: read`, `id-token: write` (necesario para WIF) y
`pull-requests: write` (para que las reviews de Gemini comenten).

---

## 3. Job `quality`

Runner `ubuntu-latest`. Instala el entorno con [`uv`](https://docs.astral.sh/uv/) (Python **3.13**
fijado explícitamente). Pasos en orden:

| # | Paso | Comando / Action | Falla si… |
|---|------|------------------|-----------|
| 0 | Gitleaks (secretos) | `gitleaks/gitleaks-action@v2` (historial git) | encuentra un secreto; falsos positivos se silencian en `.gitleaksignore` |
| 1 | Lint | `uv run ruff check backend/` | hay errores de estilo/imports |
| 2 | Tests + cobertura | `uv run pytest --cov=backend --cov-report=xml -q` | falla un test; genera `coverage.xml` para SonarQube |
| 3 | Mutation testing | `uv run mutmut run` → `mutmut export-cicd-stats` → `python scripts/mutation_gate.py 50` | el *mutation score* es **< 50%** |
| 4 | Trivy (SCA/IaC) | `aquasecurity/trivy-action` (`scan-type: fs`, `severity: CRITICAL`, `ignore-unfixed: true`) | hay vulnerabilidades **CRITICAL** con fix disponible |
| 5 | SonarQube Cloud | `SonarSource/sonarqube-scan-action` (`continue-on-error: true`) | **no bloquea** (advisory); solo corre si existe `SONAR_TOKEN` |

### Gate de mutación

`scripts/mutation_gate.py` lee `mutants/mutmut-cicd-stats.json` y calcula
`score = killed / (total - skipped) * 100`. Sale con código ≠ 0 si `score < 50`.
El scope de mutación se define en `setup.cfg` (`[mutmut] source_paths`, `pytest_add_cli_args_test_selection`).

---

## 4. Reviews con Gemini

Dos jobs independientes que solo corren en `pull_request` (revisan el *diff*). Ambos usan
`google-github-actions/run-gemini-cli@v0.1.22` (CLI pineada a `0.45.0`) con `use_vertex_ai: true`,
modelo `gemini-2.5-flash`, autenticando a Vertex AI por **WIF** (mismo provider y SA `gh-deployer@`
que el deploy). **No se usa API key.**

```yaml
- uses: google-github-actions/run-gemini-cli@v0.1.22
  with:
    gemini_cli_version: "0.45.0"
    gemini_model: gemini-2.5-flash
    use_vertex_ai: true
    gcp_workload_identity_provider: projects/235944902030/.../providers/github-provider
    gcp_service_account: gh-deployer@rag-proyect-499005.iam.gserviceaccount.com
    gcp_project_id: rag-proyect-499005
    gcp_location: us-central1
    gcp_token_format: access_token
    settings: '{"model":{"name":"gemini-2.5-flash"},"experimental":{"useModelRouter":false}}'
    prompt: |
      ... (review de código / de seguridad)
```

### `code_review` (advisory)

Comenta el PR con bugs, calidad y buenas prácticas. **No bloquea** el merge.

### `security_review` (advisory)

Audita el diff buscando vulnerabilidades (injection, broken authn/authz, secrets, SSRF,
deserialización insegura, path traversal, dependencias riesgosas) y comenta los hallazgos. El check
es requerido por el ruleset, pero es advisory (no falla por hallazgos).

### `security_report` (reporte consolidado, no bloqueante)

Job extra (solo en `pull_request`) que junta la salida de seguridad en un **comentario sticky** del
PR (se actualiza en cada push, no spammea):

- Corre **Trivy en modo reporte** (`CRITICAL,HIGH,MEDIUM`, **incluye sin-fix**, `exit-code: 0`),
  arma una tabla markdown con `jq` (severidad · paquete · versión · fix · ID) y la postea con
  `marocchino/sticky-pull-request-comment@v2` (header `security-report`).
- Apunta además a los hallazgos de **Gemini**, **Snyk** y **SonarQube**.
- **No bloquea.** El gate determinístico es el Trivy del job `quality` (falla ante CRITICAL con fix);
  este reporte muestra el panorama completo (incluye MEDIUM y sin-fix).

---

## 5. Job `deploy`

`needs: quality`, y solo corre en `push` a `master`
(`if: github.ref == 'refs/heads/master' && github.event_name == 'push'`).

> Los review jobs corren solo en PR, por eso `deploy` no los lleva en `needs`; el bloqueo real lo
> aplica el [ruleset](#6-protección-de-rama-ruleset) al impedir el merge si fallan.

Pasos:

1. **Auth a GCP** (`google-github-actions/auth@v2`) vía WIF, con `token_format: access_token`.
2. **Login a Artifact Registry** (`docker/login-action`) usando ese access token
   (`username: oauth2accesstoken`).
3. **Build + push** (`docker/build-push-action`):
   ```yaml
   tags: us-central1-docker.pkg.dev/rag-proyect-499005/cloud-run-source-deploy/rag-backend:${{ github.sha }}
   ```

   > El `Dockerfile` es **multi-stage**: la etapa *builder* instala `build-essential` + `uv` y compila
   > el `.venv`; la etapa *runtime* (slim, solo `libgomp1`) copia ese `.venv` y el código. Así los
   > compiladores no llegan a la imagen final (menor tamaño y superficie de ataque).
   >
   > **torch CPU-only:** `pyproject.toml` fija `torch` al índice `pytorch-cpu` (`[tool.uv.sources]`,
   > marker `sys_platform == 'linux'`), evitando ~2GB de libs CUDA inútiles en Cloud Run (sin GPU).
4. **Deploy** por imagen (sin rebuild en Cloud Build):
   ```bash
   gcloud run deploy rag-backend \
     --image "$IMAGE:${{ github.sha }}" \
     --region us-central1 --allow-unauthenticated \
     --memory 2Gi --cpu 1 --cpu-boost --timeout 300 --max-instances 1 \
     --clear-secrets \
     --set-env-vars BUILD_VERSION=${{ github.sha }},GEMINI_MODEL=gemini-2.5-flash,VERTEX_PROJECT_ID=rag-proyect-499005,VERTEX_LOCATION=us-central1,ENABLE_LOAD_ENDPOINT=true
   ```

   > El LLM autentica por **ADC** (la service account de runtime tiene `roles/aiplatform.user`).
   > `ENABLE_LOAD_ENDPOINT=true` activa el endpoint sintético `/api/load` para las pruebas k6.

### Marcador de versión

`BUILD_VERSION` se inyecta como variable de entorno y la app la imprime al arrancar:

```
=== rag-backend startup OK | build=<sha> ===
```

Verificación en logs:

```bash
gcloud run services logs read rag-backend \
  --project rag-proyect-499005 --region us-central1 --limit 50 | grep "startup OK"
```

---

## 6. Protección de rama (ruleset)

`master` tiene un **repository ruleset** (`enforcement: active`) que exige:

- **Pull request** antes de integrar (no se puede pushear directo a master).
- **Required status checks**: `quality` y `security_review` deben pasar.
- Bloquea borrado de la rama y force-push (`deletion`, `non_fast_forward`).

El gate real del deploy es `quality` (bloqueante). `security_review` es requerido pero advisory.
`code_review` y `SonarQube` no son requeridos (informativos).

> Los rulesets en repos privados requieren GitHub Pro; por eso este repo es **público**.

---

## 7. Autenticación: Workload Identity Federation

No se usan claves JSON de service account. GitHub emite un token OIDC que se intercambia por
credenciales de GCP:

| Recurso | Valor |
|---------|-------|
| Workload Identity Pool | `github-pool` |
| OIDC Provider | `github-provider` (condición: `repository_owner == narodriguezb`) |
| Service Account | `gh-deployer@rag-proyect-499005.iam.gserviceaccount.com` |

Roles de la SA `gh-deployer@`: `run.admin`, `artifactregistry.writer`, `iam.serviceAccountUser`,
`cloudbuild.builds.editor`, `storage.admin` y **`aiplatform.user`** (para las reviews con Gemini en
Vertex). La SA de runtime de Cloud Run (`235944902030-compute@developer.gserviceaccount.com`) tiene
**`aiplatform.user`** para llamar a Gemini vía ADC.

---

## 8. Secrets y variables

GitHub → *Settings → Secrets and variables → Actions*.

| Nombre | Tipo | Uso | Si falta… |
|--------|------|-----|-----------|
| `SONAR_TOKEN` | secret | SonarQube Cloud | el step de Sonar se salta |

> Las reviews y el runtime autentican a Vertex AI por **WIF/ADC**, sin secrets de LLM.

---

## 9. Reproducir los gates en local

```bash
uv sync --dev
uv run ruff check backend/
uv run pytest --cov=backend --cov-report=term-missing -q
uv run mutmut run && uv run mutmut export-cicd-stats && uv run python scripts/mutation_gate.py 50
```

---

## 10. Infraestructura (GCP)

| Recurso | Valor |
|---------|-------|
| Proyecto | `rag-proyect-499005` (nº `235944902030`) |
| Cloud Run | servicio `rag-backend`, región `us-central1`, 2Gi / 1 vCPU, escala a cero |
| Artifact Registry | `us-central1-docker.pkg.dev/rag-proyect-499005/cloud-run-source-deploy` |
| Vertex AI | Gemini `gemini-2.5-flash` en `us-central1` (ADC; SA con `roles/aiplatform.user`) |
| URL | https://rag-backend-235944902030.us-central1.run.app |

---

## 11. Troubleshooting

| Síntoma | Causa | Solución |
|---------|-------|----------|
| `Install dependencies` falla: `onnxruntime ... no wheel for cp314` | `uv` eligió Python 3.14 (el `.python-version` está gitignored) | el workflow fija `python-version: "3.13"` en `setup-uv` |
| `code_review`/`security_review` falla autenticando a GCP | el SA `gh-deployer@` no tiene `roles/aiplatform.user`, o el WIF no resuelve | otorgar el rol; verificar provider/SA del WIF |
| Gemini CLI: *not running in a trusted directory* | feature de "trusted folders" en modo headless | setear `GEMINI_CLI_TRUST_WORKSPACE: "true"` en el `env` del step |
| Gemini responde `404 model not found` (`gemini-3.x…`) | versiones nuevas de la gemini-cli defaultean a Gemini 3.x + model router | pinear `gemini_cli_version: "0.45.0"`, `gemini_model: gemini-2.5-flash` y `settings: '{"model":{"name":"gemini-2.5-flash"},"experimental":{"useModelRouter":false}}'` |
| Gemini responde `429 RESOURCE_EXHAUSTED` | cuota del modelo agotada | revisar cuotas de Vertex |
| Build falla en el preload: `OSError: couldn't connect to 'https://huggingface.co'` | descarga del modelo en build-time falló (transitorio) | el `RUN` del preload reintenta 3× y es best-effort: el build no falla; el modelo se baja en el primer arranque |
