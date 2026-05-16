#!/bin/bash
set -euo pipefail

WMS_CONTROL_URL="${WMS_CONTROL_URL:-http://localhost:8001/api/v1/generator}"
CONSUMER_METRICS_URL="${CONSUMER_METRICS_URL:-http://localhost:8002/metrics}"
DEMO_LAG_THRESHOLD="${DEMO_LAG_THRESHOLD:-25}"
DEMO_LAG_WAIT_SECONDS="${DEMO_LAG_WAIT_SECONDS:-120}"
DEMO_CQL_WAIT_SECONDS="${DEMO_CQL_WAIT_SECONDS:-90}"
DEMO_GENERATOR_RESUME_ON_EXIT="${DEMO_GENERATOR_RESUME_ON_EXIT:-1}"

_demo_generator_was_paused=0

demo_pause_generator() {
  local response
  response="$(curl -sS -X POST "${WMS_CONTROL_URL}/pause" || true)"
  if [[ -n "${response}" ]] && grep -q '"paused":true' <<<"${response}"; then
    _demo_generator_was_paused=1
  fi
}

demo_resume_generator() {
  if [[ "${DEMO_GENERATOR_RESUME_ON_EXIT}" != "1" ]]; then
    return
  fi
  if [[ "${_demo_generator_was_paused}" == "1" ]]; then
    curl -sS -X POST "${WMS_CONTROL_URL}/resume" >/dev/null || true
  fi
}

demo_max_lag() {
  curl -sS "${CONSUMER_METRICS_URL}" | awk '
    /^consumer_lag\{/ {
      value = $2 + 0
      if (value > max) {
        max = value
      }
    }
    END { print max + 0 }
  '
}

demo_wait_for_low_lag() {
  local elapsed=0
  while (( elapsed < DEMO_LAG_WAIT_SECONDS )); do
    local lag
    lag="$(demo_max_lag)"
    if awk "BEGIN { exit !(${lag} <= ${DEMO_LAG_THRESHOLD}) }"; then
      return 0
    fi
    sleep 3
    elapsed=$((elapsed + 3))
  done
  echo "consumer_lag is still above ${DEMO_LAG_THRESHOLD}; refusing to run a manual E2E scenario on a stale backlog." >&2
  return 1
}

demo_prepare_manual_window() {
  demo_pause_generator
  demo_wait_for_low_lag
}

demo_wait_for_cql_contains() {
  local query="$1"
  local expected="$2"
  local elapsed=0
  local output=""

  while (( elapsed < DEMO_CQL_WAIT_SECONDS )); do
    output="$(docker exec smart-warehouse-cassandra-1 cqlsh -e "${query}" || true)"
    if grep -q "${expected}" <<<"${output}"; then
      printf '%s\n' "${output}"
      return 0
    fi
    sleep 2
    elapsed=$((elapsed + 2))
  done

  echo "Expected Cassandra output to contain: ${expected}" >&2
  echo "Last query output:" >&2
  printf '%s\n' "${output}" >&2
  return 1
}
