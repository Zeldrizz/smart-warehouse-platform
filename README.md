# Smart Warehouse Platform

Standalone repository for the Smart Warehouse system with full CI, automated tests, load testing, Prometheus/Grafana monitoring, Alertmanager alerts, and system-level SLI/SLO gates.

## Stack

- `wms-service` - HTTP producer that validates requests and publishes warehouse events to Kafka
- `consumer-service` - Kafka consumer that projects warehouse state to Cassandra
- `Kafka` + `Schema Registry`
- `Cassandra` cluster with `3` nodes
- `Prometheus`
- `Grafana`
- `Alertmanager`
- `kafka-exporter`
- `cadvisor`
- `k6`

## Quick Start

Run everything from the repository root:

```bash
docker-compose down -v
docker-compose up -d --build
./scripts/wait_for_stack.sh
```

After startup:

- `wms-service`: `http://localhost:8001`
- `consumer-service`: `http://localhost:8002`
- `Prometheus`: `http://localhost:9090`
- `Alertmanager`: `http://localhost:9094`
- `Grafana`: `http://localhost:3000` (`admin/admin`)

## Operational Commands

All checks are automated and run without manual setup steps:

```bash
./scripts/run_unit_tests.sh
./scripts/run_integration_tests.sh
./scripts/run_e2e_tests.sh
./scripts/run_load_tests.sh
./scripts/run_prometheus_gates.sh
./scripts/demo_monitoring.sh
./scripts/collect_artifacts.sh artifacts/ci
```

## CI Pipeline

GitHub Actions workflow:

- `.github/workflows/smart-warehouse-ci.yml`

Pipeline stages:

1. `build-images`
2. `unit-tests`
3. `start-stack`
4. `integration-tests`
5. `e2e-tests`
6. `load-tests`
7. `prometheus-gates`
8. `artifacts`

In CI the synthetic generator in `wms-service` is disabled to keep latency and event-delay measurements deterministic. Locally the generator stays enabled by default for realistic live traffic.

## System-Level SLI, SLO and Failure Thresholds

The system uses real Prometheus queries, not hardcoded values. These SLI are checked by `scripts/check_prometheus_gates.py` and executed from `./scripts/run_prometheus_gates.sh`. If a failure threshold is crossed, the script exits with code `1` and CI fails.

| SLI | What is measured | PromQL | SLO target | Failure threshold | Why these thresholds |
| --- | --- | --- | --- | --- | --- |
| API availability | Share of successful `POST /api/v1/events` requests in WMS | `sum(rate(http_requests_total{service="wms-service",endpoint="/api/v1/events",status=~"2.."}[5m])) / clamp_min(sum(rate(http_requests_total{service="wms-service",endpoint="/api/v1/events"}[5m])), 0.0001)` | `>= 99.5%` | `< 95%` | WMS only validates and publishes to Kafka, so steady-state availability must be near-perfect. Below `95%` the API is effectively degraded for clients. |
| WMS publish latency p95 | End-to-end HTTP latency of `POST /api/v1/events` | `histogram_quantile(0.95, sum by(le) (rate(http_request_duration_seconds_bucket{service="wms-service",endpoint="/api/v1/events"}[5m])))` | `< 0.5s` | `> 1.0s` | The producer path is lightweight and asynchronous. `500ms` is a reasonable healthy target, while `1s` signals abnormal broker or application slowdown. |
| Event processing delay p95 | Delay from event `occurred_at` until terminal handling in `consumer-service` | `histogram_quantile(0.95, sum by(le) (rate(event_end_to_end_delay_seconds_bucket[5m])))` | `< 5s` | `> 10s` | This metric captures system-level async freshness. Short spikes are acceptable under load, but above `10s` the warehouse projections become too stale for operational use. |

How these SLI are used:

- in CI gates: `scripts/check_prometheus_gates.py`
- in operational wrapper: `scripts/run_prometheus_gates.sh`
- in monitoring: `prometheus/alert_rules.yml`
- in saved artifacts: `artifacts/prometheus/gates.json`

## Monitoring

Prometheus scrape targets are configured in `prometheus/prometheus.yml`:

- `wms-service`
- `consumer-service`
- `kafka-exporter`
- `cadvisor`

Grafana dashboards are provisioned from code:

- `grafana/dashboards/services_dashboard.json`
- `grafana/dashboards/infrastructure_dashboard.json`
- `grafana/provisioning/datasources/prometheus.yml`
- `grafana/provisioning/dashboards/dashboards.yml`

Alert rules are stored in:

- `prometheus/alert_rules.yml`

Alertmanager config:

- `alertmanager/alertmanager.yml`

## Artifacts

The project stores reproducible evidence for CI and local verification:

- `artifacts/unit/*.xml`
- `artifacts/tests/*.xml`
- `artifacts/load/k6-summary.json`
- `artifacts/prometheus/gates.json`
- `artifacts/prometheus/demo_monitoring/*.json`
- `artifacts/ci/docker-compose.log`
- `artifacts/ci/prometheus-alerts.json`
- `artifacts/ci/alertmanager-alerts.json`

## Detailed Report

The full requirement-by-requirement implementation report is in:

- `report/REPORT.md`
