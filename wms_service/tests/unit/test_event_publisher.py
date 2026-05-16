"""Unit tests for request-to-event mapping in the WMS publisher."""

from __future__ import annotations

from app.api.schemas import OrderCreatedRequest, OrderItemRequest, ProductReceivedRequest
from app.application.event_service import WarehouseEventPublisher


class RecordingProducer:
    def __init__(self) -> None:
        self.calls: list[dict] = []

    def publish(self, record: dict, schema_version: str, routing_key: str) -> None:
        self.calls.append({
            "record": record,
            "schema_version": schema_version,
            "routing_key": routing_key,
        })


def test_product_received_v1_mapping_strips_supplier_id() -> None:
    producer = RecordingProducer()
    publisher = WarehouseEventPublisher(producer)
    request = ProductReceivedRequest(
        event_id="evt-1",
        event_type="PRODUCT_RECEIVED",
        occurred_at=1710000000000,
        product_id="SKU-1",
        zone_id="ZONE-A",
        quantity=5,
        supplier_id="SUP-1",
        schema_version="v1",
    )

    envelope = publisher.publish_request(request)

    assert envelope.schema_version == "v1"
    assert envelope.routing_key == "SKU-1"
    assert "supplier_id" not in envelope.record
    assert producer.calls[0]["schema_version"] == "v1"
    assert producer.calls[0]["routing_key"] == "SKU-1"
    assert producer.calls[0]["record"]["event_id"] == "evt-1"


def test_order_created_mapping_preserves_items_and_order_routing_key() -> None:
    producer = RecordingProducer()
    publisher = WarehouseEventPublisher(producer)
    request = OrderCreatedRequest(
        event_id="evt-order",
        event_type="ORDER_CREATED",
        occurred_at=1710000001000,
        order_id="ORDER-1",
        items=[
            OrderItemRequest(product_id="SKU-1", zone_id="ZONE-A", quantity=2),
            OrderItemRequest(product_id="SKU-2", zone_id="ZONE-B", quantity=3),
        ],
    )

    envelope = publisher.publish_request(request)

    assert envelope.routing_key == "ORDER-1"
    assert envelope.record["order_id"] == "ORDER-1"
    assert envelope.record["items"] == [
        {"product_id": "SKU-1", "zone_id": "ZONE-A", "quantity": 2},
        {"product_id": "SKU-2", "zone_id": "ZONE-B", "quantity": 3},
    ]
    assert producer.calls[0]["record"]["items"][1]["product_id"] == "SKU-2"
