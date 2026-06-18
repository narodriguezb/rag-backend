# Monitoreo — Golden signals del backend (Cloud Monitoring)

Observabilidad del servicio Cloud Run `rag-backend` usando **métricas nativas de Cloud Run**
(`run.googleapis.com/*`), sin instrumentar código de la app. Este directorio define el **dashboard**
y las **alertas** que las visualizan y vigilan.

## Contenido

| Archivo | Qué define |
|---|---|
| `dashboard.json` | Dashboard "SLIs - rag-backend" (7 widgets) |
| `alert-availability.json` | Alerta: disponibilidad (2xx/total) < 99% |
| `alert-errors.json` | Alerta: errores 5xx (5xx/total) > 1% |
| `alert-latency.json` | Alerta: latencia p95 > 8000 ms |
| `notification-channel.json` | Canal de notificación por email |
| `apply.sh` | Crea el canal + el dashboard + las 3 alertas |

## SLOs

| SLI | Objetivo | Métrica nativa |
|---|---|---|
| Disponibilidad | **≥ 99%** (ratio 2xx/total) | `request_count` |
| Latencia p95 | **< 8 s** | `request_latencies` |
| Errores 5xx | **< 1%** (ratio 5xx/total) | `request_count` |

Las alertas usan ventana de 60 s (`alignmentPeriod` 60 s + `duration` 60 s) y notifican por email.
Disponibilidad y errores se evalúan como **ratio** (no rate) para no dar falsos positivos cuando el
servicio escala a cero. El umbral de latencia es 8 s porque las queries RAG tardan segundos.

## Widgets del dashboard

1. Tasa de errores 5xx · 2. Latencia p95 · 3. Disponibilidad (2xx) · 4. Instancias activas ·
5. Cold start (p95 startup latency) · 6. Saturación CPU y memoria · 7. Throttling (429/seg).

## Aplicar

Requiere los componentes `beta` y `alpha` de gcloud:

```bash
gcloud components install beta alpha --quiet
export CLOUDSDK_PYTHON=/usr/bin/python3 PYENV_VERSION=system
./apply.sh
```

`apply.sh` crea el canal de email, el dashboard y las 3 políticas de alerta en el proyecto
`rag-proyect-499005`. El email destino se define en `notification-channel.json`, y debe quedar
**verificado** (`verificationStatus: VERIFIED`) para que se envíen las notificaciones.

### Actualizar un dashboard ya creado

`gcloud monitoring dashboards update` exige el `etag` actual:

```bash
export CLOUDSDK_PYTHON=/usr/bin/python3 PYENV_VERSION=system
ETAG=$(gcloud monitoring dashboards describe <DASHBOARD_ID> --project=rag-proyect-499005 --format="value(etag)")
jq --arg e "$ETAG" '. + {etag:$e}' dashboard.json > /tmp/dash.json
gcloud monitoring dashboards update <DASHBOARD_ID> --project=rag-proyect-499005 --config-from-file=/tmp/dash.json
```

## Generar tráfico

El servicio **escala a cero**, así que el dashboard se ve plano sin tráfico. Para verlo moverse y
disparar las alertas, corré la prueba de carga: ver la sección **Pruebas de carga (k6)** del
[`README`](../README.md).
