#!/bin/bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "${SCRIPT_DIR}/_demo_common.sh"
trap demo_resume_generator EXIT

API_URL="${API_URL:-http://localhost:8001/api/v1/events}"
EVENT_ID="${EVENT_ID:-IDEMPOTENT-$RANDOM}"
PRODUCT_ID="${PRODUCT_ID:-SKU-IDEMPOTENT-$RANDOM}"
BASE_TS="$(date -u +%s000)"
PAYLOAD="{\"event_id\":\"${EVENT_ID}\",\"event_type\":\"PRODUCT_RECEIVED\",\"occurred_at\":${BASE_TS},\"product_id\":\"${PRODUCT_ID}\",\"zone_id\":\"ZONE-A\",\"quantity\":50}"

demo_prepare_manual_window

curl -sS -X POST "$API_URL" -H "Content-Type: application/json" -d "$PAYLOAD"
echo
demo_wait_for_cql_contains \
  "SELECT JSON available_quantity FROM warehouse.inventory_by_product_zone WHERE product_id='${PRODUCT_ID}' AND zone_id='ZONE-A';" \
  '"available_quantity": 50'

curl -sS -X POST "$API_URL" -H "Content-Type: application/json" -d "$PAYLOAD"
echo
echo "Final state after duplicate event with the same event_id:"
demo_wait_for_cql_contains \
  "SELECT JSON product_id, zone_id, available_quantity, reserved_quantity FROM warehouse.inventory_by_product_zone WHERE product_id='${PRODUCT_ID}' AND zone_id='ZONE-A';" \
  '"available_quantity": 50'
