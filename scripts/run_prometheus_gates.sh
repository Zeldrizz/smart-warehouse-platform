#!/usr/bin/env bash
set -euo pipefail

mkdir -p artifacts/prometheus

wait_for_lag_drain() {
  local max_attempts="${1:-24}"
  local sleep_seconds="${2:-5}"
  local query='max(consumer_lag)'
  local previous_value=""

  for ((attempt=1; attempt<=max_attempts; attempt++)); do
    local response
    response="$(curl -fsS -G "http://localhost:9090/api/v1/query" --data-urlencode "query=${query}")"
    local value
    value="$(python3 -c 'import json,sys; data=json.load(sys.stdin); result=data.get("data", {}).get("result", []); print(result[0]["value"][1] if result else "0")' <<<"${response}")"
    echo "Prometheus consumer lag check ${attempt}/${max_attempts}: max_lag=${value}"
    previous_value="${value}"
    if python3 -c 'import sys; raise SystemExit(0 if float(sys.argv[1]) <= 0.0 else 1)' "${value}"; then
      return 0
    fi
    sleep "${sleep_seconds}"
  done

  echo "Consumer lag did not drain before Prometheus gate evaluation. Last observed max_lag=${previous_value}" >&2
  return 1
}

wait_for_lag_drain 24 5
sleep 10
python3 scripts/check_prometheus_gates.py \
  --prometheus-url "http://localhost:9090" \
  --alertmanager-url "http://localhost:9094" \
  --output-json "artifacts/prometheus/gates.json"
