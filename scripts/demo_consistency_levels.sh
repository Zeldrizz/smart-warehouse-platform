#!/bin/bash
set -euo pipefail

STATE_FILE="${STATE_FILE:-/tmp/hw7-report-demo-state.env}"

if [[ -f "${STATE_FILE}" ]]; then
  source "${STATE_FILE}"
fi

PRODUCT_ID="${PRODUCT_ID:-${FAILOVER_PRODUCT_ID:-SKU-FAILOVER-DEMO}}"

run_query() {
  local level="$1"

  echo "Consistency level set to ${level}."
  set +e
  docker exec -i hw7-cassandra-1 cqlsh <<EOF
CONSISTENCY ${level};
SELECT product_id, total_available_quantity, total_reserved_quantity
FROM warehouse.inventory_totals_by_product
WHERE product_id = '${PRODUCT_ID}';
EOF
  local status=$?
  set -e

  echo "Exit code: ${status}"
  echo
}

docker stop hw7-cassandra-2 >/dev/null
sleep 10

run_query ONE
run_query QUORUM
run_query ALL

docker start hw7-cassandra-2 >/dev/null
sleep 25

echo "Cluster status after Cassandra node recovery:"
docker exec hw7-cassandra-1 nodetool status
