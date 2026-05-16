#!/usr/bin/env bash
set -euo pipefail

if command -v docker-compose >/dev/null 2>&1; then
  COMPOSE=(docker-compose)
else
  COMPOSE=(docker compose)
fi

mkdir -p artifacts/load
chmod 0777 artifacts/load
"${COMPOSE[@]}" --profile load run --rm load-tests
