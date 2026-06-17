#!/usr/bin/env bash
set -euo pipefail

PROJECT="rag-proyect-499005"
DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

echo "==> Proyecto: $PROJECT"
echo "==> Cuenta gcloud activa:"
gcloud config get-value account

echo "==> Creando canal de notificacion (email)..."
CHANNEL=$(gcloud beta monitoring channels create \
  --project="$PROJECT" \
  --channel-content-from-file="$DIR/notification-channel.json" \
  --format="value(name)")
echo "    Canal: $CHANNEL"

echo "==> Creando dashboard de SLIs..."
gcloud monitoring dashboards create \
  --project="$PROJECT" \
  --config-from-file="$DIR/dashboard.json"

for f in alert-availability alert-errors alert-latency; do
  echo "==> Creando politica de alerta: $f"
  tmp="$(mktemp)"
  sed "s|__CHANNEL__|$CHANNEL|g" "$DIR/$f.json" > "$tmp"
  gcloud alpha monitoring policies create \
    --project="$PROJECT" \
    --policy-from-file="$tmp"
  rm -f "$tmp"
done

echo "==> Listo. Revisa el dashboard en Cloud Monitoring > Dashboards > 'SLIs - rag-backend'."
