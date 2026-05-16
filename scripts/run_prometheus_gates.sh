#!/usr/bin/env bash
set -euo pipefail

mkdir -p artifacts/prometheus
sleep 10
python3 scripts/check_prometheus_gates.py \
  --prometheus-url "http://localhost:9090" \
  --alertmanager-url "http://localhost:9094" \
  --output-json "artifacts/prometheus/gates.json"
