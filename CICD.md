# CI/CD — Backend (`rag-backend`)

Documentación detallada del pipeline de integración y despliegue continuo.
Resumen y enlace en el [README](README.md#cicd). Definición: [`.github/workflows/ci.yml`](.github/workflows/ci.yml).

---

## Tabla de contenidos

- [Stack y herramientas](#stack-y-herramientas)

1. [Visión general](#1-visión-general)
2. [Disparadores](#2-disparadores)
3. [Job `quality`](#3-job-quality)
4. [Reviews con Claude (`code_review` / `security_review`)](#4-reviews-con-claude)
5. [Job `deploy`](#5-job-deploy)
6. [Protección de rama (ruleset)](#6-protección-de-rama-ruleset)
7. [Autenticación: Workload Identity Federation](#7-autenticación-workload-identity-federation)
8. [Secrets y variables](#8-secrets-y-variables)
9. [Reproducir los gates en local](#9-reproducir-los-gates-en-local)
10. [Infraestructura (GCP)](#10-infraestructura-gcp)
11. [Troubleshooting](#11-troubleshooting)

---

## 1. Visión general

El pipeline tiene dos fases: **gates** (calidad + seguridad) y **deploy**. Los gates corren
en cada Pull Request a `master`; el deploy corre solo cuando los cambios aterrizan en `master`
(merge), y únicamente si la fase de gates pasó.

```
                    ┌─────────────────────── PR a master ───────────────────────┐
                    │                                                            │
   commit  ─────►   │  quality            code_review (Claude)   security_review │
   en una rama      │  (lint, tests,      (comenta el diff,      (Claude; falla  │
                    │   mutation, scan)    advisory)             si hay hallazgos)│
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
| `security_review` | `pull_request` | **Sí** (check requerido) |
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
| Anthropic Claude (SDK `anthropic`) | generación RAG |
| `uv` | gestión de dependencias y entorno |

### Calidad y seguridad (en CI)
| Herramienta | Versión / ref | Rol |
|---|---|---|
| ruff | dev dep | lint + orden de imports |
| pytest + pytest-cov | dev dep | tests unitarios + cobertura (`coverage.xml`) |
| mutmut | `>=3,<4` | mutation testing (gate ≥50%, `scripts/mutation_gate.py`) |
| Trivy | `aquasecurity/trivy-action@master` | escaneo de vulnerabilidades (filesystem/deps) |
| SonarQube Cloud | `SonarSource/sonarqube-scan-action@v4` | análisis estático + cobertura |
| Claude code review | `anthropics/claude-code-action@v1` | revisión de código (advisory) |
| Claude security review | `anthropics/claude-code-security-review@main` | revisión de seguridad (gate) |

### Build y deploy
| Herramienta | Versión / ref (pin) | Rol |
|---|---|---|
| `astral-sh/setup-uv` | `@v5` | instala `uv` + Python 3.13 |
| Docker Buildx | `docker/setup-buildx-action@8d2750c…` | builder con caché |
| build-push-action | `docker/build-push-action@10e90e3…` | build + push de la imagen |
| login-action | `docker/login-action@c94ce9f…` | login a Artifact Registry |
| `google-github-actions/auth` | `@v2` | WIF (OIDC → GCP), `token_format: access_token` |
| `google-github-actions/setup-gcloud` | `@v2` | CLI `gcloud` |

> Las actions de Docker están **fijadas a commit SHA** (no a tags `@v3/@v6`) porque manejan el
> access token del registry — mitigación de cadena de suministro pedida por el `security_review`.

### Caché (clave para deploys rápidos)
| Caché | Mecanismo | Efecto |
|---|---|---|
| Capas de la imagen Docker | `cache-from: type=gha` / `cache-to: type=gha,mode=max` en `build-push-action` | reutiliza la capa pesada de `torch`/deps; el primer deploy llena la caché (~10 min), los siguientes ~1-2 min |
| Dependencias `uv` | `setup-uv` con `enable-cache: true` | acelera `uv sync` en el job `quality` |

### Plataforma
| Servicio | Rol |
|---|---|
| GitHub Actions | orquestación CI/CD |
| GitHub Rulesets | protección de rama (gate del merge/deploy) |
| Google Cloud Run | hosting del backend |
| Artifact Registry | registro de imágenes Docker |
| Secret Manager | `ANTHROPIC_API_KEY` en runtime |
| Workload Identity Federation | autenticación sin claves JSON |

---

## 2. Disparadores

```yaml
on:
  push:
    branches: [master]   # merge a master -> quality + deploy
  pull_request:
    branches: [master]   # PR -> quality + reviews de Claude
  workflow_dispatch:     # ejecución manual
```

Permisos del `GITHUB_TOKEN`: `contents: read`, `id-token: write` (necesario para WIF) y
`pull-requests: write` (para que las reviews de Claude comenten).

---

## 3. Job `quality`

Runner `ubuntu-latest`. Instala el entorno con [`uv`](https://docs.astral.sh/uv/) (Python **3.13**
fijado explícitamente — ver [Troubleshooting](#11-troubleshooting)). Pasos en orden:

| # | Paso | Comando / Action | Falla si… |
|---|------|------------------|-----------|
| 1 | Lint | `uv run ruff check backend/` | hay errores de estilo/imports |
| 2 | Tests + cobertura | `uv run pytest --cov=backend --cov-report=xml -q` | falla un test; genera `coverage.xml` para SonarQube |
| 3 | Mutation testing | `uv run mutmut run` → `mutmut export-cicd-stats` → `python scripts/mutation_gate.py 50` | el *mutation score* es **< 50%** |
| 4 | Trivy (SCA/IaC) | `aquasecurity/trivy-action` (`scan-type: fs`, `severity: CRITICAL`, `ignore-unfixed: true`) | hay vulnerabilidades **CRITICAL** con fix disponible |
| 5 | SonarQube Cloud | `SonarSource/sonarqube-scan-action` (`continue-on-error: true`) | **no bloquea** (informativo); solo corre si existe `SONAR_TOKEN` |

### Gate de mutación

`scripts/mutation_gate.py` lee `mutants/mutmut-cicd-stats.json` y calcula
`score = killed / (total - skipped) * 100`. Sale con código ≠ 0 si `score < 50`.
El scope de mutación se define en `setup.cfg` (`[mutmut] source_paths`, `pytest_add_cli_args_test_selection`).

---

## 4. Reviews con Claude

Dos jobs independientes que solo corren en `pull_request` (revisan el *diff*).

### `code_review` (advisory)

- Action: `anthropics/claude-code-action@v1`, modelo `claude-sonnet-4-6`.
- Comenta el PR con bugs / calidad / buenas prácticas. **No bloquea** el merge.
- Requiere la **GitHub App de Claude** instalada en el repo (https://github.com/apps/claude);
  si no, el token-exchange falla con 401.

### `security_review` (gate)

- Action: `anthropics/claude-code-security-review@main`, modelo `claude-sonnet-4-6`.
- Audita el diff buscando vulnerabilidades y comenta los hallazgos.
- La action expone el output `findings-count`; un paso posterior hace `exit 1` si es `> 0`:

  ```yaml
  - name: Fail if security findings
    if: ${{ steps.sec.outputs.findings-count > 0 }}
    run: exit 1
  ```
- Es check **requerido** por el ruleset → si Claude encuentra algo, **bloquea el merge**.

> No usa la GitHub App; autentica con `ANTHROPIC_API_KEY` directamente.

---

## 5. Job `deploy`

`needs: quality`, y solo corre en `push` a `master`
(`if: github.ref == 'refs/heads/master' && github.event_name == 'push'`).

> Los review jobs corren solo en PR, por eso `deploy` no los lleva en `needs`; el bloqueo real
> lo aplica el [ruleset](#6-protección-de-rama-ruleset) al impedir el merge si fallan.

Pasos:

1. **Auth a GCP** (`google-github-actions/auth@v2`) vía WIF, con `token_format: access_token`.
2. **Login a Artifact Registry** (`docker/login-action`) usando ese access token
   (`username: oauth2accesstoken`).
3. **Build + push con caché** (`docker/build-push-action`):
   ```yaml
   tags: us-central1-docker.pkg.dev/rag-proyect-499005/cloud-run-source-deploy/rag-backend:${{ github.sha }}
   cache-from: type=gha
   cache-to: type=gha,mode=max
   ```
   Reutiliza las capas (incluida la pesada de `torch`) entre runs → solo reconstruye lo que cambia.
4. **Deploy** por imagen (no por `--source`, así no se reconstruye en Cloud Build):
   ```bash
   gcloud run deploy rag-backend \
     --image "$IMAGE:${{ github.sha }}" \
     --region us-central1 --allow-unauthenticated \
     --memory 2Gi --cpu 1 --cpu-boost --timeout 300 --max-instances 1 \
     --set-env-vars BUILD_VERSION=${{ github.sha }} \
     --update-secrets ANTHROPIC_API_KEY=ANTHROPIC_API_KEY:latest
   ```

> Todas las actions de Docker están **fijadas a commit SHA** (no a tags mutables) porque manejan
> el access token del registry — mitiga ataques de cadena de suministro (hallazgo detectado por el
> propio `security_review`).

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

Efecto: si el `security_review` de Claude falla (encontró algo), **el PR no se puede mergear**, por
lo tanto **no hay deploy**. `code_review` y `SonarQube` no son requeridos (informativos).

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

Roles de la SA: `run.admin`, `artifactregistry.writer`, `iam.serviceAccountUser`,
`cloudbuild.builds.editor`, `storage.admin`. La SA de runtime de Cloud Run tiene
`secretmanager.secretAccessor` sobre `ANTHROPIC_API_KEY`.

---

## 8. Secrets y variables

GitHub → *Settings → Secrets and variables → Actions*.

| Nombre | Tipo | Uso | Si falta… |
|--------|------|-----|-----------|
| `ANTHROPIC_API_KEY` | secret | reviews de Claude | `security_review`/`code_review` no pueden correr |
| `SONAR_TOKEN` | secret | SonarQube Cloud | el step de Sonar se salta |

> Los secrets nunca van en el repo. La API key de runtime de Cloud Run se lee desde **Secret Manager**
> (`--update-secrets`), no como texto plano.

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
| Secret Manager | `ANTHROPIC_API_KEY` |
| URL | https://rag-backend-235944902030.us-central1.run.app |

---

## 11. Troubleshooting

| Síntoma | Causa | Solución |
|---------|-------|----------|
| `Install dependencies` falla: `onnxruntime ... no wheel for cp314` | `uv` eligió Python 3.14 (el `.python-version` está gitignored) | el workflow fija `python-version: "3.13"` en `setup-uv` |
| `code_review` falla en ~25s: *Claude Code is not installed* | falta la GitHub App de Claude | instalar https://github.com/apps/claude en el repo |
| `code_review` falla: *Workflow validation failed... identical content on default branch* | el PR modifica `ci.yml` (aún no está en master) | normal al cambiar el workflow; se resuelve al mergear |
| `security_review` falla con `findings-count > 0` | Claude encontró un hallazgo real | corregir el hallazgo (es el gate funcionando), p. ej. fijar actions a SHA |
| El deploy tarda ~10 min | primera vez: caché de capas fría | runs siguientes reutilizan la caché (~1-2 min) |

> Snyk se removió del workflow (se colgaba escaneando el árbol de dependencias de ML). El primer
> deploy histórico usaba `gcloud run deploy --source` (rebuild completo en cada deploy); ahora se usa
> `buildx` + caché + deploy por imagen.
