#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "${ROOT_DIR}"

PYTHONPATH="${ROOT_DIR}:${ROOT_DIR}/wms_service" pytest -v --tb=short wms_service/tests/unit
PYTHONPATH="${ROOT_DIR}:${ROOT_DIR}/consumer_service" pytest -v --tb=short consumer_service/tests/unit
