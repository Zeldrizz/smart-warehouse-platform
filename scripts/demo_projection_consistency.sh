#!/bin/bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "${SCRIPT_DIR}/_demo_common.sh"
trap demo_resume_generator EXIT

API_URL="${API_URL:-http://localhost:8001/api/v1/events}"
PRODUCT_ID="${PRODUCT_ID:-SKU-PROJECTION-$RANDOM}"
BASE_TS="$(date -u +%s000)"

demo_prepare_manual_window

curl -sS -X POST "$API_URL" -H "Content-Type: application/json" -d "{\"event_id\":\"${PRODUCT_ID}-recv-${BASE_TS}\",\"event_type\":\"PRODUCT_RECEIVED\",\"occurred_at\":${BASE_TS},\"product_id\":\"${PRODUCT_ID}\",\"zone_id\":\"ZONE-A\",\"quantity\":100}"
echo

echo "inventory_by_product_zone"
demo_wait_for_cql_contains \
  "SELECT product_id, zone_id, available_quantity, reserved_quantity FROM warehouse.inventory_by_product_zone WHERE product_id='${PRODUCT_ID}' AND zone_id='ZONE-A';" \
  "${PRODUCT_ID}"

echo "inventory_totals_by_product"
demo_wait_for_cql_contains \
  "SELECT product_id, total_available_quantity, total_reserved_quantity FROM warehouse.inventory_totals_by_product WHERE product_id='${PRODUCT_ID}';" \
  "${PRODUCT_ID}"

echo "inventory_by_zone"
demo_wait_for_cql_contains \
  "SELECT zone_id, product_id, available_quantity, reserved_quantity FROM warehouse.inventory_by_zone WHERE zone_id='ZONE-A' AND product_id='${PRODUCT_ID}';" \
  "${PRODUCT_ID}"
