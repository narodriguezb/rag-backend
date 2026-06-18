# CLAUDE.md

Guía para Claude Code (claude.ai/code) al trabajar en este repositorio.

## Descripción del proyecto

Course Materials RAG — Backend. Servicio FastAPI que implementa un sistema de Retrieval-Augmented
Generation sobre materiales de curso, usando ChromaDB para el almacenamiento vectorial y Gemini (vía
Vertex AI) para la generación. Expone una API JSON que consume el frontend React (repo aparte:
`../rag-frontend`).

Este repo es **solo API** — no sirve ningún frontend. CORS está abierto para desarrollo local con el
dev server del frontend.

## Build y ejecución

```bash
uv sync                                                  # instala/locka dependencias
cp .env.example .env                                     # proyecto/región de Vertex (defaults ya puestos)
gcloud auth application-default login                    # ADC para Vertex AI (solo local)

./run.sh                                                 # preferido: arranca la API
# o
cd backend && uv run uvicorn app:app --reload --port 8000
```

La API corre en `http://localhost:8000`. Usar siempre `uv` (nunca `pip` directo); dejar que `uv`
gestione todas las dependencias y ejecute todo Python.

## API

Todos los endpoints en `backend/app.py`:
- `GET /` — health check (`{ status, service }`)
- `POST /api/query` — `{ query, session_id? }` → `{ answer, sources, session_id }`
- `GET /api/courses` — `{ total_courses, course_titles }`

## Arquitectura

El backend sigue un patrón de orquestación modular.

| Módulo (`backend/`) | Responsabilidad |
|---|---|
| `app.py` | App FastAPI, CORS, modelos request/response, endpoints, carga de documentos al arranque |
| `rag_system.py` | Orquestador principal que conecta todos los componentes |
| `document_processor.py` | Chunkea los documentos de curso (con overlap) |
| `vector_store.py` | Interfaz a ChromaDB para búsqueda semántica |
| `ai_generator.py` | Integración con Gemini (Vertex AI) con soporte de function calling |
| `session_manager.py` | Historial de conversación por sesión |
| `search_tools.py` | Búsqueda basada en herramientas expuesta al modelo |
| `models.py` | Modelos Pydantic (cursos, lecciones, chunks) |
| `config.py` | Configuración desde variables de entorno |

### Patrones clave
- **Búsqueda basada en herramientas:** el modelo (Gemini) llama a `CourseSearchTool` vía function
  calling en lugar de hacer búsqueda vectorial directa en el handler.
- **Sesiones:** el contexto de conversación se mantiene por `session_id` con historial configurable
  (`MAX_HISTORY`).
- **Deduplicación:** los documentos de curso se deduplican por título.
- **Handlers livianos:** los endpoints en `app.py` delegan en `rag_system`; sin lógica de negocio en
  los handlers HTTP.

## Flujo de datos
1. Al arrancar, los documentos en `docs/` se procesan y chunkean.
2. Los chunks se embeben y se guardan en ChromaDB (`backend/chroma_db/`).
3. Una query dispara una búsqueda basada en herramientas vía Gemini (function calling).
4. Gemini usa `CourseSearchTool` para recuperar el contenido relevante.
5. La respuesta se genera con fuentes y se actualiza el contexto de sesión.

## Configuración

Ajustes clave en `backend/config.py`:
- `CHUNK_SIZE: 800` — tamaño de chunk de texto para el vector store
- `CHUNK_OVERLAP: 100` — overlap de caracteres entre chunks
- `MAX_RESULTS: 5` — máximo de resultados de búsqueda
- `MAX_HISTORY: 2` — mensajes de conversación recordados
- `EMBEDDING_MODEL: "all-MiniLM-L6-v2"` — modelo sentence-transformer
- `GEMINI_MODEL` — id del modelo Gemini (default `gemini-2.5-flash`)
- `VERTEX_PROJECT_ID` / `VERTEX_LOCATION` — proyecto y región de Vertex AI (default `rag-proyect-499005` / `us-central1`)

## Variables de entorno
- `GEMINI_MODEL`, `VERTEX_PROJECT_ID`, `VERTEX_LOCATION` — config de Vertex AI (defaults en `config.py`).
- `ENABLE_LOAD_ENDPOINT` — cuando es truthy, expone `GET /api/load` (carga sintética para k6); apagado por defecto.
- Auth por **ADC**, no API key: `gcloud auth application-default login` en local; la service account
  de Cloud Run (`roles/aiplatform.user`) en producción.

## Guías de desarrollo

### Calidad de código
- **Eliminar comentarios al final:** limpiar comentarios explicativos tras un cambio. Mantener el
  código autoexplicativo; conservar comentarios solo para lógica genuinamente no obvia.
- Al tocar un archivo, eliminar imports, variables y ramas muertas que queden sin uso.

### Convenciones
- Requiere Python 3.13+.
- Usar siempre `uv` para correr el server y los archivos Python; `uv` gestiona las dependencias.
- Mantener los handlers livianos — delegar en `rag_system` y los módulos de arriba.

## Notas importantes
- Usa búsqueda basada en herramientas, no búsqueda por similitud directa.
- El almacenamiento de ChromaDB persiste en `backend/chroma_db/` (gitignored; se reconstruye desde
  `docs/` al arrancar).
- Nunca editar / commitear rutas secretas: `.env`, `.venv/`, `__pycache__/`, `backend/chroma_db/`.
