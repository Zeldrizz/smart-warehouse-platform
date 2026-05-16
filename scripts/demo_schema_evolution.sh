#!/bin/bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "${SCRIPT_DIR}/_demo_common.sh"
trap demo_resume_generator EXIT

API_URL="${API_URL:-http://localhost:8001/api/v1/events}"
REGISTRY_URL="${REGISTRY_URL:-http://localhost:8081}"
BASE_TS="$(date -u +%s000)"
PRODUCT_V1="${PRODUCT_V1:-SKU-V1-DEMO-$RANDOM}"
PRODUCT_V2="${PRODUCT_V2:-SKU-V2-DEMO-$RANDOM}"

demo_prepare_manual_window

curl -sS -X POST "$API_URL" -H "Content-Type: application/json" -d "{\"event_id\":\"schema-v1-$RANDOM\",\"event_type\":\"PRODUCT_RECEIVED\",\"occurred_at\":${BASE_TS},\"schema_version\":\"v1\",\"product_id\":\"${PRODUCT_V1}\",\"zone_id\":\"ZONE-A\",\"quantity\":10}"
echo
echo "V1 Cassandra row with supplier_id=null:"
demo_wait_for_cql_contains \
  "SELECT JSON product_id, zone_id, supplier_id FROM warehouse.inventory_by_product WHERE product_id='${PRODUCT_V1}';" \
  '"supplier_id": null'

curl -sS -X POST "$API_URL" -H "Content-Type: application/json" -d "{\"event_id\":\"schema-v2-$RANDOM\",\"event_type\":\"PRODUCT_RECEIVED\",\"occurred_at\":$((BASE_TS+1000)),\"schema_version\":\"v2\",\"product_id\":\"${PRODUCT_V2}\",\"zone_id\":\"ZONE-B\",\"quantity\":15,\"supplier_id\":\"SUP-001\"}"
echo
echo "V2 Cassandra row with supplier_id=SUP-001:"
demo_wait_for_cql_contains \
  "SELECT JSON product_id, zone_id, supplier_id FROM warehouse.inventory_by_product WHERE product_id='${PRODUCT_V2}';" \
  '"supplier_id": "SUP-001"'

echo "Inspect schema versions and compatibility:"
curl -sS "${REGISTRY_URL}/subjects/warehouse-events-value/versions"
echo
curl -sS "${REGISTRY_URL}/config/warehouse-events-value"
echo
