# HW 7 Report - CI/CD, Testing & Observability for Smart Warehouse

## 1. Что реализовано

`smart-warehouse-platform` сделан как отдельный, самодостаточный репозиторий на базе решения из `hw_6`. Внутри него сохранена исходная бизнес-архитектура `wms-service + consumer-service + Kafka + Cassandra`, а поверх неё добавлены:

- единая HTTP Prometheus-инструментация для обоих сервисов;
- новый `GET /metrics` в `wms-service` и расширенные метрики в `consumer-service`;
- полный monitoring stack: `Prometheus + Grafana + Alertmanager + kafka-exporter + cadvisor`;
- unit, integration, e2e, load и SLI/SLO gate tests;
- GitHub Actions workflow в корне репозитория;
- скрипты для локального воспроизведения всего контура.

Ключевой результат: исходный `hw_6` не менялся, а standalone-репозиторий поднимается одной командой `docker compose up --build` / `docker-compose up --build`.

## 2. Как запускать и показывать решение

### 2.1 Старт стенда

```bash
# run from repository root
docker-compose down -v
docker-compose up -d --build
./scripts/wait_for_stack.sh
```

После этого доступны:

- WMS API: `http://localhost:8001`
- Consumer API: `http://localhost:8002`
- Prometheus: `http://localhost:9090`
- Alertmanager: `http://localhost:9094`
- Grafana: `http://localhost:3000` (`admin/admin`)

### 2.2 Операционные команды из контракта

```bash
# run from repository root
./scripts/run_unit_tests.sh
./scripts/run_integration_tests.sh
./scripts/run_e2e_tests.sh
./scripts/run_load_tests.sh
./scripts/run_prometheus_gates.sh
./scripts/demo_monitoring.sh
./scripts/collect_artifacts.sh artifacts/ci
```

### 2.3 Остановка стенда

```bash
# run from repository root
docker-compose down -v
```

## 3. Реализация по пунктам плана

### 3.1 Изоляция от `hw_6`

Изоляция сделана на уровне файлов, контейнеров, volumes и CI:

- отдельный standalone-репозиторий;
- все `container_name` и Docker volumes имеют префикс `hw7-`;
- monitoring, tests и artifacts живут только внутри этого проекта;
- GitHub Actions лежит в корне репозитория: `.github/workflows/hw7-ci.yml`.

Доказательства:

- `docker-compose.yml:1-423`
- `.github/workflows/hw7-ci.yml:1-105`

### 3.2 Общая HTTP-инструментация Prometheus

Вынесен общий модуль `common/observability.py`, который используется обоими сервисами. В нём объявлены и регистрируются:

- `http_requests_total{service,method,endpoint,status}`
- `http_request_errors_total{service,method,endpoint,error_type}`
- `http_request_duration_seconds_bucket{service,method,endpoint}`

Именно этот модуль ставит middleware и нормализует `endpoint`, `status` и `error_type`.

Доказательства:

- объявления метрик: `common/observability.py:16-33`
- middleware: `common/observability.py:76-120`
- unit test на `status` и `error_type`: `wms_service/tests/unit/test_http_metrics.py:11-44`

### 3.3 Новый `/metrics` у `wms-service` и расширение `/metrics` у `consumer-service`

В `wms-service` добавлен новый системный роутер с `GET /metrics`. В `consumer-service` endpoint уже существовал как operational surface, но теперь он отдает и общие HTTP-метрики, и бизнес/SLI-метрики.

Доказательства:

- подключение middleware в WMS: `wms_service/app/main.py:35-43`
- `GET /metrics` в WMS: `wms_service/app/api/routes.py:78-81`
- подключение middleware в consumer: `consumer_service/app/main.py:35-42`
- переиспользование общего observability-модуля в образах:
  - `wms_service/Dockerfile:12-14`
  - `consumer_service/Dockerfile:12-14`

### 3.4 Метрика `event_end_to_end_delay_seconds`

В `consumer-service` оставлены бизнес-метрики и добавлена системная histogram-метрика `event_end_to_end_delay_seconds{event_type}`. Она измеряет разницу между `occurred_at` события и моментом terminal handling после `commit`.

Доказательства:

- объявление histogram: `common/observability.py:53-58`
- запись значения после обработки события: `consumer_service/app/application/consumer_worker.py:137-142`

### 3.5 Monitoring stack: Prometheus, Grafana, Alertmanager, infra exporters

В `docker-compose.yml` добавлены:

- `kafka-exporter`
- `cadvisor`
- `alertmanager`
- `prometheus`
- `grafana`

Prometheus скрейпит оба приложения, `kafka-exporter` и `cadvisor`.

Доказательства:

- monitoring services: `docker-compose.yml:276-411`
- scrape config: `prometheus/prometheus.yml:1-37`
- Alertmanager wiring: `prometheus/prometheus.yml:8-13`
- minimal Alertmanager config: `alertmanager/alertmanager.yml:1-12`

### 3.6 Dashboards и alert rules

В Grafana добавлены два dashboard JSON:

- `grafana/dashboards/services_dashboard.json`
- `grafana/dashboards/infrastructure_dashboard.json`

Они покрывают:

- latency `p50/p95/p99`
- error rate
- throughput
- `event_end_to_end_delay`
- consumer lag
- Kafka/topic health
- CPU/memory контейнеров Kafka и Cassandra через `cadvisor`

Alert rules лежат в репозитории и подключены через Prometheus:

- `HighHttpErrorRate`
- `HighHttpLatencyP95`
- `ServiceDown`
- `ConsumerLagHigh`
- дополнительно `EventProcessingDelayHigh`

Доказательства:

- `prometheus/alert_rules.yml:1-49`
- demo фиксации firing alerts: `scripts/demo_monitoring.sh:32-102`

### 3.7 Тестовый контур

Тесты разделены на слои ровно по заданию.

#### Unit tests

- WMS mapping request -> envelope:
  - `wms_service/tests/unit/test_event_publisher.py:21-67`
- Consumer domain processing:
  - duplicate: `consumer_service/tests/unit/test_event_processor.py:71-88`
  - stale: `consumer_service/tests/unit/test_event_processor.py:90-116`
  - `ORDER_CREATED`: `consumer_service/tests/unit/test_event_processor.py:118-142`
  - `ORDER_COMPLETED`: `consumer_service/tests/unit/test_event_processor.py:144-179`
- HTTP metrics middleware:
  - `wms_service/tests/unit/test_http_metrics.py:11-44`

#### Integration tests

Integration tests идут на реальном compose-стеке:

- WMS API -> Kafka -> Consumer -> Cassandra:
  - `tests/integration/test_service_interactions.py:48-64`
- DLQ path:
  - `tests/integration/test_service_interactions.py:66-107`
- `/metrics` и Prometheus scrape:
  - `tests/integration/test_service_interactions.py:108-132`

Тестовые фикстуры и изоляция:

- `tests/conftest.py:17-97`

#### E2E test

Полный пользовательский сценарий склада:

- `receive -> reserve -> move -> order create -> order complete`
- проверки HTTP response, Cassandra projections и order state

Доказательство:

- `tests/e2e/test_full_flow.py:46-123`

#### Load test

K6 сценарий соответствует требованиям:

- `10` VU
- `30s`
- нагрузка на `POST /api/v1/events`
- уникальные `event_id`
- поток `PRODUCT_RECEIVED / PRODUCT_RESERVED / PRODUCT_MOVED`
- thresholds:
  - `http_req_failed < 1%`
  - `p95(http_req_duration) < 500ms`

Доказательства:

- `scripts/load/wms_events.js:4-87`
- launcher: `scripts/run_load_tests.sh:1-12`

### 3.8 SLI/SLO gates по Prometheus API

Отдельный gate script опрашивает Prometheus API и валидирует SLI/SLO пороги:

- availability `>= 99.5%`
- WMS HTTP p95 latency `< 500ms`
- event end-to-end p95 `< 5s`

Доказательства:

- PromQL и пороги: `scripts/check_prometheus_gates.py:15-37`
- сохранение evidence JSON: `scripts/check_prometheus_gates.py:96-135`
- launcher: `scripts/run_prometheus_gates.sh:1-9`

### 3.9 CI/CD workflow

Workflow лежит в корне репозитория, как и требовалось:

- `.github/workflows/hw7-ci.yml`

Он запускается на `push`, `pull_request`, `workflow_dispatch`, исполняется из корня standalone-репозитория и собран в последовательные стадии:

1. `build-images`
2. `unit-tests`
3. `start-stack`
4. `integration-tests`
5. `e2e-tests`
6. `load-tests`
7. `prometheus-gates`
8. `artifacts`

Практически это сделано как отдельные jobs для `build-images` и `unit-tests`, а стадии `start-stack` -> `artifacts` оформлены как последовательные steps одного job `start-stack`. Это сознательно: GitHub runner между jobs не делит один и тот же Docker stack, поэтому stack-dependent stages должны жить в одном job, если требуется повторно использовать поднятую инфраструктуру.

Доказательства:

- `.github/workflows/hw7-ci.yml:1-105`

## 4. Таблица соответствия требованиям

| Требование | Где реализовано |
| --- | --- |
| Самодостаточный standalone-репозиторий | `docker-compose.yml:1-423` |
| `/metrics` в `wms-service` | `wms_service/app/api/routes.py:78-81` |
| Общий HTTP middleware для обоих сервисов | `common/observability.py:76-120`, `wms_service/app/main.py:35-43`, `consumer_service/app/main.py:35-42` |
| `event_end_to_end_delay_seconds` | `common/observability.py:53-58`, `consumer_service/app/application/consumer_worker.py:137-142` |
| Prometheus + Alertmanager + Grafana + infra metrics | `docker-compose.yml:276-411`, `prometheus/prometheus.yml:1-37`, `alertmanager/alertmanager.yml:1-12` |
| Alert rules | `prometheus/alert_rules.yml:1-49` |
| Unit / integration / e2e / load tests | `wms_service/tests/unit`, `consumer_service/tests/unit`, `tests/integration`, `tests/e2e`, `scripts/load/wms_events.js` |
| Prometheus gates | `scripts/check_prometheus_gates.py:15-135` |
| GitHub Actions workflow | `.github/workflows/hw7-ci.yml:1-105` |

## 5. SLI/SLO и локально зафиксированные значения

Локальная проверка проведена 2026-05-16.

Данные взяты из `artifacts/prometheus/gates.json`.

| SLI | PromQL | Target | Local value |
| --- | --- | --- | --- |
| API availability | `sum(rate(http_requests_total{service="wms-service",endpoint="/api/v1/events",status=~"2.."}[5m])) / clamp_min(sum(rate(http_requests_total{service="wms-service",endpoint="/api/v1/events"}[5m])), 0.0001)` | `>= 0.995` | `1.000000` |
| WMS p95 latency | `histogram_quantile(0.95, sum by(le) (rate(http_request_duration_seconds_bucket{service="wms-service",endpoint="/api/v1/events"}[5m])))` | `< 0.5s` | `0.004786s` |
| End-to-end delay p95 | `histogram_quantile(0.95, sum by(le) (rate(event_end_to_end_delay_seconds_bucket[5m])))` | `< 5s` | `0.190562s` |

Все три gate-проверки локально прошли.

## 6. Локальная верификация

Ниже перечислено, что было реально прогнано локально.

### 6.1 Unit tests

Команда:

```bash
# run from repository root
./scripts/run_unit_tests.sh
```

Результат: `7 passed`.

### 6.2 Integration tests

Команда:

```bash
# run from repository root
./scripts/run_integration_tests.sh
```

Результат: `3 passed`.

### 6.3 E2E test

Команда:

```bash
# run from repository root
./scripts/run_e2e_tests.sh
```

Результат: `1 passed`.

### 6.4 Load test

Команда:

```bash
# run from repository root
./scripts/run_load_tests.sh
```

Фактический сценарий:

- publish workload: `10 VU`, `30s`
- health workload: `1 VU`, `30s`

В `artifacts/load/k6-summary.json` зафиксированы:

- `1476` успешных publish checks;
- `30` успешных health checks;
- `http_req_duration p95 = 5.33632725 ms`.

### 6.5 Monitoring / alerts demo

Команда:

```bash
# run from repository root
./scripts/demo_monitoring.sh
```

Скрипт демонстрирует два firing сценария:

- `ConsumerLagHigh`
- `ServiceDown`

И сохраняет snapshots в:

- `artifacts/prometheus/demo_monitoring/consumer-lag-high-prometheus.json`
- `artifacts/prometheus/demo_monitoring/consumer-lag-high-alertmanager.json`
- `artifacts/prometheus/demo_monitoring/service-down-prometheus.json`
- `artifacts/prometheus/demo_monitoring/service-down-alertmanager.json`

## 7. Артефакты

После прогона `./scripts/collect_artifacts.sh artifacts/ci` собираются:

- `artifacts/ci/docker-compose-ps.txt`
- `artifacts/ci/docker-compose.log`
- `artifacts/ci/prometheus-alerts.json`
- `artifacts/ci/alertmanager-alerts.json`
- `artifacts/load/k6-summary.json`
- `artifacts/prometheus/gates.json`
- `artifacts/prometheus/demo_monitoring/*.json`

Логика сборки артефактов:

- `scripts/collect_artifacts.sh:1-16`

## 8. Итог

План для HW 7 реализован:

- standalone-репозиторий изолирован от `hw_6`;
- observability добавлена без изменения бизнес-API, кроме нового `GET /metrics` у WMS;
- monitoring stack и alerting подняты в compose;
- тестовый контур покрывает unit, integration, e2e, load и Prometheus gates;
- CI workflow оформлен в корне репозитория и исполняет стадии из задания;
- локальная верификация пройдена, evidence сохранены в `artifacts`.
