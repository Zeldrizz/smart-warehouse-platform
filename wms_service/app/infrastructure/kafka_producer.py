"""Kafka producer adapter for warehouse events."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

import requests
from confluent_kafka.avro import AvroProducer
from confluent_kafka.avro import loads as avro_loads

from app.config import settings

logger = logging.getLogger(__name__)

_KEY_SCHEMA = avro_loads('"string"')


def _resolve_schema_dir() -> Path:
    for candidate in Path(__file__).resolve().parents:
        schema_dir = candidate / "schemas"
        if schema_dir.exists():
            return schema_dir
    raise FileNotFoundError("Unable to locate schemas directory")


def _load_schema(filename: str):
    with open(_resolve_schema_dir() / filename, encoding="utf-8") as schema_file:
        return avro_loads(schema_file.read())


class KafkaWarehouseProducer:
    """Low-level Kafka producer capable of writing both event schema versions."""

    def __init__(self) -> None:
        self._schemas = {
            "v1": _load_schema("warehouse_event_v1.avsc"),
            "v2": _load_schema("warehouse_event_v2.avsc"),
        }
        self._producer = AvroProducer(
            {
                "bootstrap.servers": settings.kafka_brokers,
                "schema.registry.url": settings.schema_registry_url,
                "acks": "all",
                "retries": 5,
                "retry.backoff.ms": 200,
                "delivery.timeout.ms": 30000,
                "request.timeout.ms": 10000,
                "enable.idempotence": True,
                "linger.ms": 25,
                "compression.type": "lz4",
            },
            default_key_schema=_KEY_SCHEMA,
        )
        logger.info("WMS Kafka producer connected to %s", settings.kafka_brokers)

    def publish(self, record: dict[str, Any], schema_version: str, routing_key: str) -> None:
        schema = self._schemas[schema_version]
        self._producer.produce(
            topic=settings.kafka_topic,
            key=routing_key,
            value=record,
            value_schema=schema,
            callback=self._delivery_callback,
        )
        self._producer.poll(0)

    def healthcheck(self) -> None:
        self._producer.list_topics(timeout=5)
        response = requests.get(f"{settings.schema_registry_url}/subjects", timeout=5)
        response.raise_for_status()

    def flush(self) -> None:
        self._producer.flush(timeout=10)

    @staticmethod
    def _delivery_callback(err, msg) -> None:
        if err is not None:
            logger.error("Kafka delivery failed: %s", err)
        else:
            logger.info(
                "Event published: routing_key=%s topic=%s partition=%d offset=%d",
                msg.key(),
                msg.topic(),
                msg.partition(),
                msg.offset(),
            )
