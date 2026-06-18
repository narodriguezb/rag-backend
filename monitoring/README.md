# Monitoreo — Golden signals del backend (Cloud Monitoring)

Observabilidad del servicio Cloud Run `rag-backend` usando **métricas nativas de Cloud Run**
(`run.googleapis.com/*`), sin tocar código de la app. Inspirado en el repo de clase `cicdtraining`,
adaptado a este servicio.

> Las métricas nativas las emite Cloud Run solo; este directorio solo define el **dashboard** y las
> **alertas** que las visualizan/vigilan.

## Contenido

| Archivo | Qué define |
|---|---|
| `dashboard.json` | Dashboard "SLIs - rag-backend" (7 widgets) |
| `alert-availability.json` | Alerta: disponibilidad (2xx/total) < 99% |
| `alert-errors.json` | Alerta: errores 5xx (5xx/total) > 1% |
| `alert-latency.json` | Alerta: latencia p95 > 8000 ms |
| `notification-channel.json` | Canal de notificación por email |
| `apply.sh` | Crea el canal + dashboard + las 3 alertas |

## SLOs

| SLI | Objetivo | Métrica nativa |
|---|---|---|
| Disponibilidad | **≥ 99%** (ratio 2xx/total) | `request_count` |
| Latencia p95 | **< 8 s** | `request_latencies` |
| Errores 5xx | **< 1%** (ratio 5xx/total) | `request_count` |

> Difieren del tutorial: las alertas de disponibilidad/errores son **ratio** (no *rate*) para no dar
> falsos positivos cuando el servicio escala a cero; la latencia usa `ALIGN_PERCENTILE_95`; ventana
> de 60 s (`alignmentPeriod` 60 s + `duration` 60 s) para que disparen durante una prueba de carga
> sin esperar 5 min sostenidos. La p95 < 500 ms del tutorial **no aplica** a un RAG (las queries
> tardan segundos), por eso 8 s.
>
> **Nota sobre 5xx:** al saturar con `maxScale=1`, Cloud Run responde **429** (clase 4xx), no 5xx, así
> que la alerta de errores 5xx no dispara por carga; bajo saturación disparan **latencia p95** y
> **disponibilidad** (los 429 bajan el ratio 2xx/total). El canal de email debe estar **verificado**
> (`verificationStatus: VERIFIED`) o no se envían correos aunque la alerta dispare.

## Widgets del dashboard

1. Tasa de errores 5xx · 2. Latencia p95 · 3. Disponibilidad (2xx) · 4. Instancias activas ·
5. **Cold start** (p95 startup latency) · 6. **Saturación** CPU y memoria · 7. **Throttling** (429/seg).

## Aplicar

Requiere los componentes `beta` y `alpha` de gcloud y el workaround de pyenv de este Mac:

```bash
gcloud components install beta alpha --quiet
export CLOUDSDK_PYTHON=/usr/bin/python3 PYENV_VERSION=system
./apply.sh
```

`apply.sh` crea el canal de email, el dashboard y las 3 políticas de alerta en el proyecto
`rag-proyect-499005` (cuenta `nestorx211@gmail.com`). El email destino se define en
`notification-channel.json`.

### Actualizar un dashboard ya creado

`gcloud monitoring dashboards update` exige el `etag` actual:

```bash
export CLOUDSDK_PYTHON=/usr/bin/python3 PYENV_VERSION=system
ETAG=$(gcloud monitoring dashboards describe <DASHBOARD_ID> --project=rag-proyect-499005 --format="value(etag)")
jq --arg e "$ETAG" '. + {etag:$e}' dashboard.json > /tmp/dash.json
gcloud monitoring dashboards update <DASHBOARD_ID> --project=rag-proyect-499005 --config-from-file=/tmp/dash.json
```

## Nota

El servicio **escala a cero**, así que el dashboard se ve plano sin tráfico. Para verlo moverse
(cold starts, saturación, 429) corré la prueba de carga: ver la sección **Load testing (k6)** del
[`README`](../README.md).
