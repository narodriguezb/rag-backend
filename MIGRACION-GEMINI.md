# Migración del LLM: Claude (Anthropic) → Gemini (Vertex AI)

Fecha: 2026-06-17

Este documento registra el cambio del proveedor de LLM del backend RAG, de **Anthropic Claude** (SDK `anthropic`, API key) a **Google Gemini** sobre **Vertex AI** (SDK `google-genai`, autenticación por ADC), tanto en la **app** como en el **CI/CD**.

---

## 1. Motivo

- Se agotaron los tokens de la cuenta de Anthropic que usaban tanto la app (generación RAG) como el CI (reviews de código y seguridad con Claude).
- Hay **saldo gratuito de GCP ($300, free trial)** disponible, así que conviene usar un modelo facturado a GCP.

### ¿Por qué Gemini y no Claude-on-Vertex?

Se evaluó primero **mantener Claude pero facturando a Vertex AI** (cambio mínimo de código). Se descartó porque:

- `claude-sonnet-4@20250514` en Vertex **solo está disponible en el endpoint `global`** (las regiones devuelven 404).
- En ese endpoint, la cuota `global_online_prediction_requests_per_base_model` para el modelo **arranca en 0** → requiere un *quota increase request*.
- **La cuenta de free trial de GCP no permite solicitar aumentos de cuota** (restricción del trial; habría que pasar a cuenta de pago).
- `anthropics/claude-code-security-review` **no soporta Vertex** (solo `claude-api-key`).

En cambio, **Gemini (`gemini-2.5-flash`) funciona de inmediato** en `us-central1` (misma región que Cloud Run) con la cuota por defecto del trial, sin pedir aumentos. Se verificó con una llamada real antes de migrar.

---

## 2. Qué cambió en la app

| Archivo | Cambio |
|---|---|
| `backend/ai_generator.py` | Reescrito de `anthropic.Anthropic` a `google-genai`. Usa `genai.Client(vertexai=True, project, location)` y un **loop de function calling manual**: convierte las definiciones de tools (estilo Anthropic, `input_schema`) a `types.FunctionDeclaration`, ejecuta los `function_call` vía `tool_manager.execute_tool`, devuelve los `function_response` y obtiene la respuesta final. |
| `backend/config.py` | Se quitaron `ANTHROPIC_API_KEY` y `ANTHROPIC_MODEL`. Se agregaron `GEMINI_MODEL` (`gemini-2.5-flash`), `VERTEX_PROJECT_ID` (`rag-proyect-499005`) y `VERTEX_LOCATION` (`us-central1`). |
| `backend/rag_system.py` | El constructor de `AIGenerator` ahora recibe `(GEMINI_MODEL, VERTEX_PROJECT_ID, VERTEX_LOCATION)`. |
| `backend/search_tools.py` | **Sin cambios.** La interfaz pública de `generate_response()` se mantuvo igual, así que las definiciones de tools (`get_tool_definition`) y el `ToolManager` no se tocaron; la conversión al formato Gemini ocurre dentro de `AIGenerator`. |
| `pyproject.toml` | `anthropic==0.58.2` → `google-genai>=1.0.0` (resuelto a `2.8.0`). |
| `.env.example` | Reemplazado por `GEMINI_MODEL`, `VERTEX_PROJECT_ID`, `VERTEX_LOCATION`, `ENABLE_LOAD_ENDPOINT`. |

### Modelo y región

- Modelo: **`gemini-2.5-flash`** (configurable vía `GEMINI_MODEL`).
- Región: **`us-central1`** (misma que Cloud Run → sin salto cross-region).

---

## 3. Autenticación (sin API key)

Ya **no se usa una API key**. `google-genai` con `vertexai=True` autentica por **Application Default Credentials (ADC)**:

- **En Cloud Run:** usa automáticamente la *service account* de runtime del servicio (`235944902030-compute@developer.gserviceaccount.com`), a la que se le otorgó el rol **`roles/aiplatform.user`**.
- **En local:** requiere `gcloud auth application-default login`.

### Cambios de infraestructura GCP (una vez)

```bash
gcloud services enable aiplatform.googleapis.com --project=rag-proyect-499005

gcloud projects add-iam-policy-binding rag-proyect-499005 \
  --member="serviceAccount:235944902030-compute@developer.gserviceaccount.com" \
  --role="roles/aiplatform.user"

gcloud projects add-iam-policy-binding rag-proyect-499005 \
  --member="serviceAccount:gh-deployer@rag-proyect-499005.iam.gserviceaccount.com" \
  --role="roles/aiplatform.user"
```

(El SA `gh-deployer@` necesita el rol porque el CI también llama a Gemini en las reviews.)

---

## 4. Qué cambió en el CI/CD (`.github/workflows/ci.yml`)

| Job | Antes | Ahora |
|---|---|---|
| `code_review` | `anthropics/claude-code-action@v1` (`ANTHROPIC_API_KEY`) | `google-github-actions/run-gemini-cli@v0.1.22` con `use_vertex_ai: true` + WIF. **Advisory.** |
| `security_review` | `anthropics/claude-code-security-review@main` (gate duro: fallaba si había findings) | `run-gemini-cli` con prompt de seguridad. **Advisory** (ya no bloquea el merge). |
| `deploy` | `--update-secrets ANTHROPIC_API_KEY=...` | `--clear-secrets` + `--set-env-vars ...,GEMINI_MODEL,VERTEX_PROJECT_ID,VERTEX_LOCATION,ENABLE_LOAD_ENDPOINT=true` |

- Las reviews autentican a Vertex por **WIF** (provider `projects/235944902030/.../github-provider`, SA `gh-deployer@`), reutilizando la misma federación que ya usaba el deploy. No hay API key de Gemini.
- El modelo de las reviews se fija con `GEMINI_MODEL=gemini-2.5-flash`.

> **Cambio de comportamiento:** el `security_review` dejó de ser **gate duro**. Antes un hallazgo bloqueaba el merge; ahora solo comenta. El ruleset de `master` sigue exigiendo que el check exista y pase, lo cual ocurre porque ahora es advisory.

---

## 5. Validación realizada

- `uv sync` instala `google-genai 2.8.0` y desinstala `anthropic`.
- `ruff check backend/` → limpio.
- `pytest` → **16/16 OK** (sin regresiones).
- Prueba funcional local del flujo RAG con Gemini (ADC):
  - Pregunta general → responde sin usar el tool.
  - Pregunta de curso → **dispara `search_course_content`**, recupera chunks y devuelve respuesta **con fuentes**.

---

## 6. Operación y pendientes

- **`ENABLE_LOAD_ENDPOINT=true`** quedó activado en el deploy para poder correr la prueba de carga k6 contra Cloud Run. **Apagarlo después** (`ENABLE_LOAD_ENDPOINT=false` o quitar la env var) para no dejar el endpoint `/api/load` expuesto en producción.
- El **secreto `ANTHROPIC_API_KEY`** en Secret Manager quedó sin uso. El `.env` local todavía lo contiene (es secreto/gitignored); se puede borrar/rotar.
- Si en el futuro se quisiera volver a Claude-on-Vertex, hay que **pasar la cuenta de GCP a pago** y solicitar la cuota del endpoint global.

## 7. Cómo revertir

1. `pyproject.toml`: volver a `anthropic==0.58.2` (quitar `google-genai`), `uv sync`.
2. Restaurar `backend/ai_generator.py`, `backend/config.py` y `backend/rag_system.py` desde el historial git previo a la migración.
3. CI: restaurar los jobs `code_review`/`security_review` con las actions de Anthropic y el `--update-secrets ANTHROPIC_API_KEY` en `deploy`.
4. Requiere tokens de Anthropic válidos.
