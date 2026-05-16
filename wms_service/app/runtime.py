"""Composition root for the WMS service runtime."""

from __future__ import annotations

from dataclasses import dataclass

from app.application.event_service import WarehouseEventPublisher
from app.application.generator import WarehouseTrafficGenerator
from app.infrastructure.kafka_producer import KafkaWarehouseProducer


@dataclass
class WMSRuntime:
    producer: KafkaWarehouseProducer
    publisher: WarehouseEventPublisher
    generator: WarehouseTrafficGenerator

    @classmethod
    def build(cls) -> "WMSRuntime":
        producer = KafkaWarehouseProducer()
        publisher = WarehouseEventPublisher(producer)
        generator = WarehouseTrafficGenerator(publisher)
        return cls(producer=producer, publisher=publisher, generator=generator)
