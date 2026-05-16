"""Unit tests for deterministic warehouse event processing."""

from __future__ import annotations

from datetime import UTC, datetime

from app.application.processor import EventProcessor
from app.domain.models import EventContext, InventoryKey, InventoryState, KafkaMetadata, OrderItemData, OrderState, ProductTotalsState, ZoneInfo


class FakeRepository:
    def __init__(self) -> None:
        self.processed: set[str] = set()
        self.inventory: dict[tuple[str, str], InventoryState] = {}
        self.totals: dict[str, ProductTotalsState] = {}
        self.orders: dict[str, OrderState] = {}
        self.zones = {
            "ZONE-A": ZoneInfo(zone_id="ZONE-A", zone_name="Zone A", capacity=1000),
            "ZONE-B": ZoneInfo(zone_id="ZONE-B", zone_name="Zone B", capacity=1000),
            "ZONE-C": ZoneInfo(zone_id="ZONE-C", zone_name="Zone C", capacity=1000),
        }
        self.apply_calls = 0

    def is_event_processed(self, event_id: str) -> bool:
        return event_id in self.processed

    def get_inventory(self, key: InventoryKey):
        return self.inventory.get((key.product_id, key.zone_id))

    def get_zone_inventory(self, zone_id: str):
        return [row for row in self.inventory.values() if row.zone_id == zone_id]

    def get_product_total(self, product_id: str):
        return self.totals.get(product_id)

    def get_order(self, order_id: str):
        return self.orders.get(order_id)

    def get_zone(self, zone_id: str):
        return self.zones.get(zone_id)

    def apply_state_change(self, inventory_rows, total_rows, order_state, context, outcome, error_code=None, error_reason=None) -> None:
        self.apply_calls += 1
        for row in inventory_rows:
            self.inventory[(row.product_id, row.zone_id)] = row
        for row in total_rows:
            self.totals[row.product_id] = row
        if order_state is not None:
            self.orders[order_state.order_id] = order_state
        self.processed.add(context.event_id)


def build_context(event_id: str, event_type: str, occurred_at: int, **event_fields) -> EventContext:
    event = {
        "event_id": event_id,
        "event_type": event_type,
        "occurred_at": occurred_at,
        **event_fields,
    }
    return EventContext(
        event=event,
        raw_json=str(event),
        event_id=event_id,
        event_type=event_type,
        occurred_at=occurred_at,
        schema_variant="v2",
        metadata=KafkaMetadata(partition=0, offset=1),
    )


def test_duplicate_event_is_ignored() -> None:
    repository = FakeRepository()
    repository.processed.add("dup-1")
    processor = EventProcessor(repository)

    result = processor.process(build_context(
        "dup-1",
        "PRODUCT_RECEIVED",
        1710000000000,
        product_id="SKU-1",
        zone_id="ZONE-A",
        quantity=10,
    ))

    assert result.action == "duplicate"
    assert result.outcome == "DUPLICATE"
    assert repository.apply_calls == 0


def test_stale_event_does_not_override_newer_inventory() -> None:
    repository = FakeRepository()
    repository.inventory[("SKU-1", "ZONE-A")] = InventoryState(
        product_id="SKU-1",
        zone_id="ZONE-A",
        available_quantity=50,
        reserved_quantity=0,
        last_event_ts=1710000005000,
        updated_at=datetime.now(UTC),
    )
    processor = EventProcessor(repository)

    result = processor.process(build_context(
        "stale-1",
        "PRODUCT_RECEIVED",
        1710000001000,
        product_id="SKU-1",
        zone_id="ZONE-A",
        quantity=10,
    ))

    current = repository.inventory[("SKU-1", "ZONE-A")]
    assert result.action == "stale"
    assert result.outcome == "STALE"
    assert current.available_quantity == 50
    assert repository.apply_calls == 0


def test_order_created_reserves_inventory() -> None:
    repository = FakeRepository()
    repository.inventory[("SKU-1", "ZONE-A")] = InventoryState(product_id="SKU-1", zone_id="ZONE-A", available_quantity=100)
    repository.totals["SKU-1"] = ProductTotalsState(product_id="SKU-1", total_available_quantity=100, total_reserved_quantity=0)
    processor = EventProcessor(repository)

    result = processor.process(build_context(
        "order-create-1",
        "ORDER_CREATED",
        1710000010000,
        order_id="ORDER-1",
        items=[{"product_id": "SKU-1", "zone_id": "ZONE-A", "quantity": 15}],
    ))

    inventory = repository.inventory[("SKU-1", "ZONE-A")]
    totals = repository.totals["SKU-1"]
    order = repository.orders["ORDER-1"]
    assert result.action == "applied"
    assert inventory.available_quantity == 85
    assert inventory.reserved_quantity == 15
    assert totals.total_available_quantity == 85
    assert totals.total_reserved_quantity == 15
    assert order.status == "CREATED"
    assert order.items == [OrderItemData(product_id="SKU-1", zone_id="ZONE-A", quantity=15)]


def test_order_completed_releases_reserved_inventory() -> None:
    repository = FakeRepository()
    repository.inventory[("SKU-1", "ZONE-A")] = InventoryState(
        product_id="SKU-1",
        zone_id="ZONE-A",
        available_quantity=85,
        reserved_quantity=15,
        last_event_ts=1710000010000,
    )
    repository.totals["SKU-1"] = ProductTotalsState(product_id="SKU-1", total_available_quantity=85, total_reserved_quantity=15)
    repository.orders["ORDER-1"] = OrderState(
        order_id="ORDER-1",
        status="CREATED",
        items=[OrderItemData(product_id="SKU-1", zone_id="ZONE-A", quantity=15)],
        created_at=datetime.now(UTC),
        updated_at=datetime.now(UTC),
        last_event_ts=1710000010000,
    )
    processor = EventProcessor(repository)

    result = processor.process(build_context(
        "order-complete-1",
        "ORDER_COMPLETED",
        1710000015000,
        order_id="ORDER-1",
    ))

    inventory = repository.inventory[("SKU-1", "ZONE-A")]
    totals = repository.totals["SKU-1"]
    order = repository.orders["ORDER-1"]
    assert result.action == "applied"
    assert inventory.available_quantity == 85
    assert inventory.reserved_quantity == 0
    assert totals.total_available_quantity == 85
    assert totals.total_reserved_quantity == 0
    assert order.status == "COMPLETED"
