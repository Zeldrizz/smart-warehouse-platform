#!/bin/bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "${SCRIPT_DIR}/_demo_common.sh"
trap demo_resume_generator EXIT

API_URL="${API_URL:-http://localhost:8001/api/v1/events}"
PRODUCT_ID="${PRODUCT_ID:-SKU-BASE-$RANDOM}"
ORDER_ID="${ORDER_ID:-ORDER-BASE-$RANDOM}"
BASE_TS="$(date -u +%s000)"

demo_prepare_manual_window

post() {
  local payload="$1"
  echo "POST $payload"
  curl -sS -X POST "$API_URL" -H "Content-Type: application/json" -d "$payload"
  echo
}

post "{\"event_id\":\"${PRODUCT_ID}-recv\",\"event_type\":\"PRODUCT_RECEIVED\",\"occurred_at\":${BASE_TS},\"product_id\":\"${PRODUCT_ID}\",\"zone_id\":\"ZONE-A\",\"quantity\":100}"
demo_wait_for_cql_contains \
  "SELECT JSON available_quantity FROM warehouse.inventory_by_product_zone WHERE product_id='${PRODUCT_ID}' AND zone_id='ZONE-A';" \
  '"available_quantity": 100'

post "{\"event_id\":\"${PRODUCT_ID}-reserve\",\"event_type\":\"PRODUCT_RESERVED\",\"occurred_at\":$((BASE_TS+1000)),\"product_id\":\"${PRODUCT_ID}\",\"zone_id\":\"ZONE-A\",\"quantity\":30}"
demo_wait_for_cql_contains \
  "SELECT JSON available_quantity, reserved_quantity FROM warehouse.inventory_by_product_zone WHERE product_id='${PRODUCT_ID}' AND zone_id='ZONE-A';" \
  '"available_quantity": 70'
demo_wait_for_cql_contains \
  "SELECT JSON available_quantity, reserved_quantity FROM warehouse.inventory_by_product_zone WHERE product_id='${PRODUCT_ID}' AND zone_id='ZONE-A';" \
  '"reserved_quantity": 30'

post "{\"event_id\":\"${PRODUCT_ID}-move\",\"event_type\":\"PRODUCT_MOVED\",\"occurred_at\":$((BASE_TS+2000)),\"product_id\":\"${PRODUCT_ID}\",\"from_zone_id\":\"ZONE-A\",\"to_zone_id\":\"ZONE-B\",\"quantity\":20}"
demo_wait_for_cql_contains \
  "SELECT JSON available_quantity, reserved_quantity FROM warehouse.inventory_by_product_zone WHERE product_id='${PRODUCT_ID}' AND zone_id='ZONE-A';" \
  '"available_quantity": 50'
demo_wait_for_cql_contains \
  "SELECT JSON available_quantity, reserved_quantity FROM warehouse.inventory_by_product_zone WHERE product_id='${PRODUCT_ID}' AND zone_id='ZONE-B';" \
  '"available_quantity": 20'

post "{\"event_id\":\"${PRODUCT_ID}-ship\",\"event_type\":\"PRODUCT_SHIPPED\",\"occurred_at\":$((BASE_TS+3000)),\"product_id\":\"${PRODUCT_ID}\",\"zone_id\":\"ZONE-A\",\"quantity\":10}"
demo_wait_for_cql_contains \
  "SELECT JSON available_quantity, reserved_quantity FROM warehouse.inventory_by_product_zone WHERE product_id='${PRODUCT_ID}' AND zone_id='ZONE-A';" \
  '"available_quantity": 40'

post "{\"event_id\":\"${ORDER_ID}-create\",\"event_type\":\"ORDER_CREATED\",\"occurred_at\":$((BASE_TS+4000)),\"order_id\":\"${ORDER_ID}\",\"items\":[{\"product_id\":\"${PRODUCT_ID}\",\"zone_id\":\"ZONE-A\",\"quantity\":15}]}"
demo_wait_for_cql_contains \
  "SELECT JSON available_quantity, reserved_quantity FROM warehouse.inventory_by_product_zone WHERE product_id='${PRODUCT_ID}' AND zone_id='ZONE-A';" \
  '"available_quantity": 25'
demo_wait_for_cql_contains \
  "SELECT JSON available_quantity, reserved_quantity FROM warehouse.inventory_by_product_zone WHERE product_id='${PRODUCT_ID}' AND zone_id='ZONE-A';" \
  '"reserved_quantity": 45'

post "{\"event_id\":\"${ORDER_ID}-complete\",\"event_type\":\"ORDER_COMPLETED\",\"occurred_at\":$((BASE_TS+5000)),\"order_id\":\"${ORDER_ID}\"}"
echo "Final ZONE-A state:"
demo_wait_for_cql_contains \
  "SELECT JSON product_id, zone_id, available_quantity, reserved_quantity FROM warehouse.inventory_by_product_zone WHERE product_id='${PRODUCT_ID}' AND zone_id='ZONE-A';" \
  '"reserved_quantity": 30'

echo "Final ZONE-B state:"
demo_wait_for_cql_contains \
  "SELECT JSON product_id, zone_id, available_quantity, reserved_quantity FROM warehouse.inventory_by_product_zone WHERE product_id='${PRODUCT_ID}' AND zone_id='ZONE-B';" \
  '"available_quantity": 20'

echo "Final product totals:"
demo_wait_for_cql_contains \
  "SELECT JSON product_id, total_available_quantity, total_reserved_quantity FROM warehouse.inventory_totals_by_product WHERE product_id='${PRODUCT_ID}';" \
  '"total_available_quantity": 45'
