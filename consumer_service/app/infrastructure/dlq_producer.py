"""Dead Letter Queue producer."""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from pathlib import Path

from confluent_kafka.avro import AvroProducer
from confluent_kafka.avro import loads as avro_loads

from app.config import settings
from app.domain.models import EventContext

logger = logging.getLogger(__name__)

_KEY_SCHEMA = avro_loads('"string"')


def _resolve_schema_dir() -> Path:
    for candidate in Path(__file__).resolve().parents:
        schema_dir = candidate / "schemas"
        if schema_dir.exists():
            return schema_dir
    raise FileNotFoundError("Unable to locate schemas directory")


def _load_schema():
    with open(_resolve_schema_dir() / "warehouse_dlq_event.avsc", encoding="utf-8") as schema_file:
        return avro_loads(schema_file.read())


class DLQProducer:
    def __init__(self) -> None:
        self._schema = _load_schema()
        self._producer = AvroProducer(
            {
                "bootstrap.servers": settings.kafka_brokers,
                "schema.registry.url": settings.schema_registry_url,
                "acks": "all",
                "retries": 5,
                "enable.idempotence": True,
            },
            default_key_schema=_KEY_SCHEMA,
            default_value_schema=self._schema,
        )

    def publish(self, context: EventContext, error_code: str, error_reason: str) -> None:
        payload = {
            "event_id": context.event_id,
            "event_type": context.event_type,
            "original_event_json": context.raw_json,
            "error_reason": error_reason,
            "error_code": error_code,
            "failed_at": int(datetime.now(UTC).timestamp() * 1000),
            "kafka_partition": context.metadata.partition,
            "kafka_offset": context.metadata.offset,
        }
        self._producer.produce(
            topic=settings.kafka_dlq_topic,
            key=context.event_id,
            value=payload,
            callback=self._delivery_callback,
        )
        self._producer.flush(timeout=10)

    @staticmethod
    def _delivery_callback(err, msg) -> None:
        if err is not None:
            logger.error("DLQ delivery failed: %s", err)
        else:
            logger.info(
                "DLQ event published: event_id=%s partition=%d offset=%d",
                msg.key(),
                msg.partition(),
                msg.offset(),
            )

    def close(self) -> None:
        self._producer.flush(timeout=10)
