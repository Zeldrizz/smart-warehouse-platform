#!/bin/bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "${SCRIPT_DIR}/_demo_common.sh"
trap demo_resume_generator EXIT

API_URL="${API_URL:-http://localhost:8001/api/v1/events}"
CONSUMER_URL="${CONSUMER_URL:-http://localhost:8002}"
SCHEMA_REGISTRY_URL="${SCHEMA_REGISTRY_URL:-http://schema-registry:8081}"
PRODUCT_ID="${PRODUCT_ID:-SKU-DLQ-$RANDOM}"
BASE_TS="$(date -u +%s000)"

demo_prepare_manual_window

curl -sS -X POST "$API_URL" -H "Content-Type: application/json" -d "{\"event_id\":\"${PRODUCT_ID}-invalid\",\"event_type\":\"PRODUCT_SHIPPED\",\"occurred_at\":${BASE_TS},\"product_id\":\"${PRODUCT_ID}\",\"zone_id\":\"ZONE-A\",\"quantity\":-5}"
echo
sleep 4

echo "Consumer health after invalid event:"
curl -sS "${CONSUMER_URL}/health"
echo

echo "Matching DLQ message from warehouse-events-dlq:"
docker exec hw7-schema-registry bash -lc "timeout 15s kafka-avro-console-consumer --bootstrap-server kafka-1:29092 --topic warehouse-events-dlq --property schema.registry.url=${SCHEMA_REGISTRY_URL} --from-beginning | grep -F '${PRODUCT_ID}-invalid'" || true
echo

echo "Sending a valid event after the invalid one:"
curl -sS -X POST "$API_URL" -H "Content-Type: application/json" -d "{\"event_id\":\"${PRODUCT_ID}-valid\",\"event_type\":\"PRODUCT_RECEIVED\",\"occurred_at\":$((BASE_TS+1000)),\"product_id\":\"${PRODUCT_ID}-VALID\",\"zone_id\":\"ZONE-A\",\"quantity\":10}"
echo
demo_wait_for_cql_contains \
  "SELECT product_id, zone_id, available_quantity, reserved_quantity FROM warehouse.inventory_by_product_zone WHERE product_id='${PRODUCT_ID}-VALID' AND zone_id='ZONE-A';" \
  "${PRODUCT_ID}-VALID"
