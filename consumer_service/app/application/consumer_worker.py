"""Background Kafka consumer loop."""

from __future__ import annotations

import json
import logging
import threading
import time
from typing import Any

from confluent_kafka import KafkaException, TopicPartition
from confluent_kafka.avro import AvroConsumer

from app.config import settings
from app.domain.models import EventContext, KafkaMetadata
from app.infrastructure.cassandra_repository import WarehouseRepository
from app.infrastructure.dlq_producer import DLQProducer
from app.metrics import (
    consumer_lag,
    dlq_events_total,
    event_end_to_end_delay_seconds,
    event_processing_duration_seconds,
    events_processed_total,
)
from app.application.processor import EventProcessor

logger = logging.getLogger(__name__)


class ConsumerWorker:
    def __init__(
        self,
        repository: WarehouseRepository,
        processor: EventProcessor,
        dlq_producer: DLQProducer,
    ) -> None:
        self._repository = repository
        self._processor = processor
        self._dlq_producer = dlq_producer
        self._stop_event = threading.Event()
        self._thread: threading.Thread | None = None
        self._consumer: AvroConsumer | None = None
        self._running = False
        self._kafka_ok = False
        self._cassandra_ok = False
        self._paused = False
        self._last_lag_refresh = 0.0
        self._last_healthcheck = 0.0

    def start(self) -> None:
        if self._thread is not None:
            return
        self._thread = threading.Thread(target=self._run, name="warehouse-consumer", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop_event.set()
        if self._consumer is not None:
            try:
                self._consumer.close()
            except Exception:
                pass
        if self._thread is not None:
            self._thread.join(timeout=10)

    def status(self) -> dict[str, Any]:
        return {
            "running": self._running,
            "kafka_ok": self._kafka_ok,
            "cassandra_ok": self._cassandra_ok,
            "paused": self._paused,
        }

    def pause(self) -> None:
        self._paused = True
        if self._consumer is not None:
            partitions = self._consumer.assignment()
            if partitions:
                self._consumer.pause(partitions)

    def resume(self) -> None:
        self._paused = False
        if self._consumer is not None:
            partitions = self._consumer.assignment()
            if partitions:
                self._consumer.resume(partitions)

    def _build_consumer(self) -> AvroConsumer:
        consumer = AvroConsumer(
            {
                "bootstrap.servers": settings.kafka_brokers,
                "group.id": settings.kafka_consumer_group,
                "enable.auto.commit": False,
                "auto.offset.reset": "earliest",
                "schema.registry.url": settings.schema_registry_url,
                "session.timeout.ms": 45000,
                "max.poll.interval.ms": 300000,
            }
        )
        consumer.subscribe([settings.kafka_topic])
        return consumer

    def _run(self) -> None:
        self._consumer = self._build_consumer()
        self._running = True
        logger.info("Consumer loop started for topic=%s group=%s", settings.kafka_topic, settings.kafka_consumer_group)
        try:
            while not self._stop_event.is_set():
                try:
                    self._refresh_health()
                    self._refresh_lag()
                    if self._paused:
                        if self._consumer.assignment():
                            self._consumer.pause(self._consumer.assignment())
                        self._consumer.poll(0.1)
                        self._kafka_ok = True
                        time.sleep(0.2)
                        continue
                    msg = self._consumer.poll(settings.consumer_poll_timeout)
                    self._kafka_ok = True
                    if msg is None:
                        continue
                    if msg.error():
                        raise KafkaException(msg.error())

                    context = self._build_context(msg.value(), msg.partition(), msg.offset())
                    started_at = time.monotonic()
                    result = self._processor.process(context)

                    if result.action == "stale":
                        self._repository.apply_state_change([], [], None, context, outcome="STALE", error_code=result.error_code, error_reason=result.error_reason)
                    elif result.action == "dlq":
                        self._dlq_producer.publish(context, result.error_code or "DLQ_ERROR", result.error_reason or "Unknown error")
                        dlq_events_total.labels(result.error_code or "DLQ_ERROR").inc()
                        self._repository.apply_state_change([], [], None, context, outcome="DLQ", error_code=result.error_code, error_reason=result.error_reason)

                    self._consumer.commit(message=msg, asynchronous=False)
                    elapsed = time.monotonic() - started_at
                    events_processed_total.labels(context.event_type).inc()
                    event_processing_duration_seconds.observe(elapsed)
                    wall_delay_seconds = max((time.time() * 1000 - context.occurred_at) / 1000, 0.0)
                    event_end_to_end_delay_seconds.labels(context.event_type).observe(wall_delay_seconds)
                    logger.info(
                        "Event handled: event_id=%s event_type=%s partition=%s offset=%s schema_variant=%s outcome=%s",
                        context.event_id,
                        context.event_type,
                        context.metadata.partition,
                        context.metadata.offset,
                        context.schema_variant,
                        result.outcome,
                    )
                except Exception as exc:
                    self._kafka_ok = False
                    logger.exception("Consumer loop error: %s", exc)
                    time.sleep(2)
        finally:
            self._running = False
            self._kafka_ok = False
            if self._consumer is not None:
                self._consumer.close()
            logger.info("Consumer loop stopped")

    def _build_context(self, event: dict[str, Any], partition: int, offset: int) -> EventContext:
        event_id = event["event_id"]
        event_type = event["event_type"]
        occurred_at = int(event["occurred_at"])
        schema_variant = "v2" if "supplier_id" in event else "v1"
        return EventContext(
            event=event,
            raw_json=json.dumps(event, sort_keys=True),
            event_id=event_id,
            event_type=event_type,
            occurred_at=occurred_at,
            schema_variant=schema_variant,
            metadata=KafkaMetadata(partition=partition, offset=offset),
        )

    def _refresh_lag(self) -> None:
        if not self._consumer or (time.monotonic() - self._last_lag_refresh) < settings.lag_refresh_seconds:
            return
        self._last_lag_refresh = time.monotonic()
        partitions = self._consumer.assignment()
        if not partitions:
            metadata = self._consumer.list_topics(settings.kafka_topic, timeout=5)
            topic = metadata.topics.get(settings.kafka_topic)
            if topic:
                partitions = [TopicPartition(settings.kafka_topic, partition_id) for partition_id in topic.partitions]
        if not partitions:
            return
        committed = {
            tp.partition: committed_tp.offset
            for tp, committed_tp in zip(partitions, self._consumer.committed(partitions, timeout=5))
        }
        for tp in partitions:
            low, high = self._consumer.get_watermark_offsets(tp, cached=False)
            committed_offset = committed.get(tp.partition, -1)
            lag = max(high - committed_offset, 0) if committed_offset >= 0 else high
            consumer_lag.labels(str(tp.partition)).set(lag)

    def _refresh_health(self) -> None:
        if (time.monotonic() - self._last_healthcheck) < settings.healthcheck_seconds:
            return
        self._last_healthcheck = time.monotonic()
        self._cassandra_ok = self._repository.healthcheck()
