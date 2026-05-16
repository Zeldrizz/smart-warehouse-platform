#!/bin/bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "${SCRIPT_DIR}/_demo_common.sh"
trap demo_resume_generator EXIT

API_URL="${API_URL:-http://localhost:8001/api/v1/events}"
STATE_FILE="${STATE_FILE:-/tmp/smart-warehouse-report-demo-state.env}"
PRODUCT_ID="${PRODUCT_ID:-SKU-FAILOVER-$RANDOM}"
BASE_TS="$(date -u +%s000)"

demo_prepare_manual_window

echo "Initial cluster status:"
docker exec smart-warehouse-cassandra-1 nodetool status
echo

docker stop smart-warehouse-cassandra-2
curl -sS -X POST "$API_URL" -H "Content-Type: application/json" -d "{\"event_id\":\"${PRODUCT_ID}-recv-${BASE_TS}\",\"event_type\":\"PRODUCT_RECEIVED\",\"occurred_at\":${BASE_TS},\"product_id\":\"${PRODUCT_ID}\",\"zone_id\":\"ZONE-A\",\"quantity\":200}"
echo
curl -sS -X POST "$API_URL" -H "Content-Type: application/json" -d "{\"event_id\":\"${PRODUCT_ID}-ship-${BASE_TS}\",\"event_type\":\"PRODUCT_SHIPPED\",\"occurred_at\":$((BASE_TS+1000)),\"product_id\":\"${PRODUCT_ID}\",\"zone_id\":\"ZONE-A\",\"quantity\":50}"
echo
docker start smart-warehouse-cassandra-2
sleep 25
printf 'FAILOVER_PRODUCT_ID=%s\n' "${PRODUCT_ID}" > "${STATE_FILE}"
echo "Saved failover scenario state to ${STATE_FILE}"
echo "Check cluster status:"
docker exec smart-warehouse-cassandra-1 nodetool status
echo "Check final inventory:"
demo_wait_for_cql_contains \
  "SELECT product_id, zone_id, available_quantity FROM warehouse.inventory_by_product_zone WHERE product_id='${PRODUCT_ID}' AND zone_id='ZONE-A';" \
  "${PRODUCT_ID}"
