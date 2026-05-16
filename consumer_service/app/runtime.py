"""Composition root for the consumer service."""

from __future__ import annotations

from dataclasses import dataclass

from app.application.consumer_worker import ConsumerWorker
from app.application.processor import EventProcessor
from app.application.traffic_analytics import TrafficAnalyticsService
from app.infrastructure.cassandra_repository import WarehouseRepository
from app.infrastructure.dlq_producer import DLQProducer


@dataclass
class ConsumerRuntime:
    repository: WarehouseRepository
    dlq_producer: DLQProducer
    processor: EventProcessor
    worker: ConsumerWorker
    traffic_analytics: TrafficAnalyticsService

    @classmethod
    def build(cls) -> "ConsumerRuntime":
        repository = WarehouseRepository()
        dlq_producer = DLQProducer()
        processor = EventProcessor(repository)
        worker = ConsumerWorker(repository, processor, dlq_producer)
        traffic_analytics = TrafficAnalyticsService(repository)
        return cls(
            repository=repository,
            dlq_producer=dlq_producer,
            processor=processor,
            worker=worker,
            traffic_analytics=traffic_analytics,
        )
