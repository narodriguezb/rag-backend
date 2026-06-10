# CI/CD — Backend

Documentación del flujo de integración y despliegue continuo del backend
(FastAPI + uv). Los workflows viven en `.github/workflows/`.

## Resumen

- Los **gates de calidad y seguridad** corren en **cada PR a `master`**.
- El **deploy** corre solo cuando hay commits en `master` (push/merge), y **solo
  si el gate de calidad pasa**.
- Dos reviews con **Claude** comentan automáticamente cada PR.

```
PR a master    ──► quality (lint, tests, mutation, Trivy, Snyk, Sonar)
                   + Claude code review + Claude security review (comentan el PR)
merge a master ──► quality ──► deploy (Cloud Run vía WIF)
```

## Workflows

| Archivo | Disparador | Qué hace |
|---|---|---|
| `ci.yml` | PR + push a `master` | Gate de calidad → deploy (gateado) |
| `code-review.yml` | PR a `master` | Claude revisa el diff y comenta (equiv. `/code-review`) |
| `security-review.yml` | PR a `master` | Claude hace revisión de seguridad y comenta (equiv. `/security-review`) |

### `ci.yml`

**Job `quality`** (corre en PR y en push). Pasos en orden:

1. **ruff** — linter de estilo e imports.
2. **pytest + coverage** — tests unitarios; genera `coverage.xml` para SonarQube.
3. **mutmut** — mutation testing; `scripts/mutation_gate.py 50` **falla si el
   score de mutación es < 50%**.
4. **Trivy** — escaneo de vulnerabilidades del filesystem (`CRITICAL,HIGH`, solo
   las que tienen fix disponible). Bloqueante.
5. **Snyk** — escaneo de vulnerabilidades en dependencias. Corre solo si existe
   el secret `SNYK_TOKEN`. Bloqueante (`--severity-threshold=high`).
6. **SonarQube Cloud** — análisis estático + cobertura. Corre solo si existe
   `SONAR_TOKEN`. **No bloqueante** (`continue-on-error`).

**Job `deploy`** (`needs: quality`, solo en push a `master`):

- Se autentica a Google Cloud con **Workload Identity Federation (WIF)** — sin
  claves JSON: GitHub OIDC asume la service account `gh-deployer`.
- Ejecuta `gcloud run deploy --source .`, que construye el `Dockerfile` con
  Cloud Build y publica en **Cloud Run**.
- La `ANTHROPIC_API_KEY` se inyecta desde **Secret Manager**
  (`--update-secrets`), nunca como texto plano.

### `code-review.yml` y `security-review.yml`

- Usan las actions oficiales `anthropics/claude-code-action` y
  `anthropics/claude-code-security-review`.
- Modelo: `claude-sonnet-4-6` (se puede subir a `claude-opus-4-8`).
- Necesitan `pull-requests: write` para comentar en el PR.
- Consumen tokens de la cuenta Anthropic en cada PR.

## Comandos locales (replican el gate)

```bash
uv run ruff check backend/                                   # lint
uv run pytest --cov=backend --cov-report=term-missing -q     # tests + coverage
uv run mutmut run                                            # mutation testing
uv run mutmut export-cicd-stats                              # vuelca stats a JSON
uv run python scripts/mutation_gate.py 50                    # gate >= 50%
```

## Secrets y variables

GitHub → *Settings → Secrets and variables → Actions*.

| Nombre | Tipo | Para qué |
|---|---|---|
| `ANTHROPIC_API_KEY` | secret | Reviews de Claude (code + security) |
| `SONAR_TOKEN` | secret | SonarQube Cloud (opcional) |
| `SNYK_TOKEN` | secret | Snyk (opcional) |

Si un secret opcional no está, su paso se salta sin romper el pipeline.

## Infraestructura (Google Cloud)

| Recurso | Valor |
|---|---|
| Proyecto | `rag-proyect-499005` |
| Servicio Cloud Run | `rag-backend` (región `us-central1`, 2Gi / 1 vCPU, escala a cero) |
| Secret | `ANTHROPIC_API_KEY` en Secret Manager |
| WIF | pool `github-pool`, provider `github-provider`, SA `gh-deployer@rag-proyect-499005.iam.gserviceaccount.com` (scope: owner `narodriguezb`) |

## Cómo probar

1. Crea una rama, haz commit y abre un **PR a `master`**.
2. En el PR verás correr `quality` + los dos reviews de Claude (comentan inline).
3. Al **mergear a `master`** se dispara el `deploy` a Cloud Run.
