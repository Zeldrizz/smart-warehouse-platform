#!/usr/bin/env bash
set -euo pipefail

if command -v docker-compose >/dev/null 2>&1; then
  COMPOSE=(docker-compose)
else
  COMPOSE=(docker compose)
fi

"${COMPOSE[@]}" --profile tests run --rm tests pytest -v --tb=short -s integration
