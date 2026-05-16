# Smart Warehouse Platform

Standalone CI/CD, testing, and observability project for the Smart Warehouse system.

## Stack

- `wms-service`
- `consumer-service`
- `Kafka`
- `Cassandra`
- `Prometheus`
- `Grafana`
- `Alertmanager`

## Quick Start

```bash
docker-compose up -d --build
./scripts/wait_for_stack.sh
```

## Test Commands

```bash
./scripts/run_unit_tests.sh
./scripts/run_integration_tests.sh
./scripts/run_e2e_tests.sh
./scripts/run_load_tests.sh
./scripts/run_prometheus_gates.sh
```

## CI

GitHub Actions workflow:

- `.github/workflows/hw7-ci.yml`

## Documentation

Detailed implementation report:

- `report/REPORT.md`
