#!/bin/bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "${SCRIPT_DIR}/_demo_common.sh"

WMS_URL="${WMS_URL:-http://localhost:8001/api/v1/events}"
CONSUMER_URL="${CONSUMER_URL:-http://localhost:8002}"
PRODUCT_ID="${PRODUCT_ID:-SKU-LAG-$RANDOM}"
BASE_TS="$(date -u +%s000)"
CONSUMER_PAUSED=0
ARTIFACT_DIR="${SCRIPT_DIR}/../artifacts/prometheus/demo_monitoring"

mkdir -p "${ARTIFACT_DIR}"

cleanup() {
  if [[ "${CONSUMER_PAUSED}" == "1" ]]; then
    curl -sS -X POST "$CONSUMER_URL/admin/consumer/resume" >/dev/null || true
  fi
  demo_resume_generator
}

trap cleanup EXIT

post() {
  local payload="$1"
  echo "POST $payload"
  curl -sS -X POST "$WMS_URL" -H "Content-Type: application/json" -d "$payload"
  echo
}

capture_alert_snapshot() {
  local slug="$1"
  local query="$2"

  echo "Prometheus firing snapshot for ${slug}:"
  curl -sS -G http://localhost:9090/api/v1/query \
    --data-urlencode "query=${query}" | tee "${ARTIFACT_DIR}/${slug}-prometheus.json"
  echo

  echo "Alertmanager snapshot for ${slug}:"
  curl -sS http://localhost:9094/api/v2/alerts | tee "${ARTIFACT_DIR}/${slug}-alertmanager.json"
  echo
}

demo_pause_generator
demo_wait_for_low_lag

echo "Pausing consumer to accumulate lag"
curl -sS -X POST "$CONSUMER_URL/admin/consumer/pause"
CONSUMER_PAUSED=1
echo

post "{\"event_id\":\"${PRODUCT_ID}-001\",\"event_type\":\"PRODUCT_RECEIVED\",\"occurred_at\":${BASE_TS},\"product_id\":\"${PRODUCT_ID}\",\"zone_id\":\"ZONE-A\",\"quantity\":100}"
post "{\"event_id\":\"${PRODUCT_ID}-002\",\"event_type\":\"PRODUCT_RESERVED\",\"occurred_at\":$((BASE_TS+1000)),\"product_id\":\"${PRODUCT_ID}\",\"zone_id\":\"ZONE-A\",\"quantity\":10}"
post "{\"event_id\":\"${PRODUCT_ID}-003\",\"event_type\":\"PRODUCT_RELEASED\",\"occurred_at\":$((BASE_TS+2000)),\"product_id\":\"${PRODUCT_ID}\",\"zone_id\":\"ZONE-A\",\"quantity\":5}"
post "{\"event_id\":\"${PRODUCT_ID}-004\",\"event_type\":\"PRODUCT_MOVED\",\"occurred_at\":$((BASE_TS+3000)),\"product_id\":\"${PRODUCT_ID}\",\"from_zone_id\":\"ZONE-A\",\"to_zone_id\":\"ZONE-B\",\"quantity\":20}"
post "{\"event_id\":\"${PRODUCT_ID}-005\",\"event_type\":\"INVENTORY_COUNTED\",\"occurred_at\":$((BASE_TS+4000)),\"product_id\":\"${PRODUCT_ID}\",\"zone_id\":\"ZONE-B\",\"counted_quantity\":18}"
post "{\"event_id\":\"${PRODUCT_ID}-006\",\"event_type\":\"PRODUCT_RECEIVED\",\"occurred_at\":$((BASE_TS+5000)),\"product_id\":\"${PRODUCT_ID}\",\"zone_id\":\"ZONE-C\",\"quantity\":7}"
post "{\"event_id\":\"${PRODUCT_ID}-007\",\"event_type\":\"PRODUCT_RESERVED\",\"occurred_at\":$((BASE_TS+6000)),\"product_id\":\"${PRODUCT_ID}\",\"zone_id\":\"ZONE-A\",\"quantity\":15}"
post "{\"event_id\":\"${PRODUCT_ID}-008\",\"event_type\":\"PRODUCT_RELEASED\",\"occurred_at\":$((BASE_TS+7000)),\"product_id\":\"${PRODUCT_ID}\",\"zone_id\":\"ZONE-A\",\"quantity\":10}"
post "{\"event_id\":\"${PRODUCT_ID}-009\",\"event_type\":\"PRODUCT_SHIPPED\",\"occurred_at\":$((BASE_TS+8000)),\"product_id\":\"${PRODUCT_ID}\",\"zone_id\":\"ZONE-B\",\"quantity\":8}"
post "{\"event_id\":\"${PRODUCT_ID}-010\",\"event_type\":\"PRODUCT_RECEIVED\",\"occurred_at\":$((BASE_TS+9000)),\"product_id\":\"${PRODUCT_ID}\",\"zone_id\":\"ZONE-A\",\"quantity\":3}"

sleep 8
echo "Lag metrics while consumer is paused:"
curl -sS "${CONSUMER_URL}/metrics" | grep -E '^(consumer_lag|events_processed_total|cassandra_write_errors_total)'
echo

echo "Waiting for ConsumerLagHigh alert to fire..."
sleep 70
capture_alert_snapshot "consumer-lag-high" 'ALERTS{alertname="ConsumerLagHigh",alertstate="firing"}'

echo "Resuming consumer and checking lag recovery"
curl -sS -X POST "$CONSUMER_URL/admin/consumer/resume"
CONSUMER_PAUSED=0
echo
previous_lag_threshold="${DEMO_LAG_THRESHOLD}"
DEMO_LAG_THRESHOLD=0
demo_wait_for_low_lag
DEMO_LAG_THRESHOLD="${previous_lag_threshold}"
curl -sS "${CONSUMER_URL}/metrics" | grep -E '^consumer_lag'
echo

echo "Stopping consumer container to trigger ServiceDown"
docker stop smart-warehouse-consumer-service >/dev/null
sleep 75
capture_alert_snapshot "service-down" 'ALERTS{alertname="ServiceDown",alertstate="firing"}'

echo "Starting consumer container again"
docker start smart-warehouse-consumer-service >/dev/null
sleep 20
curl -sS "${CONSUMER_URL}/health"
echo

echo "Current alert state snapshot:"
curl -sS -G http://localhost:9090/api/v1/query --data-urlencode 'query=ALERTS' | tee "${ARTIFACT_DIR}/final-prometheus-alerts.json"
echo

echo "Alertmanager snapshot:"
curl -sS http://localhost:9094/api/v2/alerts | tee "${ARTIFACT_DIR}/final-alertmanager-alerts.json"
echo
