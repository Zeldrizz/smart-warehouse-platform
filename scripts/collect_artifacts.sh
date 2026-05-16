#!/usr/bin/env bash
set -euo pipefail

if command -v docker-compose >/dev/null 2>&1; then
  COMPOSE=(docker-compose)
else
  COMPOSE=(docker compose)
fi

TARGET_DIR="${1:-artifacts/ci}"
mkdir -p "${TARGET_DIR}"

("${COMPOSE[@]}" ps || true) > "${TARGET_DIR}/docker-compose-ps.txt"
("${COMPOSE[@]}" logs --no-color || true) > "${TARGET_DIR}/docker-compose.log"
(curl -fsS "http://localhost:9090/api/v1/alerts" || true) > "${TARGET_DIR}/prometheus-alerts.json"
(curl -fsS "http://localhost:9094/api/v2/alerts" || true) > "${TARGET_DIR}/alertmanager-alerts.json"
