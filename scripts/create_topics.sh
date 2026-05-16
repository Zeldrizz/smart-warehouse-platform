#!/bin/bash
set -euo pipefail

KAFKA_BROKERS="${KAFKA_BROKERS:-kafka-1:29092,kafka-2:29093}"
SCHEMA_REGISTRY_URL="${SCHEMA_REGISTRY_URL:-http://schema-registry:8081}"
EVENT_TOPIC="${EVENT_TOPIC:-warehouse-events}"
DLQ_TOPIC="${DLQ_TOPIC:-warehouse-events-dlq}"

echo "=== Waiting for Kafka brokers ==="
cub kafka-ready -b "$KAFKA_BROKERS" 2 60

echo "=== Creating Kafka topics ==="
kafka-topics --create \
  --if-not-exists \
  --bootstrap-server "$KAFKA_BROKERS" \
  --topic "$EVENT_TOPIC" \
  --partitions 3 \
  --replication-factor 2 \
  --config min.insync.replicas=1 \
  --config retention.ms=604800000

kafka-topics --create \
  --if-not-exists \
  --bootstrap-server "$KAFKA_BROKERS" \
  --topic "$DLQ_TOPIC" \
  --partitions 3 \
  --replication-factor 2 \
  --config min.insync.replicas=1 \
  --config retention.ms=604800000

echo "=== Topics created ==="
kafka-topics --describe --bootstrap-server "$KAFKA_BROKERS" --topic "$EVENT_TOPIC"
kafka-topics --describe --bootstrap-server "$KAFKA_BROKERS" --topic "$DLQ_TOPIC"

register_schema() {
  local subject="$1"
  local schema_path="$2"
  local schema
  schema=$(sed 's/"/\\"/g' "$schema_path" | tr -d '\n')
  curl -fsS -X POST "${SCHEMA_REGISTRY_URL}/subjects/${subject}/versions" \
    -H "Content-Type: application/vnd.schemaregistry.v1+json" \
    -d "{\"schemaType\":\"AVRO\",\"schema\":\"${schema}\"}" >/tmp/schema-register-response.json
  cat /tmp/schema-register-response.json
  echo ""
}

echo "=== Registering V1 warehouse schema ==="
register_schema "${EVENT_TOPIC}-value" /schemas/warehouse_event_v1.avsc

echo "=== Setting BACKWARD compatibility for ${EVENT_TOPIC}-value ==="
curl -fsS -X PUT "${SCHEMA_REGISTRY_URL}/config/${EVENT_TOPIC}-value" \
  -H "Content-Type: application/vnd.schemaregistry.v1+json" \
  -d '{"compatibility":"BACKWARD"}'
echo ""

echo "=== Registering V2 warehouse schema ==="
register_schema "${EVENT_TOPIC}-value" /schemas/warehouse_event_v2.avsc

echo "=== Registering DLQ schema ==="
register_schema "${DLQ_TOPIC}-value" /schemas/warehouse_dlq_event.avsc

echo "=== Schema versions ==="
curl -fsS "${SCHEMA_REGISTRY_URL}/subjects/${EVENT_TOPIC}-value/versions/latest"
echo ""
curl -fsS "${SCHEMA_REGISTRY_URL}/subjects/${DLQ_TOPIC}-value/versions/latest"
echo ""

echo "=== Kafka init complete ==="
