# Детальный отчёт по выполнению ДЗ №7 — CI/CD, Testing & Observability

Этот отчёт сделан в том же доказательном формате, что и отчёт из `hw_6`:

1. в начале есть готовый сценарий защиты;
2. дальше по каждому требованию из `hw_7_TASK.md` приведена исходная формулировка, объяснение реализации, аргументация, почему пункт считается выполненным, и ссылки на код;
3. в конце приведена фактическая локальная проверка текущего standalone-репозитория `smart-warehouse-platform`.

---

## 0. Как показывать решение на защите

Ниже приведён не просто список команд, а реальный сценарий защиты на 15-20 минут. Его удобно держать открытым рядом с терминалом и браузером.

### 0.0 Рекомендуемый порядок показа

Оптимальный порядок для защиты такой:

1. поднять стенд и показать, что вся инфраструктура собирается одной командой;
2. показать GitHub Actions workflow и уже прошедший run;
3. руками прогнать один полный пользовательский сценарий через API и проверить Cassandra;
4. на тех же данных показать Prometheus, Grafana и Alertmanager;
5. показать автоматические integration / e2e / load / Prometheus-gates;
6. показать артефакты и объяснить, как pipeline падает при ошибках.

Если времени мало, приоритет такой:

1. `docker-compose up -d --build`;
2. успешный run в GitHub Actions;
3. ручной E2E-сценарий;
4. Grafana + Prometheus;
5. `./scripts/run_e2e_tests.sh` и `./scripts/run_prometheus_gates.sh`.

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

Что показать ассистенту сразу после старта:

```bash
curl -sS http://localhost:8001/api/v1/health | python3 -m json.tool
curl -sS http://localhost:8002/health | python3 -m json.tool
curl -sS http://localhost:8001/metrics | head -n 20
curl -sS http://localhost:8002/metrics | head -n 20
docker exec smart-warehouse-cassandra-1 nodetool status
docker exec smart-warehouse-kafka-1 kafka-topics --describe --topic warehouse-events --bootstrap-server kafka-1:29092
docker exec smart-warehouse-kafka-1 kafka-topics --describe --topic warehouse-events-dlq --bootstrap-server kafka-1:29092
```

Что должно быть видно:

- все long-running контейнеры в `Up`;
- `kafka-init` и `cassandra-migrator` завершились `Exit 0`;
- Cassandra cluster состоит из `3` нод со статусом `UN`;
- создан основной topic `warehouse-events` и DLQ topic `warehouse-events-dlq`;
- оба сервиса healthy;
- `/metrics` у обоих сервисов отвечает в Prometheus-compatible формате.

Где обеспечивается готовность стенда:

- `scripts/wait_for_stack.sh:1-30`
- `docker-compose.yml:1-423`

### 0.2 Что именно показать в GitHub Actions и что при этом проговорить

В GitHub открыть:

- workflow файл `.github/workflows/smart-warehouse-ci.yml`;
- последний успешный run этого workflow;
- при наличии - один исторический failed run, чтобы показать отрицательный сценарий.

Что проговорить по самому workflow:

1. workflow запускается на `push`, `pull_request`, `workflow_dispatch`;
2. pipeline разбит на `3` jobs: `build-images -> unit-tests -> start-stack`;
3. `build-images` отдельно доказывает, что Docker-образы собираются из репозитория;
4. `unit-tests` запускает тесты обоих сервисов отдельно и сохраняет `JUnit XML` в артефакты;
5. `start-stack` поднимает реальную инфраструктуру и уже на ней последовательно гоняет `integration`, `e2e`, `load`, `Prometheus gates`;
6. в CI выставлен `GENERATOR_ENABLED=false`, чтобы synthetic traffic не загрязнял метрики и gates;
7. `if: always()` используется только там, где это нужно для диагностики: сбор артефактов, upload, teardown;
8. любой красный step в `build`, `tests`, `load` или `gates` завершает job ненулевым exit code.

Что показать в UI run-а:

1. job `build-images` и лог `docker compose build`;
2. job `unit-tests` и шаги `Run WMS unit tests`, `Run consumer unit tests`;
3. job `start-stack` и шаги:
   - `Start stack`
   - `Wait for stack readiness`
   - `Run integration tests`
   - `Run E2E tests`
   - `Run load tests`
   - `Validate Prometheus gates`
4. вкладку `Artifacts` и артефакты:
   - `smart-warehouse-unit-artifacts`
   - `smart-warehouse-stack-artifacts`

Что полезно проговорить про артефакты:

- в unit-артефактах лежат `artifacts/unit/wms-unit.xml` и `artifacts/unit/consumer-unit.xml`;
- в stack-артефактах лежат `artifacts/tests/integration.xml`, `artifacts/tests/e2e.xml`, `artifacts/load/k6-summary.json`, `artifacts/prometheus/gates.json`, `artifacts/ci/docker-compose.log`, снапшоты alerts из Prometheus и Alertmanager;
- это важно, потому что при падении pipeline студент не теряет диагностику.

Где смотреть код:

- `.github/workflows/smart-warehouse-ci.yml:1-80`
- `scripts/collect_artifacts.sh:1-16`
- `scripts/check_prometheus_gates.py:1-154`

### 0.3 Ручной E2E-сценарий для защиты: полный пользовательский поток через API

Это самый важный блок для защиты. Он показывает не “отдельный сервис”, а сквозную логику:

`WMS HTTP API -> Kafka -> consumer-service -> Cassandra projections`

Перед ручным сценарием лучше изолировать окно от фонового synthetic traffic:

```bash
source ./scripts/_demo_common.sh
demo_prepare_manual_window
```

Что делает helper:

- ставит встроенный generator на паузу;
- ждёт, пока `consumer_lag` опустится ниже безопасного порога;
- тем самым manual E2E не конфликтует с фоновым потоком.

Теперь подготовить уникальные идентификаторы:

```bash
export SUFFIX="$(date +%s)"
export PRODUCT_ID="SKU-DEMO-${SUFFIX}"
export ORDER_ID="ORDER-DEMO-${SUFFIX}"
export BASE_TS="$(date -u +%s000)"
echo "$PRODUCT_ID"
echo "$ORDER_ID"
```

Важно: команды ниже лучше запускать **по одной**, а не вставлять весь раздел целиком в IDE task-runner или одноразовый терминал.

#### Шаг 1. PRODUCT_RECEIVED

```bash
curl -sS -X POST http://localhost:8001/api/v1/events -H "Content-Type: application/json" -d "{\"event_id\":\"${PRODUCT_ID}-recv\",\"event_type\":\"PRODUCT_RECEIVED\",\"occurred_at\":${BASE_TS},\"product_id\":\"${PRODUCT_ID}\",\"zone_id\":\"ZONE-A\",\"quantity\":100}" | python3 -m json.tool
```

Что проговорить:

- API отвечает `202 Accepted`;
- в теле ответа есть `event_id` и `status = accepted`;
- это подтверждает корректность публичного API и публикации события.

Проверка в Cassandra:

```bash
sleep 3
docker exec smart-warehouse-cassandra-1 cqlsh -e "SELECT product_id, zone_id, available_quantity, reserved_quantity FROM warehouse.inventory_by_product_zone WHERE product_id = '${PRODUCT_ID}' AND zone_id = 'ZONE-A';"
```

Что должно быть видно:

- `available_quantity = 100`
- `reserved_quantity = 0`

#### Шаг 2. PRODUCT_RESERVED

```bash
curl -sS -X POST http://localhost:8001/api/v1/events -H "Content-Type: application/json" -d "{\"event_id\":\"${PRODUCT_ID}-reserve\",\"event_type\":\"PRODUCT_RESERVED\",\"occurred_at\":$((BASE_TS+1000)),\"product_id\":\"${PRODUCT_ID}\",\"zone_id\":\"ZONE-A\",\"quantity\":30}" | python3 -m json.tool

sleep 3
docker exec smart-warehouse-cassandra-1 cqlsh -e "SELECT product_id, zone_id, available_quantity, reserved_quantity FROM warehouse.inventory_by_product_zone WHERE product_id = '${PRODUCT_ID}' AND zone_id = 'ZONE-A';"
```

Что должно быть видно:

- `available_quantity = 70`
- `reserved_quantity = 30`

#### Шаг 3. PRODUCT_MOVED

```bash
curl -sS -X POST http://localhost:8001/api/v1/events -H "Content-Type: application/json" -d "{\"event_id\":\"${PRODUCT_ID}-move\",\"event_type\":\"PRODUCT_MOVED\",\"occurred_at\":$((BASE_TS+2000)),\"product_id\":\"${PRODUCT_ID}\",\"from_zone_id\":\"ZONE-A\",\"to_zone_id\":\"ZONE-B\",\"quantity\":20}" | python3 -m json.tool

sleep 3
docker exec smart-warehouse-cassandra-1 cqlsh -e "SELECT product_id, zone_id, available_quantity, reserved_quantity FROM warehouse.inventory_by_product_zone WHERE product_id = '${PRODUCT_ID}' AND zone_id IN ('ZONE-A', 'ZONE-B');"
```

Что должно быть видно:

- для `ZONE-A`: `available_quantity = 50`, `reserved_quantity = 30`;
- для `ZONE-B`: `available_quantity = 20`, `reserved_quantity = 0`.

#### Шаг 4. ORDER_CREATED

```bash
curl -sS -X POST http://localhost:8001/api/v1/events -H "Content-Type: application/json" -d "{\"event_id\":\"${ORDER_ID}-create\",\"event_type\":\"ORDER_CREATED\",\"occurred_at\":$((BASE_TS+3000)),\"order_id\":\"${ORDER_ID}\",\"items\":[{\"product_id\":\"${PRODUCT_ID}\",\"zone_id\":\"ZONE-A\",\"quantity\":15}]}" | python3 -m json.tool

sleep 3
docker exec smart-warehouse-cassandra-1 cqlsh -e "SELECT product_id, zone_id, available_quantity, reserved_quantity FROM warehouse.inventory_by_product_zone WHERE product_id = '${PRODUCT_ID}' AND zone_id = 'ZONE-A';"
```

Что должно быть видно:

- `available_quantity = 35`
- `reserved_quantity = 45`

Здесь удобно отдельно проговорить, что `ORDER_CREATED` - это уже не просто изменение одного склада, а доменная операция, которая пересчитывает резервы по товару.

#### Шаг 5. ORDER_COMPLETED

```bash
curl -sS -X POST http://localhost:8001/api/v1/events -H "Content-Type: application/json" -d "{\"event_id\":\"${ORDER_ID}-complete\",\"event_type\":\"ORDER_COMPLETED\",\"occurred_at\":$((BASE_TS+4000)),\"order_id\":\"${ORDER_ID}\"}" | python3 -m json.tool

sleep 5
docker exec smart-warehouse-cassandra-1 cqlsh -e "SELECT product_id, zone_id, available_quantity, reserved_quantity FROM warehouse.inventory_by_product_zone WHERE product_id = '${PRODUCT_ID}' AND zone_id = 'ZONE-A';"

docker exec smart-warehouse-cassandra-1 cqlsh -e "SELECT total_available_quantity, total_reserved_quantity FROM warehouse.inventory_totals_by_product WHERE product_id = '${PRODUCT_ID}';"

docker exec smart-warehouse-cassandra-1 cqlsh -e "SELECT status FROM warehouse.orders_by_id WHERE order_id = '${ORDER_ID}';"
```

Что должно быть видно в конце полного сценария:

- `ZONE-A`: `available_quantity = 35`, `reserved_quantity = 30`;
- totals по товару: `total_available_quantity = 55`, `total_reserved_quantity = 30`;
- заказ в `orders_by_id` имеет статус `COMPLETED`.

Это и есть главный ручной E2E-доказательный сценарий для защиты. Он полностью соответствует автоматическому тесту `tests/e2e/test_full_flow.py`, только воспроизводится вручную.

Где смотреть код:

- `tests/e2e/test_full_flow.py:1-105`
- `tests/conftest.py:1-82`
- `wms_service/app/api/routes.py:33-75`
- `consumer_service/app/application/processor.py:26-410`
- `consumer_service/app/infrastructure/cassandra_repository.py:24-312`

### 0.4 Что ещё показать рядом с ручным E2E

После ручного сценария полезно сразу доказать, что он не “одноразовый”, а автоматизированный:

```bash
./scripts/run_integration_tests.sh
./scripts/run_e2e_tests.sh
```

Что проговорить:

- integration-тесты проверяют именно межсервисное взаимодействие и DLQ-path;
- e2e-тест повторяет полный пользовательский сценарий через API и проверяет Cassandra;
- тесты изолированы, потому что таблицы очищаются фикстурой и используются уникальные suffix-ы;
- запуск одной командой возвращает `exit code 0` при успехе и `exit code 1` при ошибке.

Если есть время, показать нагрузку:

```bash
./scripts/run_load_tests.sh
```

Что проговорить:

- k6 генерирует HTTP traffic именно в `POST /api/v1/events`;
- поэтому после нагрузки двигаются `WMS Throughput` и `WMS Latency` панели;
- это важная деталь: встроенный generator публикует напрямую в Kafka, а не через HTTP, поэтому WMS HTTP-панели реагируют именно на ручные POST-запросы и на k6 load test.

Где смотреть:

- `scripts/run_integration_tests.sh:1-10`
- `scripts/run_e2e_tests.sh:1-10`
- `scripts/run_load_tests.sh:1-12`
- `tests/integration/test_service_interactions.py:1-150`
- `tests/e2e/test_full_flow.py:1-105`
- `scripts/load/wms_events.js:1-95`

### 0.5 Что показать в Prometheus, Grafana и Alertmanager после E2E и load

После ручного E2E и/или `./scripts/run_load_tests.sh` открыть:

- `Prometheus`: `http://localhost:9090`
- `Grafana`: `http://localhost:3000`
- `Alertmanager`: `http://localhost:9094`

#### Prometheus

Что показать в Prometheus UI:

1. `Status -> Targets`  
   Должны быть `UP` как минимум:
   - `wms-service`
   - `consumer-service`
   - `kafka-exporter`
   - `cadvisor`

2. `Graph` / instant query для HTTP API WMS:

```promql
sum(rate(http_requests_total{service="wms-service",endpoint="/api/v1/events"}[5m]))
```

Это должен быть `throughput` по WMS API.

3. `Graph` / instant query для p95 latency WMS:

```promql
histogram_quantile(0.95, sum by(le) (rate(http_request_duration_seconds_bucket{service="wms-service",endpoint="/api/v1/events"}[5m])))
```

4. `Graph` / instant query для end-to-end delay:

```promql
histogram_quantile(0.95, sum by(le) (rate(event_end_to_end_delay_seconds_bucket[5m])))
```

5. `Alerts` или query:

```promql
ALERTS
```

Если ассистент спрашивает, почему именно эти PromQL важны, ответ простой:

- первый query показывает входной API throughput;
- второй - SLI по latency для публичного API;
- третий - реальную асинхронную задержку от `occurred_at` до terminal handling в consumer;
- четвёртый показывает текущее состояние alert rules.

#### Grafana

В Grafana открыть два дашборда:

1. `Smart Warehouse Services Observability`
2. `Smart Warehouse Infrastructure Observability`

Что показать на service dashboard:

- `WMS Throughput`
- `WMS Latency Percentiles`
- `Consumer Event Throughput`
- `Consumer Processing Latency p95`
- `Event End-to-End Delay p95`

Важно проговорить заранее, чтобы не потерять время на защите:

- `WMS Throughput` и `WMS Latency` считают именно HTTP-трафик на `POST /api/v1/events`;
- если до открытия дашборда не было ручных POST-запросов или `k6`, эти панели могут быть нулевыми;
- чтобы они гарантированно двигались, достаточно либо прогнать ручной E2E выше, либо выполнить `./scripts/run_load_tests.sh`.

Что показать на infra dashboard:

- `Kafka Broker Count`
- `Kafka Consumer Group Lag`
- `Infra CPU Usage`
- `Infra Memory Working Set`
- `Monitoring Targets Up`

После холодного старта cAdvisor-метрикам может потребоваться `20-40` секунд, чтобы CPU/memory панели перестали быть пустыми.

#### Alertmanager

Для демонстрации реальных алертов использовать:

```bash
./scripts/demo_monitoring.sh
```

Что делает этот сценарий:

1. ставит generator на паузу и ждёт low lag;
2. ставит consumer на паузу и генерирует backlog;
3. ждёт firing alert `ConsumerLagHigh`;
4. затем останавливает контейнер consumer и ждёт firing alert `ServiceDown`;
5. сохраняет snapshot-ы в `artifacts/prometheus/demo_monitoring`.

Что показать ассистенту:

- в Prometheus query `ALERTS{alertstate="firing"}`;
- в Alertmanager список текущих firing alerts;
- файлы со snapshot-ами в `artifacts/prometheus/demo_monitoring`.

Где смотреть код:

- `prometheus/prometheus.yml:1-37`
- `prometheus/alert_rules.yml:1-49`
- `grafana/dashboards/services_dashboard.json:1-160`
- `grafana/dashboards/infrastructure_dashboard.json:1-90`
- `alertmanager/alertmanager.yml:1-12`
- `scripts/demo_monitoring.sh:1-102`
- `scripts/check_prometheus_gates.py:1-154`

### 0.6 Как показать, что pipeline реально падает при ошибках

На защите ассистент может отдельно спросить, как доказать отрицательный сценарий. Самый безопасный способ - не ломать `main`, а показывать один из двух вариантов:

#### Вариант A. Показать исторический failed run

Это лучший вариант. В GitHub Actions открыть старый run, где pipeline уже падал, и показать:

- какой именно step был красным;
- что downstream логика не “замаскировала” ошибку;
- что артефакты всё равно сохранились через `if: always()`.

#### Вариант B. Подготовить отдельную одноразовую demo-ветку

Если ассистент просит live negative demo, делать это только на отдельной ветке, не на `main`.

Минимальный безопасный вариант:

1. временно сломать один unit-test, например добавить `assert False`;
2. push в отдельную ветку;
3. показать, что job `unit-tests` стал красным;
4. затем revert / удалить ветку.

Что при этом проговорить:

- pipeline падает на первом реальном дефекте;
- build/test/load/gates не замалчиваются;
- артефакты при этом сохраняются, поэтому диагностика не теряется.

### 0.7 Что ещё можно показать, если ассистент просит больше деталей

Если после основного сценария остаётся время, имеет смысл показать ещё вот это:

1. `curl -sS http://localhost:8002/metrics | grep '^consumer_lag'`  
   Видно lag по партициям consumer-а.

2. `curl -sS http://localhost:9090/api/v1/alerts | python3 -m json.tool | sed -n '1,80p'`  
   Видно, что Prometheus реально держит alerts, а не просто хранит rule-файл.

3. `./scripts/run_prometheus_gates.sh`  
   Это локальный аналог CI-step `Validate Prometheus gates`.

4. `cat artifacts/prometheus/gates.json | python3 -m json.tool | sed -n '1,120p'`  
   Видно конкретные SLI, raw queries, target и failure threshold.

5. `./scripts/collect_artifacts.sh artifacts/ci && ls -R artifacts/ci`  
   Видно, что после прогона собираются compose logs и snapshots alert-ов.

### 0.8 Сбор артефактов и остановка стенда

В конце демонстрации:

```bash
./scripts/collect_artifacts.sh artifacts/ci
docker-compose down -v
```

Где смотреть:

- `scripts/collect_artifacts.sh:1-16`

---

## 1. Общие требования

Ниже общие требования проверяются не по принципу "что-то похожее есть", а по более жёсткому критерию: можно ли показать ассистенту работающий механизм, можно ли связать его с конкретным кодом и можно ли доказать, что это именно системное решение, а не ручной workaround под защиту. По этому критерию все шесть общих требований закрыты полностью.

### 1.1 «Все сервисы и инфраструктура поднимаются одной командой docker-compose up.»

**Что сделано.** Весь стенд описан в одном `docker-compose.yml`: сервисы приложения, Kafka, Schema Registry, Cassandra cluster, Prometheus, Grafana, Alertmanager, `kafka-exporter`, `cadvisor`, а также контейнеры `kafka-init`, `cassandra-migrator`, `tests`, `load-tests`.

**Почему это выполняет требование.** Студенту не нужно вручную запускать отдельные зависимости. Достаточно `docker-compose up -d --build`, после чего всё окружение поднимается как единый reproducible stack.

**Почему это именно полное выполнение, а не частичное.** В ТЗ важно не просто наличие `docker-compose.yml`, а то, что им действительно покрыта вся операционная среда: бизнес-сервисы, brokers, storage, monitoring, alerting, test runners и load runner. Здесь нет вынесенных "ручных" шагов вида "сначала отдельно запустите Prometheus", "потом локально поднимите k6", "потом руками создайте topic". Topic creation, Cassandra migrations, Prometheus, Grafana и Alertmanager входят в один стек и воспроизводятся из репозитория.

**Где смотреть.**

- `docker-compose.yml:1-423`
- `scripts/wait_for_stack.sh:21-30`

### 1.2 «CI pipeline запускается автоматически при push или PR.»

**Что сделано.** GitHub Actions workflow объявлен в корне репозитория и запускается на `push`, `pull_request`, `workflow_dispatch`.

**Почему это выполняет требование.** Автоматический старт на `push/PR` закрывает обязательную часть ТЗ. `workflow_dispatch` добавлен как удобный ручной запуск для защиты и повторных прогонов.

**Почему это именно полное выполнение, а не частичное.** В работе не используется локальный shell-script, который студент запускает вручную и называет "pipeline". Есть именно repository-native CI-конфигурация в `.github/workflows`, которая привязана к событиям GitHub и реально исполняется в GitHub Actions. Это соответствует требованию буквально, а не по аналогии.

**Где смотреть.**

- `.github/workflows/smart-warehouse-ci.yml:1-10`

### 1.3 «Пайплайн падает при любой ошибке (build, tests, metrics validation).»

**Что сделано.** В workflow нет подавления ошибок на критических стадиях. Ошибка в build, unit, integration, e2e, load или Prometheus gates завершает step/job ненулевым exit code.

**Почему это выполняет требование.** В pipeline нет “мягких” pass-through стадий для ключевых проверок. Единственное, что выполняется через `if: always()`, это сбор артефактов и teardown, чтобы не потерять диагностику после падения.

**Почему это именно полное выполнение, а не частичное.** Важный нюанс задания: падение должно происходить не только на тестах, но и на числовой валидации метрик. Здесь это обеспечивается двумя независимыми механизмами: k6 сам возвращает ошибку при нарушении thresholds, а `check_prometheus_gates.py` возвращает `exit code 1`, если прометеевские SLI вышли за failure thresholds. То есть "падает pipeline" относится не к одной стадии, а ко всему quality gate контуру.

**Где смотреть.**

- `.github/workflows/smart-warehouse-ci.yml:18-20`
- `.github/workflows/smart-warehouse-ci.yml:36-43`
- `.github/workflows/smart-warehouse-ci.yml:64-80`
- `scripts/check_prometheus_gates.py:105-154`

### 1.4 «Метрики экспортируются в Prometheus-совместимом формате.»

**Что сделано.** Оба сервиса отдают `/metrics` через `prometheus_client.generate_latest()` с корректным content type.

**Почему это выполняет требование.** Это именно Prometheus scrape endpoint, а не кастомный JSON.

**Почему это именно полное выполнение, а не частичное.** В отчёте важно зафиксировать, что речь не о метриках "вообще", а именно о scrape-compatible exposition format. Здесь соблюдены обе части: есть endpoint `/metrics`, и он отдаёт стандартный формат `prometheus_client`, который потом реально потребляется Prometheus scrape job-ами и проверяется интеграционным тестом.

**Где смотреть.**

- `common/observability.py:72-73`
- `wms_service/app/api/routes.py:78-81`
- `consumer_service/app/api/routes.py:40-43`

### 1.5 «Тесты воспроизводимы и автоматизированы (без ручных действий).»

**Что сделано.** Для каждого слоя есть отдельный запускной script, который поднимает нужную среду или использует уже поднятый compose stack. Интеграционные и E2E проверки гоняются в Docker-профиле `tests`, нагрузка - в профиле `load`.

**Почему это выполняет требование.** Тесты стартуют командами, не требуют ручной подготовки данных, и возвращают exit code процесса.

**Почему это именно полное выполнение, а не частичное.** Воспроизводимость здесь обеспечивается не одной командой запуска, а ещё и изоляцией состояния: фикстуры очищают Cassandra-проекции, тесты используют уникальные идентификаторы, а сами проверки исполняются в контролируемой Docker-среде. Иначе это были бы "автоматизированные, но нестабильные" тесты, что под ТЗ не подходит.

**Где смотреть.**

- `scripts/run_unit_tests.sh:1-8`
- `scripts/run_integration_tests.sh:1-10`
- `scripts/run_e2e_tests.sh:1-10`
- `scripts/run_load_tests.sh:1-12`
- `tests/conftest.py:48-97`

### 1.6 «Вы используете свои сервисы из предыдущего ДЗ (не нужно создавать новые с нуля).»

**Что сделано.** Бизнес-архитектура сохранена: `wms-service + consumer-service + Kafka + Cassandra`. Новое ДЗ реализовано как standalone-репозиторий на базе предыдущего решения, а не как новая искусственная система.

**Почему это выполняет требование.** Предметная область, event flow, Cassandra projections, Kafka topics, DLQ, schema evolution и consumer processing унаследованы из `hw_6`; поверх них добавлены CI, tests, observability и SLI/SLO.

**Почему это именно полное выполнение, а не частичное.** Работа не имитирует "использование прошлого ДЗ" через новый пустой сервис с одной-двумя заглушками. Здесь сохранена сама warehouse event architecture: producer публикует складские события, consumer применяет доменную логику и поддерживает Cassandra projections, а новый контур добавлен поверх существующей предметной модели.

**Где смотреть.**

- `wms_service/app/application/event_service.py:22-93`
- `consumer_service/app/application/processor.py:26-410`
- `consumer_service/app/infrastructure/cassandra_repository.py:24-312`

---

## 2. Пункты на 1–4 балла

Для блока `1-4` принципиально важно, что каждый следующий пункт опирается на предыдущий. Поэтому ниже отдельно фиксируется не только наличие файла или теста, но и то, что весь минимальный контур CI + integration + E2E + metrics работает как одна цепочка.

### 2.1 Пункт 1. CI pipeline

**Оригинальная формулировка.** «Необходимо настроить CI pipeline, который автоматически запускается при push или PR.»

**Что сделано.** В корне standalone-репозитория лежит GitHub Actions workflow `.github/workflows/smart-warehouse-ci.yml`. Он запускается автоматически на `push` и `pull_request`, а также вручную на `workflow_dispatch`.

**Почему пункт закрыт полностью.** В ТЗ дано право самому спроектировать структуру jobs и stages. Здесь структура не случайна: `build-images` отделён, чтобы ранний build failure не тратил время на тестовую среду; `unit-tests` вынесен отдельно, чтобы дешёвые ошибки отсекались раньше дорогого Docker stack; `start-stack` объединяет stack-dependent шаги в один job, потому что GitHub-hosted jobs не делят живой Docker daemon state между собой. Это не "минимальный YAML для галочки", а осмысленный CI design под ограничения платформы.

**Где смотреть.**

- `.github/workflows/smart-warehouse-ci.yml:1-10`

**Подпункт.** «В пайплайне есть шаги: build — сборка всех ваших сервисов.»

**Что сделано.** Отдельный job `build-images` выполняет `docker compose build` по всему стеку.

**Где смотреть.**

- `.github/workflows/smart-warehouse-ci.yml:12-20`

**Подпункт.** «unit tests — модульные тесты для каждого сервиса.»

**Что сделано.** Job `unit-tests` ставит зависимости и отдельно запускает unit tests для `wms-service` и `consumer-service`.

**Почему это важно для полноты пункта.** Unit-слой не смешан с integration/E2E и не прячется внутри `docker compose up`. Это отдельный deterministic step с `JUnit XML`, поэтому ассистенту легко показать, что модульные тесты действительно существуют как самостоятельный слой проверки.

**Где смотреть.**

- `.github/workflows/smart-warehouse-ci.yml:21-50`
- `wms_service/tests/unit/test_event_publisher.py:1-67`
- `wms_service/tests/unit/test_http_metrics.py:1-44`
- `consumer_service/tests/unit/test_event_processor.py:1-179`

**Подпункт.** «integration tests — интеграционные тесты (см. п.2).»

**Что сделано.** В job `start-stack` после старта окружения запускается `docker compose --profile tests run --rm tests pytest ... integration`.

**Почему это важно для полноты пункта.** Integration tests запускаются уже после старта реальной инфраструктуры и не подменяются mock-объектами. Тем самым pipeline соответствует формулировке задания, где integration stage должен проверять реальное взаимодействие сервисов.

**Где смотреть.**

- `.github/workflows/smart-warehouse-ci.yml:64-72`
- `scripts/run_integration_tests.sh:1-10`

**Подпункт.** «Пайплайн падает при любой ошибке.»

**Что сделано.** Любой failing step останавливает job. `if: always()` используется только для артефактов и teardown.

**Где смотреть.**

- `.github/workflows/smart-warehouse-ci.yml:79-95`

**Подпункт.** «Конфигурация CI хранится в репозитории.»

**Что сделано.** Конфигурация workflow закоммичена в репозиторий.

**Где смотреть.**

- `.github/workflows/smart-warehouse-ci.yml:1-95`

**Подпункт.** «Логи пайплайна доступны и читаемы.»

**Что сделано.** GitHub Actions логирует каждый step отдельно, а в артефакты дополнительно сохраняются `docker-compose.log`, junit XML, k6 summary и ответы Prometheus/Alertmanager.

**Почему это закрывает требование про читаемые логи.** Логи не только "где-то есть в Actions UI", но и разложены по стадиям и артефактам. Это делает pipeline пригодным для разбора дефекта после падения и на практике намного сильнее минимального требования.

**Где смотреть.**

- `.github/workflows/smart-warehouse-ci.yml:82-91`
- `scripts/collect_artifacts.sh:10-16`

### 2.2 Пункт 2. Интеграционные тесты сервисов

**Оригинальная формулировка.** «Необходимо реализовать интеграционные тесты, которые проверяют взаимодействие между вашими сервисами.»

**Что сделано.** Интеграционные тесты живут в `tests/integration` и гоняются против реального compose-стека в контейнере `tests`.

**Почему пункт закрыт полностью.** Тесты не проверяют один handler в изоляции, а проходят через настоящие transport/storage boundaries: HTTP, Kafka, Cassandra, Prometheus. Для этого используется отдельный `tests` container, который подключён к той же сети и тем же сервисам, что и production-like стек из compose.

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

**Почему этот набор сценариев достаточен.** Он покрывает три разных класса интеграции: happy-path межсервисный поток, failure-path с DLQ и observability-path через `/metrics` + Prometheus scrape. То есть проверяется не один случай "событие дошло", а три независимых межкомпонентных контракта.

**Где смотреть.**

- `tests/integration/test_service_interactions.py:48-64`
- `tests/integration/test_service_interactions.py:66-107`
- `tests/integration/test_service_interactions.py:108-132`

**Подпункт.** «Тесты изолированы (не зависят от порядка выполнения других тестов).»

**Что сделано.** Перед каждым тестом Cassandra-таблицы очищаются через fixture `clean_warehouse_tables`, а сущности получают уникальные suffix.

**Почему это важно для оценки.** Именно это делает integration suite воспроизводимым на CI и локально. Без очистки таблиц и уникальных идентификаторов ассистент справедливо мог бы считать тесты flaky и зависимыми от порядка.

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

**Почему пункт закрыт полностью.** E2E здесь соответствует буквальной формулировке задания: начинается с публичного API, проходит через реальный event pipeline и заканчивается в конечном хранилище. Это не integration test, переименованный в E2E, а действительно сквозной пользовательский поток.

**Где смотреть.**

- `tests/e2e/test_full_flow.py:46-123`

**Подпункт.** «Тест запускает реальный пользовательский сценарий через ваш API.»

**Что сделано.** Тест делает последовательные `POST /api/v1/events` для:

- `PRODUCT_RECEIVED`
- `PRODUCT_RESERVED`
- `PRODUCT_MOVED`
- `ORDER_CREATED`
- `ORDER_COMPLETED`

**Почему этот сценарий предметно полноценный.** Он захватывает как базовые складские операции, так и заказную доменную логику. Благодаря этому E2E демонстрирует не просто "товар пришёл и записался", а реальную согласованность между остатками, резервами, перемещением и жизненным циклом заказа.

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

**Почему это важно для полноты пункта.** Проверка идёт не по одному ряду в БД, а сразу по нескольким конечным представлениям: zone-level inventory, totals-by-product и order state. Это существенно сильнее минимальной формулировки "запись создана" и доказывает корректность проекций после цепочки событий.

**Где смотреть.**

- `tests/e2e/test_full_flow.py:27-33`
- `tests/e2e/test_full_flow.py:101-117`

### 2.4 Пункт 4. Prometheus + базовые метрики сервисов

**Оригинальная формулировка.** «Каждый ваш сервис должен экспортировать метрики в Prometheus.»

**Что сделано.** Общая Prometheus-инструментация вынесена в `common/observability.py` и подключена в оба сервиса через единый middleware.

**Почему пункт закрыт полностью.** Важен не только сам факт наличия трёх метрик, но и способ их сбора. Здесь сделан единый middleware-слой, который автоматически записывает запросы для обоих сервисов в одинаковом формате и с одинаковым набором labels. Это соответствует промышленному подходу и снимает риск расхождения между сервисами.

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

**Почему это сильное доказательство.** Ассистент на защите может попросить показать не просто названия метрик, а именно labels `method`, `endpoint`, `status`, `error_type`. В этой работе labels проектируются осознанно: endpoint нормализуется, ошибки считаются отдельно, длительность уходит в histogram buckets, то есть метрики пригодны и для Grafana, и для SLI/SLO.

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

Блок `5-7` оценивает уже не наличие CI и тестов, а пригодность системы к наблюдаемой эксплуатации: можно ли понять состояние сервисов, инфраструктуры и поведения под нагрузкой. Ниже показано, что этот слой реализован как код, а не вручную "накликан" в UI.

### 3.1 Пункт 5. Grafana: дашборды сервисов

**Оригинальная формулировка.** «Необходимо создать дашборды в Grafana для визуализации метрик ваших сервисов.»

**Что сделано.** Создан сервисный дашборд `Smart Warehouse Services Observability`.

**Почему пункт закрыт полностью.** Dashboard не ограничивается одной красивой картинкой. Он закрывает обе стороны системы: входной HTTP producer (`wms-service`) и асинхронный consumer (`consumer-service`). При этом дашборд provisioned из JSON, а не создан вручную в локальной Grafana, что важно для воспроизводимости в CI и на защите.

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

**Почему это сильнее минимума.** Минимум требовал latency, errors, throughput и хотя бы четыре панели. Здесь сделано восемь панелей, причём добавлены два действительно системных показателя - processing latency и end-to-end delay. Это превращает dashboard из формального "графика по HTTP" в наблюдение за реальным asynchronous pipeline.

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

**Что сделано.** Создан `Smart Warehouse Infrastructure Observability`.

**Почему пункт закрыт полностью.** Инфраструктурный dashboard не дублирует сервисный. Он отвечает на другой вопрос: не "что ответил API", а "где bottleneck в платформе". Для этого объединены Kafka-exporter метрики и container-level metrics через cAdvisor.

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

**Почему это важно для оценки.** В требовании было прямо сказано, что способ экспорта метрик студент выбирает сам. Здесь выбор сделан осознанно: Kafka наблюдается через специализированный exporter, а контейнерные ресурсы - через cAdvisor. Это даёт объяснимый и реплицируемый observability stack вместо произвольного набора метрик.

**Где смотреть.**

- `docker-compose.yml:276-305`
- `prometheus/prometheus.yml:27-37`

### 3.3 Пункт 7. Нагрузочное тестирование, интегрированное в CI

**Оригинальная формулировка.** «Необходимо добавить нагрузочное тестирование в CI pipeline.»

**Что сделано.** Реализован `k6` сценарий и включён в workflow как отдельный stage после E2E.

**Почему пункт закрыт полностью.** Нагрузка не существует отдельно от CI и не запускается как локальная "демка". Она встроена в pipeline после проверки функциональной корректности, то есть система сначала доказывает корректность, а затем выдерживает controlled load и только после этого проходит SLI gates.

**Где смотреть.**

- `scripts/load/wms_events.js:1-87`
- `.github/workflows/smart-warehouse-ci.yml:76-80`

**Подпункт.** «Тест запускается из CI.»

**Что сделано.** Workflow вызывает `./scripts/run_load_tests.sh`.

**Где смотреть.**

- `.github/workflows/smart-warehouse-ci.yml:76-77`
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

**Почему эти thresholds достаточны.** Они покрывают две принципиально разные вещи: качество ответа основного API и доступность системы под нагрузкой. Из-за этого load stage служит не просто генератором трафика, а полноценным gate-механизмом.

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
- `.github/workflows/smart-warehouse-ci.yml:86-91`
- `artifacts/load/k6-summary.json`

---

## 4. Пункты на 8–10 баллов

Блок `8-10` закрыт не "отдельными бонусными фичами", а цельным quality contour: нагрузка запускается в том же прогоне, Prometheus автоматически оценивает SLI, alert rules хранятся как code, а результат сохраняется как evidence. Именно эта связка переводит работу из уровня "есть мониторинг" в уровень "система сама валит CI при системной деградации".

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

**Почему пункт закрыт полностью.** Требование здесь не просто "иметь и E2E, и load, и метрики", а прогнать их в едином CI-сценарии против одного и того же стенда. Именно так это и реализовано: один и тот же стек сначала обрабатывает integration/E2E, потом реальную нагрузку, затем по его Prometheus-метрикам принимается числовое решение о прохождении quality gate.

**Где смотреть.**

- `.github/workflows/smart-warehouse-ci.yml:52-95`

**Подпункт.** «Поднимает всю систему (docker-compose up).»

**Где смотреть.**

- `.github/workflows/smart-warehouse-ci.yml:64-65`

**Подпункт.** «Запускает нагрузку.»

**Где смотреть.**

- `.github/workflows/smart-warehouse-ci.yml:76-77`

**Подпункт.** «Параллельно собирает метрики из Prometheus.»

**Что сделано.** Метрики непрерывно собирает запущенный Prometheus, который скрейпит сервисы и exporters во время всего CI job.

**Где смотреть.**

- `prometheus/prometheus.yml:1-37`
- `.github/workflows/smart-warehouse-ci.yml:64-80`

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

**Почему это сильнее формального минимума.** В системе разведены `target` и `failure_threshold`. Это означает, что отчётность по SLO и жёсткий operational fail-fast не смешиваются: pipeline может отдельно зафиксировать промах по target и отдельно принять решение о реальном провале по failure threshold. Такой дизайн ближе к реальной эксплуатации, чем бинарное "выше/ниже одного порога".

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
- `.github/workflows/smart-warehouse-ci.yml:82-91`

### 4.2 Пункт 9. Prometheus alert rules как код

**Оригинальная формулировка.** «Необходимо определить alert rules для мониторинга проблем вашей системы.»

**Что сделано.** Alert rules хранятся в репозитории и подхватываются Prometheus как code.

**Почему пункт закрыт полностью.** Здесь есть все три обязательные части: сами правила как YAML в репозитории, Alertmanager в compose и отдельный demo-сценарий, который переводит алерты в `firing`. Без третьей части это был бы только "конфиг на бумаге"; здесь же срабатывание реально воспроизводится.

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

**Почему это сильнее минимума.** ТЗ просило минимум два класса проблем. В работе закрыто четыре обязательных класса (`error rate`, `latency`, `consumer lag`, `service down`) и добавлен пятый системный alert по event processing delay. Это делает набор правил не формальным, а действительно эксплуатационным.

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

**Почему пункт закрыт полностью.** Все три SLI относятся именно к системе в целом, а не к отдельному внутреннему методу. Первый описывает доступность публичного входа, второй - качество producer-path, третий - freshness асинхронной обработки и проекций. Вместе они покрывают вход, транспорт и конечную наблюдаемую полезность системы.

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
- `.github/workflows/smart-warehouse-ci.yml:79-80`

**Подпункт.** «SLI задокументированы в README: что измеряется, какой запрос к Prometheus, целевые значения, обоснование порогов.»

**Что сделано.** В `README.md` добавлен отдельный раздел `System-Level SLI, SLO and Failure Thresholds` со всеми четырьмя обязательными компонентами: что измеряется, PromQL, SLO, failure threshold и rationale.

**Почему это важно для максимальной оценки.** Здесь выполнено не только техническое условие наличия SLI, но и документирование инженерного смысла порогов. За счёт этого на защите можно объяснить не просто "какой threshold стоит", а почему он выбран именно таким и что operationally считается деградацией.

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

Проверка повторно проведена 2026-05-17 на текущем состоянии `smart-warehouse-platform`, уже после усиления отчёта и после исправлений observability / dashboard слоя.

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
- `smart-warehouse-cassandra-migrator` - `Exit 0`;
- `smart-warehouse-kafka-init` - `Exit 0`.

Дополнительно в текущем прогоне подтверждено:

- `smart-warehouse-cadvisor` находится в `Up (healthy)`;
- `smart-warehouse-prometheus` находится в `Up (healthy)`;
- `smart-warehouse-grafana` находится в `Up (healthy)`;
- `smart-warehouse-alertmanager` находится в `Up (healthy)`.

Дополнительная проверка:

```bash
docker exec smart-warehouse-cassandra-1 nodetool status
docker exec smart-warehouse-kafka-1 kafka-topics --describe --topic warehouse-events --bootstrap-server kafka-1:29092
```

Фактический результат:

- Cassandra cluster: `3` ноды `UN`;
- Kafka topic `warehouse-events`: `3` partitions, `RF=2`, `ISR healthy`.

Дополнительная observability-проверка текущего прогона:

```bash
docker exec smart-warehouse-prometheus wget -qO- 'http://localhost:9090/api/v1/query?query=up{job=~"wms-service|consumer-service|kafka-exporter|cadvisor"}'
docker exec smart-warehouse-cadvisor sh -lc "wget -qO- http://localhost:8080/metrics | grep -E 'container_cpu_usage_seconds_total|container_memory_working_set_bytes' | head -n 8"
```

Фактический результат:

- Prometheus видит `wms-service`, `consumer-service`, `kafka-exporter`, `cadvisor` со значением `up = 1`;
- cAdvisor реально экспортирует `container_cpu_usage_seconds_total` и `container_memory_working_set_bytes` с labels `container_label_com_docker_compose_project="smart-warehouse-platform"` и `container_label_com_docker_compose_service=...`;
- это означает, что инфраструктурный дашборд больше не опирается на пустые series и имеет реальные CPU/memory данные по Kafka и Cassandra контейнерам.

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

Фактический результат по текущему прогону:

- `http_reqs = 269`
- `http_req_failed = 0`
- `http_req_duration p95 = 144.17 ms`
- `checks_passes = 509`

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
- `wms_latency_p95_seconds = 0.072857`
- `event_end_to_end_delay_p95_seconds = 1.125`

Все три gate-проверки прошли:

- `target_passed = true`
- `gate_passed = true`

Дополнительная проверка dashboard-метрик после нагрузки:

```bash
docker exec smart-warehouse-prometheus wget -qO- 'http://localhost:9090/api/v1/query?query=sum(rate(http_requests_total{service="wms-service",endpoint="/api/v1/events"}[5m]))'
docker exec smart-warehouse-prometheus wget -qO- 'http://localhost:9090/api/v1/query?query=sum%20by%20(container_label_com_docker_compose_service)(rate(container_cpu_usage_seconds_total{container_label_com_docker_compose_project="smart-warehouse-platform",container_label_com_docker_compose_service=~"kafka-[12]|cassandra-[123]"}[5m]))'
docker exec smart-warehouse-prometheus wget -qO- 'http://localhost:9090/api/v1/query?query=sum%20by%20(container_label_com_docker_compose_service)(container_memory_working_set_bytes{container_label_com_docker_compose_project="smart-warehouse-platform",container_label_com_docker_compose_service=~"kafka-[12]|cassandra-[123]"})'
```

Фактический результат:

- `WMS throughput` после k6 показывает ненулевое значение `~0.836 req/s` на текущем окне;
- CPU usage query возвращает отдельные series для `kafka-1`, `kafka-2`, `cassandra-1`, `cassandra-2`, `cassandra-3`;
- memory working set query тоже возвращает отдельные series по тем же сервисам;
- это подтверждает, что и service dashboard, и infrastructure dashboard получают реальные данные из Prometheus в текущем состоянии репозитория.

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

- `.github/workflows/smart-warehouse-ci.yml:8-9`

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
