#!/usr/bin/env bash
set -euo pipefail

wait_for() {
  local url="$1"
  local attempts="${2:-90}"
  local delay="${3:-2}"

  for ((i=1; i<=attempts; i++)); do
    if curl -fsS "${url}" >/dev/null 2>&1; then
      echo "Ready: ${url}"
      return 0
    fi
    sleep "${delay}"
  done

  echo "Timed out waiting for ${url}" >&2
  return 1
}

wait_for "http://localhost:8001/api/v1/health"
wait_for "http://localhost:8002/health"
wait_for "http://localhost:8001/metrics"
wait_for "http://localhost:8002/metrics"
wait_for "http://localhost:8081/subjects"
wait_for "http://localhost:9090/-/healthy"
wait_for "http://localhost:9094/-/healthy"
wait_for "http://localhost:3000/api/health"

curl -fsS "http://localhost:9090/api/v1/query?query=up" >/dev/null
