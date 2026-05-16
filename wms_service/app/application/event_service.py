"""Application service for publishing manual and generated warehouse events."""

from __future__ import annotations

from typing import Any

from app.api.schemas import (
    InventoryCountedRequest,
    OrderCompletedRequest,
    OrderCreatedRequest,
    ProductMovedRequest,
    ProductReceivedRequest,
    ProductReleasedRequest,
    ProductReservedRequest,
    ProductShippedRequest,
    WarehouseEventRequest,
)
from app.domain.events import WarehouseEventEnvelope
from app.infrastructure.kafka_producer import KafkaWarehouseProducer


class WarehouseEventPublisher:
    def __init__(self, producer: KafkaWarehouseProducer) -> None:
        self._producer = producer

    def publish_request(self, request: WarehouseEventRequest) -> WarehouseEventEnvelope:
        envelope = self._to_envelope(request)
        self.publish_envelope(envelope)
        return envelope

    def publish_generated(self, record: dict[str, Any], schema_version: str = "v2") -> WarehouseEventEnvelope:
        routing_key = record.get("_routing_key") or record.get("product_id") or record.get("order_id") or record["event_id"]
        payload = {key: value for key, value in record.items() if not key.startswith("_")}
        envelope = WarehouseEventEnvelope(record=payload, schema_version=schema_version, routing_key=str(routing_key))
        self.publish_envelope(envelope)
        return envelope

    def publish_envelope(self, envelope: WarehouseEventEnvelope) -> None:
        self._producer.publish(
            record=envelope.record,
            schema_version=envelope.schema_version,
            routing_key=envelope.routing_key,
        )

    @staticmethod
    def _to_envelope(request: WarehouseEventRequest) -> WarehouseEventEnvelope:
        record: dict[str, Any] = {
            "event_id": request.event_id,
            "event_type": request.event_type,
            "occurred_at": request.occurred_at,
            "product_id": None,
            "zone_id": None,
            "quantity": None,
            "from_zone_id": None,
            "to_zone_id": None,
            "counted_quantity": None,
            "order_id": None,
            "items": None,
            "supplier_id": None,
        }

        schema_version = "v2"

        if isinstance(request, ProductReceivedRequest):
            record["product_id"] = request.product_id
            record["zone_id"] = request.zone_id
            record["quantity"] = request.quantity
            record["supplier_id"] = request.supplier_id
            schema_version = request.schema_version
        elif isinstance(request, ProductShippedRequest | ProductReservedRequest | ProductReleasedRequest):
            record["product_id"] = request.product_id
            record["zone_id"] = request.zone_id
            record["quantity"] = request.quantity
        elif isinstance(request, ProductMovedRequest):
            record["product_id"] = request.product_id
            record["from_zone_id"] = request.from_zone_id
            record["to_zone_id"] = request.to_zone_id
            record["quantity"] = request.quantity
        elif isinstance(request, InventoryCountedRequest):
            record["product_id"] = request.product_id
            record["zone_id"] = request.zone_id
            record["counted_quantity"] = request.counted_quantity
        elif isinstance(request, OrderCreatedRequest):
            record["order_id"] = request.order_id
            record["items"] = [item.model_dump(mode="python") for item in request.items]
        elif isinstance(request, OrderCompletedRequest):
            record["order_id"] = request.order_id

        if schema_version == "v1":
            record.pop("supplier_id", None)

        routing_key = record.get("product_id") or record.get("order_id") or record["event_id"]
        return WarehouseEventEnvelope(record=record, schema_version=schema_version, routing_key=routing_key)
