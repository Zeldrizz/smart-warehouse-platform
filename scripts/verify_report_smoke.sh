#!/bin/bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
LOG_DIR="${ROOT_DIR}/report"
LOG_FILE="${LOG_DIR}/smoke_check_latest.log"
RUN_TESTS="${RUN_TESTS:-0}"

mkdir -p "${LOG_DIR}"

exec > >(tee "${LOG_FILE}") 2>&1

step() {
  echo
  echo "================================================================"
  echo "$1"
  echo "================================================================"
}

run() {
  echo
  echo "+ $*"
  "$@"
}

cd "${ROOT_DIR}"

step "HW6 smoke verification"
echo "Log file: ${LOG_FILE}"
echo "Started at: $(date -u '+%Y-%m-%dT%H:%M:%SZ')"

step "Stack status"
run docker-compose ps

step "Health endpoints"
run curl -fsS http://localhost:8001/api/v1/health
run curl -fsS http://localhost:8002/health
run curl -fsS http://localhost:3000/api/health
run curl -fsS http://localhost:8081/subjects

step "Synthetic traffic"
run ./scripts/demo_synthetic_traffic.sh

step "Scenario 1: base flow"
run ./scripts/demo_base_flow.sh

step "Scenario 2: idempotency"
run ./scripts/demo_idempotency.sh

step "Scenario 3: projection consistency"
run ./scripts/demo_projection_consistency.sh

step "Scenario 4: out-of-order"
run ./scripts/demo_out_of_order.sh

step "Scenario 5: DLQ"
run ./scripts/demo_dlq.sh

step "Scenario 6: Cassandra failover"
run ./scripts/demo_cassandra_failover.sh

step "Scenario 6b: consistency levels"
run ./scripts/demo_consistency_levels.sh

step "Scenario 7: monitoring"
run ./scripts/demo_monitoring.sh

step "Scenario 8: schema evolution"
run ./scripts/demo_schema_evolution.sh

if [[ "${RUN_TESTS}" == "1" ]]; then
  step "Integration tests"
  run docker-compose --profile tests up --build tests
fi

step "Smoke verification complete"
echo "Finished at: $(date -u '+%Y-%m-%dT%H:%M:%SZ')"
echo "Review the commands and outputs in ${LOG_FILE}"
