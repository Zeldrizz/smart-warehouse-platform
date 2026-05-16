#!/bin/bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "${SCRIPT_DIR}/_demo_common.sh"
trap demo_resume_generator EXIT

API_URL="${API_URL:-http://localhost:8001/api/v1/events}"
PRODUCT_ID="${PRODUCT_ID:-SKU-OOO-$RANDOM}"
BASE_TS="$(date -u +%s000)"

demo_prepare_manual_window

curl -sS -X POST "$API_URL" -H "Content-Type: application/json" -d "{\"event_id\":\"${PRODUCT_ID}-recv-1\",\"event_type\":\"PRODUCT_RECEIVED\",\"occurred_at\":${BASE_TS},\"product_id\":\"${PRODUCT_ID}\",\"zone_id\":\"ZONE-A\",\"quantity\":100}"
echo
demo_wait_for_cql_contains \
  "SELECT JSON available_quantity FROM warehouse.inventory_by_product_zone WHERE product_id='${PRODUCT_ID}' AND zone_id='ZONE-A';" \
  '"available_quantity": 100'

curl -sS -X POST "$API_URL" -H "Content-Type: application/json" -d "{\"event_id\":\"${PRODUCT_ID}-ship-1\",\"event_type\":\"PRODUCT_SHIPPED\",\"occurred_at\":$((BASE_TS+300000)),\"product_id\":\"${PRODUCT_ID}\",\"zone_id\":\"ZONE-A\",\"quantity\":20}"
echo
demo_wait_for_cql_contains \
  "SELECT JSON available_quantity FROM warehouse.inventory_by_product_zone WHERE product_id='${PRODUCT_ID}' AND zone_id='ZONE-A';" \
  '"available_quantity": 80'

curl -sS -X POST "$API_URL" -H "Content-Type: application/json" -d "{\"event_id\":\"${PRODUCT_ID}-recv-old\",\"event_type\":\"PRODUCT_RECEIVED\",\"occurred_at\":$((BASE_TS+120000)),\"product_id\":\"${PRODUCT_ID}\",\"zone_id\":\"ZONE-A\",\"quantity\":50}"
echo
demo_wait_for_cql_contains \
  "SELECT event_id FROM warehouse.processed_events_by_id WHERE event_id='${PRODUCT_ID}-recv-old';" \
  "${PRODUCT_ID}-recv-old"
echo "Final state after stale event:"
demo_wait_for_cql_contains \
  "SELECT JSON product_id, zone_id, available_quantity, reserved_quantity FROM warehouse.inventory_by_product_zone WHERE product_id='${PRODUCT_ID}' AND zone_id='ZONE-A';" \
  '"available_quantity": 80'
