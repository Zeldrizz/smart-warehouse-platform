# Детальный отчёт по выполнению ДЗ №7 — CI/CD, Testing & Observability

Этот отчёт сделан в том же доказательном формате, что и отчёт из `hw_6`:

1. в начале есть готовый сценарий защиты;
2. дальше по каждому требованию из `hw_7_TASK.md` приведена исходная формулировка, объяснение реализации, аргументация, почему пункт считается выполненным, и ссылки на код;
3. в конце приведена фактическая локальная проверка текущего standalone-репозитория `smart-warehouse-platform`.

---

## 0. Как показывать решение на защите

### 0.1 Чистый старт стенда

Все команды выполнять из корня standalone-репозитория:

```bash
docker-compose down -v
docker-compose up -d --build
./scripts/wait_for_stack.sh
docker-compose ps
```

После этого должны быть доступны:

- `wms-service`: `http://localhost:8001`
- `consumer-service`: `http://localhost:8002`
- `Prometheus`: `http://localhost:9090`
- `Alertmanager`: `http://localhost:9094`
- `Grafana`: `http://localhost:3000`

Что показать ассистенту:

- `docker-compose ps` - все long-running контейнеры в `Up`, init/migrator контейнеры завершились `Exit 0`;
- `curl http://localhost:8001/api/v1/health`
- `curl http://localhost:8002/health`
- `curl http://localhost:8001/metrics | head`
- `curl http://localhost:8002/metrics | head`
- `docker exec hw7-cassandra-1 nodetool status`
- `docker exec hw7-kafka-1 kafka-topics --describe --topic warehouse-events --bootstrap-server kafka-1:29092`

Где обеспечивается готовность стенда:

- `scripts/wait_for_stack.sh:1-30`
- `docker-compose.yml:1-423`

### 0.2 Показ CI pipeline

В GitHub открыть workflow:

- `.github/workflows/hw7-ci.yml`

Показать:

1. что workflow запускается на `push`, `pull_request`, `workflow_dispatch`;
2. что есть стадии `build-images -> unit-tests -> start-stack`;
3. что внутри `start-stack` последовательно выполняются `integration`, `e2e`, `load`, `prometheus gates`, `artifact collection`;
4. что при ошибке любой stage job падает;
5. что артефакты доступны из UI.

Где смотреть:

- `.github/workflows/hw7-ci.yml:1-95`

### 0.3 Показ Grafana, Prometheus и Alertmanager

Показать в браузере:

- `Prometheus` targets и alerts;
- `Grafana` dashboards:
  - `HW7 Services Observability`
  - `HW7 Infrastructure Observability`
- `Alertmanager` UI.

Где смотреть код:

- `prometheus/prometheus.yml:1-37`
- `prometheus/alert_rules.yml:1-49`
- `grafana/dashboards/services_dashboard.json:1-128`
- `grafana/dashboards/infrastructure_dashboard.json:1-75`
- `grafana/provisioning/datasources/prometheus.yml:1-10`
- `grafana/provisioning/dashboards/dashboards.yml:1-11`
- `alertmanager/alertmanager.yml:1-12`

### 0.4 Показ тестов и нагрузочного сценария

Показать, что все проверки запускаются одной командой:

```bash
./scripts/run_integration_tests.sh
./scripts/run_e2e_tests.sh
./scripts/run_load_tests.sh
./scripts/run_prometheus_gates.sh
```

Дополнительно показать алерты:

```bash
./scripts/demo_monitoring.sh
```

Где смотреть:

- `scripts/run_integration_tests.sh:1-10`
- `scripts/run_e2e_tests.sh:1-10`
- `scripts/run_load_tests.sh:1-12`
- `scripts/run_prometheus_gates.sh:1-34`
- `scripts/demo_monitoring.sh:1-102`

### 0.5 Сбор артефактов и остановка стенда

```bash
./scripts/collect_artifacts.sh artifacts/ci
docker-compose down -v
```

Где смотреть:

- `scripts/collect_artifacts.sh:1-16`

---

## 1. Общие требования

### 1.1 «Все сервисы и инфраструктура поднимаются одной командой docker-compose up.»

**Что сделано.** Весь стенд описан в одном `docker-compose.yml`: сервисы приложения, Kafka, Schema Registry, Cassandra cluster, Prometheus, Grafana, Alertmanager, `kafka-exporter`, `cadvisor`, а также контейнеры `kafka-init`, `cassandra-migrator`, `tests`, `load-tests`.

**Почему это выполняет требование.** Студенту не нужно вручную запускать отдельные зависимости. Достаточно `docker-compose up -d --build`, после чего всё окружение поднимается как единый reproducible stack.

**Где смотреть.**

- `docker-compose.yml:1-423`
- `scripts/wait_for_stack.sh:21-30`

### 1.2 «CI pipeline запускается автоматически при push или PR.»

**Что сделано.** GitHub Actions workflow объявлен в корне репозитория и запускается на `push`, `pull_request`, `workflow_dispatch`.

**Почему это выполняет требование.** Автоматический старт на `push/PR` закрывает обязательную часть ТЗ. `workflow_dispatch` добавлен как удобный ручной запуск для защиты и повторных прогонов.

**Где смотреть.**

- `.github/workflows/hw7-ci.yml:1-10`

### 1.3 «Пайплайн падает при любой ошибке (build, tests, metrics validation).»

**Что сделано.** В workflow нет подавления ошибок на критических стадиях. Ошибка в build, unit, integration, e2e, load или Prometheus gates завершает step/job ненулевым exit code.

**Почему это выполняет требование.** В pipeline нет “мягких” pass-through стадий для ключевых проверок. Единственное, что выполняется через `if: always()`, это сбор артефактов и teardown, чтобы не потерять диагностику после падения.

**Где смотреть.**

- `.github/workflows/hw7-ci.yml:18-20`
- `.github/workflows/hw7-ci.yml:36-43`
- `.github/workflows/hw7-ci.yml:64-80`
- `scripts/check_prometheus_gates.py:105-154`

### 1.4 «Метрики экспортируются в Prometheus-совместимом формате.»

**Что сделано.** Оба сервиса отдают `/metrics` через `prometheus_client.generate_latest()` с корректным content type.

**Почему это выполняет требование.** Это именно Prometheus scrape endpoint, а не кастомный JSON.

**Где смотреть.**

- `common/observability.py:72-73`
- `wms_service/app/api/routes.py:78-81`
- `consumer_service/app/api/routes.py:40-43`

### 1.5 «Тесты воспроизводимы и автоматизированы (без ручных действий).»

**Что сделано.** Для каждого слоя есть отдельный запускной script, который поднимает нужную среду или использует уже поднятый compose stack. Интеграционные и E2E проверки гоняются в Docker-профиле `tests`, нагрузка - в профиле `load`.

**Почему это выполняет требование.** Тесты стартуют командами, не требуют ручной подготовки данных, и возвращают exit code процесса.

**Где смотреть.**

- `scripts/run_unit_tests.sh:1-8`
- `scripts/run_integration_tests.sh:1-10`
- `scripts/run_e2e_tests.sh:1-10`
- `scripts/run_load_tests.sh:1-12`
- `tests/conftest.py:48-97`

### 1.6 «Вы используете свои сервисы из предыдущего ДЗ (не нужно создавать новые с нуля).»

**Что сделано.** Бизнес-архитектура сохранена: `wms-service + consumer-service + Kafka + Cassandra`. Новое ДЗ реализовано как standalone-репозиторий на базе предыдущего решения, а не как новая искусственная система.

**Почему это выполняет требование.** Предметная область, event flow, Cassandra projections, Kafka topics, DLQ, schema evolution и consumer processing унаследованы из `hw_6`; поверх них добавлены CI, tests, observability и SLI/SLO.

**Где смотреть.**

- `wms_service/app/application/event_service.py:22-93`
- `consumer_service/app/application/processor.py:26-410`
- `consumer_service/app/infrastructure/cassandra_repository.py:24-312`

---

## 2. Пункты на 1–4 балла

### 2.1 Пункт 1. CI pipeline

**Оригинальная формулировка.** «Необходимо настроить CI pipeline, который автоматически запускается при push или PR.»

**Что сделано.** В корне standalone-репозитория лежит GitHub Actions workflow `.github/workflows/hw7-ci.yml`. Он запускается автоматически на `push` и `pull_request`, а также вручную на `workflow_dispatch`.

**Где смотреть.**

- `.github/workflows/hw7-ci.yml:1-10`

**Подпункт.** «В пайплайне есть шаги: build — сборка всех ваших сервисов.»

**Что сделано.** Отдельный job `build-images` выполняет `docker compose build` по всему стеку.

**Где смотреть.**

- `.github/workflows/hw7-ci.yml:12-20`

**Подпункт.** «unit tests — модульные тесты для каждого сервиса.»

**Что сделано.** Job `unit-tests` ставит зависимости и отдельно запускает unit tests для `wms-service` и `consumer-service`.

**Где смотреть.**

- `.github/workflows/hw7-ci.yml:21-50`
- `wms_service/tests/unit/test_event_publisher.py:1-67`
- `wms_service/tests/unit/test_http_metrics.py:1-44`
- `consumer_service/tests/unit/test_event_processor.py:1-179`

**Подпункт.** «integration tests — интеграционные тесты (см. п.2).»

**Что сделано.** В job `start-stack` после старта окружения запускается `docker compose --profile tests run --rm tests pytest ... integration`.

**Где смотреть.**

- `.github/workflows/hw7-ci.yml:64-72`
- `scripts/run_integration_tests.sh:1-10`

**Подпункт.** «Пайплайн падает при любой ошибке.»

**Что сделано.** Любой failing step останавливает job. `if: always()` используется только для артефактов и teardown.

**Где смотреть.**

- `.github/workflows/hw7-ci.yml:79-95`

**Подпункт.** «Конфигурация CI хранится в репозитории.»

**Что сделано.** Конфигурация workflow закоммичена в репозиторий.

**Где смотреть.**

- `.github/workflows/hw7-ci.yml:1-95`

**Подпункт.** «Логи пайплайна доступны и читаемы.»

**Что сделано.** GitHub Actions логирует каждый step отдельно, а в артефакты дополнительно сохраняются `docker-compose.log`, junit XML, k6 summary и ответы Prometheus/Alertmanager.

**Где смотреть.**

- `.github/workflows/hw7-ci.yml:82-91`
- `scripts/collect_artifacts.sh:10-16`

### 2.2 Пункт 2. Интеграционные тесты сервисов

**Оригинальная формулировка.** «Необходимо реализовать интеграционные тесты, которые проверяют взаимодействие между вашими сервисами.»

**Что сделано.** Интеграционные тесты живут в `tests/integration` и гоняются против реального compose-стека в контейнере `tests`.

**Где смотреть.**

- `tests/integration/test_service_interactions.py:1-138`
- `tests/Dockerfile:1-10`

**Подпункт.** «Тесты поднимают зависимости (Docker / Testcontainers).»

**Что сделано.** Зависимости поднимает `docker-compose`; сами тесты выполняются внутри профиля `tests`.

**Где смотреть.**

- `scripts/run_integration_tests.sh:1-10`
- `docker-compose.yml:373-398`

**Подпункт.** «Проверяют взаимодействие между сервисами, а не один сервис в изоляции.»

**Что сделано.**

- `test_wms_event_flows_through_consumer_to_cassandra` проверяет цепочку `WMS API -> Kafka -> Consumer -> Cassandra`;
- `test_invalid_event_goes_to_dlq_and_consumer_keeps_processing` проверяет DLQ и то, что consumer продолжает обрабатывать следующие события;
- `test_services_expose_prometheus_metrics_and_prometheus_scrapes_them` проверяет оба `/metrics` и факт scrape через Prometheus.

**Где смотреть.**

- `tests/integration/test_service_interactions.py:48-64`
- `tests/integration/test_service_interactions.py:66-107`
- `tests/integration/test_service_interactions.py:108-132`

**Подпункт.** «Тесты изолированы (не зависят от порядка выполнения других тестов).»

**Что сделано.** Перед каждым тестом Cassandra-таблицы очищаются через fixture `clean_warehouse_tables`, а сущности получают уникальные suffix.

**Где смотреть.**

- `tests/conftest.py:68-85`
- `tests/conftest.py:68-70`

**Подпункт.** «Тесты очищают состояние после выполнения.»

**Что сделано.** Состояние очищается `TRUNCATE` по всем проекциям, orders, processed events и history.

**Где смотреть.**

- `tests/conftest.py:73-85`

**Подпункт.** «Тесты запускаются одной командой и возвращают exit code 0 при успехе, 1 при ошибке.»

**Что сделано.** Для интеграционных тестов есть отдельная команда `./scripts/run_integration_tests.sh`.

**Где смотреть.**

- `scripts/run_integration_tests.sh:1-10`

### 2.3 Пункт 3. End-to-End тест системы

**Оригинальная формулировка.** «Необходимо реализовать E2E тест, который проверяет полный пользовательский сценарий вашей системы.»

**Что сделано.** Есть отдельный E2E test `tests/e2e/test_full_flow.py`, который прогоняет полный складской сценарий через публичный HTTP API WMS.

**Где смотреть.**

- `tests/e2e/test_full_flow.py:46-123`

**Подпункт.** «Тест запускает реальный пользовательский сценарий через ваш API.»

**Что сделано.** Тест делает последовательные `POST /api/v1/events` для:

- `PRODUCT_RECEIVED`
- `PRODUCT_RESERVED`
- `PRODUCT_MOVED`
- `ORDER_CREATED`
- `ORDER_COMPLETED`

**Где смотреть.**

- `tests/e2e/test_full_flow.py:52-99`

**Подпункт.** «Проверяет результат в конечном хранилище (ваша БД).»

**Что сделано.** После каждого шага тест читает Cassandra projections, а в конце проверяет totals и order state.

**Где смотреть.**

- `tests/e2e/test_full_flow.py:60`
- `tests/e2e/test_full_flow.py:70`
- `tests/e2e/test_full_flow.py:81-82`
- `tests/e2e/test_full_flow.py:91`
- `tests/e2e/test_full_flow.py:99`
- `tests/e2e/test_full_flow.py:101-117`

**Подпункт.** «Тест покрывает минимум один полный сценарий из предметной области вашей системы.»

**Что сделано.** Сценарий буквально моделирует полный складской поток: приход товара, резервирование, перемещение, создание и завершение заказа.

**Где смотреть.**

- `tests/e2e/test_full_flow.py:47-117`

**Подпункт.** «Тест проверяет сквозную логику, а не отдельные сервисы.»

**Что сделано.** Проверяется не отдельный handler, а вся цепочка `HTTP -> Kafka -> consumer -> Cassandra`.

**Где смотреть.**

- `wms_service/app/api/routes.py:33-40`
- `wms_service/app/application/event_service.py:26-43`
- `consumer_service/app/application/consumer_worker.py:103-161`
- `consumer_service/app/infrastructure/cassandra_repository.py:214-305`

**Подпункты к проверкам.** «Проверка HTTP/gRPC статусов. Проверка тела ответа. Проверка состояния в БД.»

**Что сделано.**

- HTTP status `202` проверяется на каждом запросе;
- тело ответа проверяется по полям `event_id` и `status=accepted`;
- Cassandra состояние проверяется по inventory projections, totals и order status.

**Где смотреть.**

- `tests/e2e/test_full_flow.py:27-33`
- `tests/e2e/test_full_flow.py:101-117`

### 2.4 Пункт 4. Prometheus + базовые метрики сервисов

**Оригинальная формулировка.** «Каждый ваш сервис должен экспортировать метрики в Prometheus.»

**Что сделано.** Общая Prometheus-инструментация вынесена в `common/observability.py` и подключена в оба сервиса через единый middleware.

**Где смотреть.**

- `common/observability.py:16-33`
- `common/observability.py:76-120`
- `wms_service/app/main.py:35-43`
- `consumer_service/app/main.py:35-42`

**Подпункт.** «Каждый сервис экспортирует метрики по endpoint /metrics.»

**Что сделано.**

- WMS: отдельный `GET /metrics`;
- Consumer: отдельный `GET /metrics`.

**Где смотреть.**

- `wms_service/app/api/routes.py:78-81`
- `consumer_service/app/api/routes.py:40-43`

**Подпункт.** «Минимум метрик на каждый сервис: http_requests_total, http_request_errors_total, http_request_duration_seconds.»

**Что сделано.** Эти три метрики объявлены централизованно и автоматически записываются middleware с нужными labels.

**Где смотреть.**

- `common/observability.py:16-33`
- `common/observability.py:76-120`

**Подпункт.** «Prometheus реально собирает метрики (настроен scrape_config).»

**Что сделано.** `prometheus.yml` содержит scrape job для обоих приложений.

**Где смотреть.**

- `prometheus/prometheus.yml:14-25`
- `tests/integration/test_service_interactions.py:122-132`

**Подпункт.** «Prometheus поднимается в docker-compose.»

**Что сделано.** В compose есть отдельный сервис `prometheus`.

**Где смотреть.**

- `docker-compose.yml:324-350`

**Подпункт.** «Студент самостоятельно выбирает клиентскую библиотеку Prometheus ... и проектирует middleware/interceptor.»

**Что сделано.** Используется `prometheus_client`, а middleware написан вручную и нормализует `endpoint`, `status`, `error_type`.

**Где смотреть.**

- `common/observability.py:8-10`
- `common/observability.py:76-120`
- `wms_service/tests/unit/test_http_metrics.py:11-44`

---

## 3. Пункты на 5–7 баллов

### 3.1 Пункт 5. Grafana: дашборды сервисов

**Оригинальная формулировка.** «Необходимо создать дашборды в Grafana для визуализации метрик ваших сервисов.»

**Что сделано.** Создан сервисный дашборд `HW7 Services Observability`.

**Где смотреть.**

- `grafana/dashboards/services_dashboard.json:1-128`

**Подпункт.** «Отдельный дашборд (или секции) для каждого вашего сервиса.»

**Что сделано.** Один dashboard содержит отдельные панели для producer (`wms-service`) и consumer (`consumer-service`).

**Где смотреть.**

- `grafana/dashboards/services_dashboard.json:13-121`

**Подпункт.** «Видны метрики: latency — p50, p95, p99; errors; throughput.»

**Что сделано.**

- `WMS Latency Percentiles`
- `WMS Error Rate`
- `WMS Throughput`
- `Consumer HTTP Error Rate`
- `Consumer Event Throughput`
- дополнительно `Consumer Processing Latency p95`, `Event End-to-End Delay p95`, `Consumer Lag by Partition`

**Где смотреть.**

- `grafana/dashboards/services_dashboard.json:13`
- `grafana/dashboards/services_dashboard.json:27`
- `grafana/dashboards/services_dashboard.json:41`
- `grafana/dashboards/services_dashboard.json:65`
- `grafana/dashboards/services_dashboard.json:79`
- `grafana/dashboards/services_dashboard.json:93`
- `grafana/dashboards/services_dashboard.json:107`
- `grafana/dashboards/services_dashboard.json:121`

**Подпункт.** «Минимум 4 панели на дашборде.»

**Что сделано.** На сервисном dashboard `8` панелей.

**Подтверждение.** Панели перечислены выше, файл экспортирован в JSON.

**Подпункт.** «Дашборд обновляется в реальном времени.»

**Что сделано.** Dashboard provisioned в Grafana и работает поверх живого Prometheus datasource. Обновление идёт в UI Grafana в реальном времени.

**Где смотреть.**

- `grafana/provisioning/datasources/prometheus.yml:1-10`
- `grafana/provisioning/dashboards/dashboards.yml:1-11`

**Подпункт.** «Дашборд экспортирован в JSON и хранится в репозитории.»

**Что сделано.** JSON лежит в репозитории.

**Где смотреть.**

- `grafana/dashboards/services_dashboard.json:1-128`

**Подпункт.** «Grafana поднимается в docker-compose с автоматическим provisioning дашбордов и datasource.»

**Что сделано.** В compose есть сервис `grafana`, а provisioning directories примонтированы как code.

**Где смотреть.**

- `docker-compose.yml:351-372`
- `grafana/provisioning/datasources/prometheus.yml:1-10`
- `grafana/provisioning/dashboards/dashboards.yml:1-11`

### 3.2 Пункт 6. Grafana: дашборд инфраструктуры

**Оригинальная формулировка.** «Необходимо создать отдельный дашборд для мониторинга инфраструктуры вашей системы.»

**Что сделано.** Создан `HW7 Infrastructure Observability`.

**Где смотреть.**

- `grafana/dashboards/infrastructure_dashboard.json:1-75`

**Подпункт.** «Дашборд должен отвечать на вопрос: “Где сейчас узкое место?”»

**Что сделано.** Дашборд показывает:

- Kafka broker count;
- Kafka consumer group lag;
- CPU usage контейнеров;
- memory working set контейнеров;
- availability monitoring targets.

По этим панелям видно, где bottleneck: в consumer lag, CPU, памяти или недоступности target.

**Где смотреть.**

- `grafana/dashboards/infrastructure_dashboard.json:13`
- `grafana/dashboards/infrastructure_dashboard.json:26`
- `grafana/dashboards/infrastructure_dashboard.json:40`
- `grafana/dashboards/infrastructure_dashboard.json:54`
- `grafana/dashboards/infrastructure_dashboard.json:68`

**Подпункт.** «Минимум 3 панели с метриками инфраструктурных компонентов.»

**Что сделано.** На infrastructure dashboard `5` панелей.

**Подпункт.** «Как именно экспортировать метрики из инфраструктурных компонентов ... студент решает самостоятельно.»

**Что сделано.**

- Kafka метрики отдаются через `kafka-exporter`;
- container CPU/memory - через `cadvisor`.

**Где смотреть.**

- `docker-compose.yml:276-305`
- `prometheus/prometheus.yml:27-37`

### 3.3 Пункт 7. Нагрузочное тестирование, интегрированное в CI

**Оригинальная формулировка.** «Необходимо добавить нагрузочное тестирование в CI pipeline.»

**Что сделано.** Реализован `k6` сценарий и включён в workflow как отдельный stage после E2E.

**Где смотреть.**

- `scripts/load/wms_events.js:1-87`
- `.github/workflows/hw7-ci.yml:76-80`

**Подпункт.** «Тест запускается из CI.»

**Что сделано.** Workflow вызывает `./scripts/run_load_tests.sh`.

**Где смотреть.**

- `.github/workflows/hw7-ci.yml:76-77`
- `scripts/run_load_tests.sh:1-12`

**Подпункт.** «Тест создаёт реалистичную нагрузку: минимум 10 VU, минимум 30 секунд.»

**Что сделано.**

- `publish` scenario: `10 VUs`, `30s`;
- отдельный `health` scenario: `1 VU`, `30s`.

**Где смотреть.**

- `scripts/load/wms_events.js:4-18`

**Подпункт.** «Определены пороги (thresholds): при превышении тест возвращает exit code 1 и CI падает.»

**Что сделано.**

- `http_req_failed < 1%`
- `http_req_duration p95 < 500ms`
- `health` checks `> 99%`

**Где смотреть.**

- `scripts/load/wms_events.js:19-24`

**Подпункт.** «Под нагрузкой сервис остаётся доступным (health check проходит).»

**Что сделано.** Внутри k6 есть отдельный health scenario, который непрерывно вызывает `GET /api/v1/health`.

**Где смотреть.**

- `scripts/load/wms_events.js:13-17`
- `scripts/load/wms_events.js:81-87`

**Подпункт.** «Логи/результаты нагрузочного теста сохраняются как артефакты пайплайна.»

**Что сделано.** k6 summary экспортируется в `artifacts/load/k6-summary.json`, а весь каталог `artifacts` публикуется GitHub Actions job-ом.

**Где смотреть.**

- `docker-compose.yml:399-411`
- `.github/workflows/hw7-ci.yml:86-91`
- `artifacts/load/k6-summary.json`

---

## 4. Пункты на 8–10 баллов

### 4.1 Пункт 8. E2E + нагрузка + метрики в одном CI прогоне

**Оригинальная формулировка.** «Необходимо реализовать комплексный CI сценарий, который запускает систему, нагружает её и проверяет метрики из Prometheus.»

**Что сделано.** В одном CI job `start-stack` последовательно выполняются:

1. `docker compose up -d --build`
2. readiness check
3. integration tests
4. e2e tests
5. load tests
6. Prometheus SLI gates
7. artifacts
8. teardown

**Почему так устроено.** Stack-dependent стадии сделаны не отдельными jobs, а последовательными steps одного job, потому что GitHub-hosted jobs не делят один и тот же живой Docker stack.

**Где смотреть.**

- `.github/workflows/hw7-ci.yml:52-95`

**Подпункт.** «Поднимает всю систему (docker-compose up).»

**Где смотреть.**

- `.github/workflows/hw7-ci.yml:64-65`

**Подпункт.** «Запускает нагрузку.»

**Где смотреть.**

- `.github/workflows/hw7-ci.yml:76-77`

**Подпункт.** «Параллельно собирает метрики из Prometheus.»

**Что сделано.** Метрики непрерывно собирает запущенный Prometheus, который скрейпит сервисы и exporters во время всего CI job.

**Где смотреть.**

- `prometheus/prometheus.yml:1-37`
- `.github/workflows/hw7-ci.yml:64-80`

**Подпункт.** «Проверяет числовые условия по метрикам, например: error rate < 1%, p95 latency < 500ms.»

**Что сделано.** Отдельный Python gate script проверяет:

- API availability `>= 99.5%`
- WMS p95 latency `< 0.5s`
- event end-to-end delay p95 `< 5s`

Для каждого есть и SLO target, и failure threshold.

**Где смотреть.**

- `scripts/check_prometheus_gates.py:15-37`
- `scripts/check_prometheus_gates.py:107-154`

**Подпункт.** «CI падает, если условия не выполнены.»

**Что сделано.** Если метрика пересекает failure threshold, `scripts/check_prometheus_gates.py` возвращает exit code `1`.

**Где смотреть.**

- `scripts/check_prometheus_gates.py:147-154`

**Подпункт.** «Метрики и результаты проверки сохраняются в артефакты пайплайна.»

**Что сделано.** Сохраняются:

- `artifacts/prometheus/gates.json`
- `artifacts/load/k6-summary.json`
- `artifacts/ci/prometheus-alerts.json`
- `artifacts/ci/alertmanager-alerts.json`
- `artifacts/ci/docker-compose.log`

**Где смотреть.**

- `scripts/check_prometheus_gates.py:131-133`
- `scripts/collect_artifacts.sh:10-16`
- `.github/workflows/hw7-ci.yml:82-91`

### 4.2 Пункт 9. Prometheus alert rules как код

**Оригинальная формулировка.** «Необходимо определить alert rules для мониторинга проблем вашей системы.»

**Что сделано.** Alert rules хранятся в репозитории и подхватываются Prometheus как code.

**Где смотреть.**

- `prometheus/alert_rules.yml:1-49`
- `prometheus/prometheus.yml:5-12`

**Подпункт.** «Определены alert rules минимум для двух из следующих ситуаций: высокий error rate, высокая latency, consumer lag, недоступность сервиса.»

**Что сделано.** Реализованы:

- `HighHttpErrorRate`
- `HighHttpLatencyP95`
- `ServiceDown`
- `ConsumerLagHigh`
- дополнительно `EventProcessingDelayHigh`

**Где смотреть.**

- `prometheus/alert_rules.yml:4-49`

**Подпункт.** «Alert rules хранятся в репозитории.»

**Где смотреть.**

- `prometheus/alert_rules.yml:1-49`

**Подпункт.** «Alertmanager поднимается в docker-compose.»

**Где смотреть.**

- `docker-compose.yml:306-323`
- `alertmanager/alertmanager.yml:1-12`

**Подпункт.** «Продемонстрировано, что при превышении порога алерт реально срабатывает (переходит в состояние firing).»

**Что сделано.** Отдельный скрипт `demo_monitoring.sh` демонстрирует два реальных firing сценария:

- `ConsumerLagHigh`
- `ServiceDown`

Он сохраняет snapshots и из Prometheus, и из Alertmanager.

**Где смотреть.**

- `scripts/demo_monitoring.sh:49-102`
- `artifacts/prometheus/demo_monitoring/consumer-lag-high-prometheus.json`
- `artifacts/prometheus/demo_monitoring/consumer-lag-high-alertmanager.json`
- `artifacts/prometheus/demo_monitoring/service-down-prometheus.json`
- `artifacts/prometheus/demo_monitoring/service-down-alertmanager.json`

**Подпункт.** «Алерты видны в UI Alertmanager или Grafana.»

**Что сделано.** Alertmanager поднят отдельным сервисом, Prometheus отправляет ему alerts, а snapshots сохраняются через `api/v2/alerts`.

**Где смотреть.**

- `prometheus/prometheus.yml:8-12`
- `scripts/demo_monitoring.sh:41-43`
- `scripts/demo_monitoring.sh:100-101`

**Подпункт.** «Конкретные PromQL-выражения, пороги и for-длительности студент определяет самостоятельно.»

**Что сделано.** Expressions, thresholds и `for` явно зафиксированы в `prometheus/alert_rules.yml`.

**Где смотреть.**

- `prometheus/alert_rules.yml:4-49`

### 4.3 Пункт 10. System-level SLI и пороги отказа

**Оригинальная формулировка.** «Необходимо определить SLI (Service Level Indicators) для всей вашей системы и показать, как они используются.»

**Что сделано.** Определены три system-level SLI:

1. `API availability`
2. `WMS publish latency p95`
3. `Event end-to-end delay p95`

**Где смотреть.**

- `README.md:1-127`
- `scripts/check_prometheus_gates.py:15-37`

**Подпункт.** «Определены 2–3 SLI всей системы.»

**Что сделано.** Определены три SLI, что полностью соответствует диапазону `2-3`.

**Подпункт.** «Для каждого SLI определены: SLO (целевое значение), порог отказа.»

**Что сделано.**

- `API availability`: target `>= 99.5%`, failure threshold `>= 95%`
- `WMS latency p95`: target `<= 0.5s`, failure threshold `<= 1.0s`
- `Event end-to-end delay p95`: target `<= 5.0s`, failure threshold `<= 10.0s`

**Где смотреть.**

- `README.md:69-84`
- `scripts/check_prometheus_gates.py:16-36`

**Подпункт.** «SLI считаются из метрик Prometheus (не hardcoded значения, а реальные PromQL-запросы).»

**Что сделано.** Для всех трёх SLI используются реальные PromQL expressions.

**Где смотреть.**

- `README.md:69-84`
- `scripts/check_prometheus_gates.py:16-36`

**Подпункт.** «SLI используются в тестах или алертах.»

**Что сделано.** Эти SLI используются в CI gates. При пересечении failure threshold CI падает.

**Где смотреть.**

- `scripts/check_prometheus_gates.py:105-154`
- `scripts/run_prometheus_gates.sh:1-34`
- `.github/workflows/hw7-ci.yml:79-80`

**Подпункт.** «SLI задокументированы в README: что измеряется, какой запрос к Prometheus, целевые значения, обоснование порогов.»

**Что сделано.** В `README.md` добавлен отдельный раздел `System-Level SLI, SLO and Failure Thresholds` со всеми четырьмя обязательными компонентами: что измеряется, PromQL, SLO, failure threshold и rationale.

**Где смотреть.**

- `README.md:69-84`

---

## 5. Что именно реализовано в коде сверх базовой формальной сдачи

Ниже перечислены ключевые инженерные решения, которые делают работу не “для галочки”, а действительно промышленной по духу.

### 5.1 Единая observability-слойка для двух сервисов

Вместо копирования одинаковых metrics handlers по двум приложениям сделан общий модуль `common/observability.py`. Он даёт:

- единый формат метрик;
- одинаковый label set;
- единый HTTP middleware;
- общее `/metrics` rendering API.

Где смотреть:

- `common/observability.py:1-120`
- `consumer_service/app/metrics.py:1-23`

### 5.2 Проверка доменной логики не только happy path, но и failure paths

Unit tests покрывают:

- duplicate event;
- stale event;
- `ORDER_CREATED`;
- `ORDER_COMPLETED`;
- request -> event mapping;
- middleware labels для `503` и `422`.

Где смотреть:

- `consumer_service/tests/unit/test_event_processor.py:71-179`
- `wms_service/tests/unit/test_event_publisher.py:21-67`
- `wms_service/tests/unit/test_http_metrics.py:11-44`

### 5.3 Отдельные gates по Prometheus API

Вместо “посмотрели глазами на Grafana и решили, что всё хорошо” сделан автоматический числовой gate через Prometheus API.

Где смотреть:

- `scripts/check_prometheus_gates.py:40-154`
- `artifacts/prometheus/gates.json`

### 5.4 Отдельный monitoring demo

Алерты не только описаны в YAML, но и реально воспроизводятся через скрипт, который:

- ставит consumer на pause;
- создаёт lag;
- снимает firing snapshots;
- останавливает consumer-service;
- показывает `ServiceDown`;
- поднимает сервис обратно.

Где смотреть:

- `scripts/demo_monitoring.sh:46-102`

---

## 6. Фактическая локальная проверка текущего standalone-репозитория

Проверка проведена 2026-05-16 на текущем состоянии `smart-warehouse-platform`.

### 6.1 Сборка и запуск контейнеров

Реально выполнено:

```bash
docker-compose down -v
GENERATOR_ENABLED=false docker-compose up -d --build
./scripts/wait_for_stack.sh
docker-compose ps
```

Фактический результат:

- все long-running сервисы в `Up (healthy)`;
- `hw7-cassandra-migrator` - `Exit 0`;
- `hw7-kafka-init` - `Exit 0`.

Дополнительная проверка:

```bash
docker exec hw7-cassandra-1 nodetool status
docker exec hw7-kafka-1 kafka-topics --describe --topic warehouse-events --bootstrap-server kafka-1:29092
```

Фактический результат:

- Cassandra cluster: `3` ноды `UN`;
- Kafka topic `warehouse-events`: `3` partitions, `RF=2`, `ISR healthy`.

### 6.2 Integration tests

Реально выполнено:

```bash
./scripts/run_integration_tests.sh
```

Фактический результат:

- `3 passed`

Покрытые сценарии:

- `WMS API -> Kafka -> Consumer -> Cassandra`
- `DLQ path`
- `/metrics` и Prometheus scrape

### 6.3 E2E test

Реально выполнено:

```bash
./scripts/run_e2e_tests.sh
```

Фактический результат:

- `1 passed`

Покрытый сценарий:

- `receive -> reserve -> move -> order create -> order complete`

### 6.4 Load test

Реально выполнено:

```bash
./scripts/run_load_tests.sh
```

Фактический результат по текущему `artifacts/load/k6-summary.json`:

- `http_reqs = 270`
- `http_req_failed = 0`
- `http_req_duration p95 = 7.037108449999997 ms`
- `checks_passes = 510`

Это удовлетворяет порогам:

- `http_req_failed < 1%`
- `p95 < 500ms`
- health checks зелёные

### 6.5 Prometheus gates

Реально выполнено:

```bash
./scripts/run_prometheus_gates.sh
```

Фактический результат по текущему `artifacts/prometheus/gates.json`:

- `api_availability = 1.0`
- `wms_latency_p95_seconds = 0.004827647311219602`
- `event_end_to_end_delay_p95_seconds = 1.7338913625194072`

Все три gate-проверки прошли:

- `target_passed = true`
- `gate_passed = true`

### 6.6 Alert demo

Реально выполнено:

```bash
./scripts/demo_monitoring.sh
```

Фактический результат:

- `ConsumerLagHigh` перешёл в `firing`;
- `ServiceDown` перешёл в `firing`;
- snapshots сохранены и из Prometheus, и из Alertmanager.

Артефакты:

- `artifacts/prometheus/demo_monitoring/consumer-lag-high-prometheus.json`
- `artifacts/prometheus/demo_monitoring/consumer-lag-high-alertmanager.json`
- `artifacts/prometheus/demo_monitoring/service-down-prometheus.json`
- `artifacts/prometheus/demo_monitoring/service-down-alertmanager.json`

### 6.7 Сбор runtime artifacts

Реально выполнено:

```bash
./scripts/collect_artifacts.sh artifacts/ci
```

Собираются:

- `artifacts/ci/docker-compose-ps.txt`
- `artifacts/ci/docker-compose.log`
- `artifacts/ci/prometheus-alerts.json`
- `artifacts/ci/alertmanager-alerts.json`
- `artifacts/load/k6-summary.json`
- `artifacts/prometheus/gates.json`

---

## 7. Warnings и что они означают

### 7.1 Warnings GitHub Actions

Аннотации вида “Node.js 20 is deprecated” относятся к самим GitHub Actions wrappers (`actions/checkout`, `actions/setup-python`, `actions/upload-artifact`), а не к нашему коду. Для снижения риска workflow уже запускается с:

- `FORCE_JAVASCRIPT_ACTIONS_TO_NODE24=true`

Где смотреть:

- `.github/workflows/hw7-ci.yml:8-9`

### 7.2 Runtime warnings от вендорных контейнеров

В логах есть vendor-level warning noise:

- Cassandra JVM / memlock / swap warnings;
- Zookeeper standalone-mode warnings;
- Schema Registry provider warnings;
- Kafka broker startup transient warnings;
- `kafka-init` log4j permission warnings из CLI образа Confluent.

Важно:

- они не приводят к падению контейнеров;
- не нарушают readiness;
- не ломают интеграционные, E2E, load и Prometheus gate проверки;
- `kafka-init` при этом завершает работу `Exit 0`, topics и schemas реально создаются.

То есть это не дефект бизнес-решения и не нарушение ТЗ, а шум сторонних образов и их startup tooling.

### 7.3 Особенность alert demo

После `demo_monitoring.sh` в Prometheus может кратковременно остаться `pending` по `EventProcessingDelayHigh`, потому что demo специально создаёт backlog и метрика `event_end_to_end_delay_seconds` считается по окну `5m`.

Это не означает, что система “сломана”. Это ожидаемое последствие intentional alert demo. Для нейтральной проверки SLI/SLO следует использовать `./scripts/run_prometheus_gates.sh` на обычном стенде, как это и сделано в CI.

---

## 8. Итог

Требования ДЗ №7 выполнены полностью:

- система поднимается одной командой `docker-compose up -d --build`;
- CI pipeline настроен и запускается автоматически на `push/PR`;
- есть unit, integration и E2E testing;
- оба сервиса отдают Prometheus-совместимые `/metrics`;
- Prometheus, Grafana, Alertmanager, `kafka-exporter`, `cadvisor` подняты в compose;
- сделаны service dashboards и infrastructure dashboard;
- load testing интегрировано в CI;
- Prometheus gates валидируют system-level SLI;
- alert rules оформлены как code и реально демонстрируются в `firing`;
- README содержит SLI/SLO/failure thresholds с PromQL и обоснованием;
- локальная проверка текущего standalone-репозитория пройдена и зафиксирована артефактами.

С инженерной точки зрения это уже не “набор скриптов вокруг старого ДЗ”, а полноценный reproducible test-and-observability contour поверх warehouse event system.
