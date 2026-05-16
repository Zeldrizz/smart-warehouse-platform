"""Synthetic warehouse traffic generator for realistic real-time marketplace load."""

from __future__ import annotations

import asyncio
import logging
import random
import uuid
from collections import defaultdict
from dataclasses import dataclass
from datetime import UTC, datetime

from app.application.event_service import WarehouseEventPublisher
from app.config import settings
from app.domain.events import GeneratorSnapshot, WarehouseEventType

logger = logging.getLogger(__name__)


@dataclass
class SimulatedInventory:
    available: int = 0
    reserved_manual: int = 0
    reserved_order: int = 0
    supplier_id: str | None = None

    @property
    def reserved(self) -> int:
        return self.reserved_manual + self.reserved_order

    @property
    def total(self) -> int:
        return self.available + self.reserved


@dataclass(frozen=True)
class SimulatedOrderItem:
    product_id: str
    zone_id: str
    quantity: int


@dataclass
class SimulatedOrder:
    order_id: str
    items: list[SimulatedOrderItem]
    created_at: datetime
    routing_key: str


@dataclass
class GeneratorRuntimeState:
    phase: str = "disabled"
    paused: bool = False
    started_at: int | None = None
    live_events_published: int = 0
    last_event_id: str | None = None
    last_event_type: str | None = None
    last_occurred_at: int | None = None


class WarehouseTrafficGenerator:
    """Generates realistic real-time warehouse operations for a marketplace-like flow."""

    def __init__(self, publisher: WarehouseEventPublisher) -> None:
        self._publisher = publisher
        self._rng = random.Random(settings.generator_seed)
        self._pause_event = asyncio.Event()
        self._pause_event.set()
        self._state = GeneratorRuntimeState(phase="idle" if settings.generator_enabled else "disabled")
        self._task: asyncio.Task | None = None
        self._products = [f"MP-SKU-{i:04d}" for i in range(1, settings.generator_product_count + 1)]
        self._zones = {
            "ZONE-LIVE-A": 30000,
            "ZONE-LIVE-B": 30000,
            "ZONE-LIVE-C": 20000,
        }
        self._suppliers = [f"SUP-{i:03d}" for i in range(1, settings.generator_supplier_count + 1)]
        self._inventory: dict[str, dict[str, SimulatedInventory]] = defaultdict(dict)
        self._open_orders: dict[str, SimulatedOrder] = {}

    def start(self) -> None:
        if not settings.generator_enabled or self._task is not None:
            return
        self._task = asyncio.create_task(self.run(), name="warehouse-traffic-generator")

    async def stop(self) -> None:
        if self._task is None:
            return
        self._task.cancel()
        try:
            await self._task
        except asyncio.CancelledError:
            pass
        self._task = None
        self._state.phase = "stopped"

    def pause(self) -> None:
        self._state.paused = True
        self._pause_event.clear()

    def resume(self) -> None:
        self._state.paused = False
        self._pause_event.set()

    def snapshot(self) -> GeneratorSnapshot:
        return GeneratorSnapshot(
            enabled=settings.generator_enabled,
            phase=self._state.phase,
            paused=self._state.paused,
            started_at=self._state.started_at,
            live_events_published=self._state.live_events_published,
            last_event_id=self._state.last_event_id,
            last_event_type=self._state.last_event_type,
            last_occurred_at=self._state.last_occurred_at,
        )

    async def run(self) -> None:
        self._state.phase = "live"
        self._state.started_at = self._ts_ms(datetime.now(UTC))
        logger.info(
            "Warehouse generator started in live mode: %s sku, %s suppliers, %s events/min",
            settings.generator_product_count,
            settings.generator_supplier_count,
            settings.generator_live_events_per_minute,
        )
        while True:
            await self._pause_event.wait()
            live_event = self._generate_live_event(datetime.now(UTC))
            self._publish(live_event)
            self._state.live_events_published += 1
            base_delay = max(0.05, 60.0 / max(settings.generator_live_events_per_minute, 1))
            await asyncio.sleep(self._rng.uniform(base_delay * 0.5, base_delay * 1.5))

    def _publish(self, record: dict[str, object]) -> None:
        schema_version = "v1" if record["event_type"] == WarehouseEventType.PRODUCT_RECEIVED.value and record.get("supplier_id") is None else "v2"
        envelope = self._publisher.publish_generated(record=record, schema_version=schema_version)
        self._state.last_event_id = envelope.record["event_id"]
        self._state.last_event_type = envelope.record["event_type"]
        self._state.last_occurred_at = int(envelope.record["occurred_at"])

    def _generate_live_event(self, event_time: datetime) -> dict[str, object]:
        return self._generate_operation(event_time)

    def _generate_operation(self, event_time: datetime) -> dict[str, object]:
        for _ in range(20):
            operation = self._pick_operation(event_time)
            generated = operation(event_time)
            if generated is not None:
                return generated
        fallback = self._build_shipped_event(event_time) or self._build_count_event(event_time)
        if fallback is not None:
            return fallback
        return self._apply_count(
            product_id=self._products[0],
            zone_id="ZONE-LIVE-A",
            counted_quantity=0,
            event_time=event_time,
        )

    def _pick_operation(self, event_time: datetime):
        hour = event_time.hour
        load_ratio = self._global_load_ratio()
        if 6 <= hour < 10:
            weights = [
                (self._build_receive_event, 34),
                (self._build_move_event, 18),
                (self._build_count_event, 10),
                (self._build_order_created_event, 12),
                (self._build_reserved_event, 10),
                (self._build_shipped_event, 10),
                (self._build_order_completed_event, 6),
            ]
        elif 10 <= hour < 18:
            weights = [
                (self._build_order_created_event, 26),
                (self._build_shipped_event, 22),
                (self._build_move_event, 14),
                (self._build_reserved_event, 14),
                (self._build_release_event, 8),
                (self._build_order_completed_event, 12),
                (self._build_receive_event, 8),
            ]
        elif 18 <= hour < 23:
            weights = [
                (self._build_shipped_event, 22),
                (self._build_order_completed_event, 18),
                (self._build_release_event, 14),
                (self._build_move_event, 10),
                (self._build_count_event, 8),
                (self._build_receive_event, 10),
                (self._build_order_created_event, 18),
            ]
        else:
            weights = [
                (self._build_receive_event, 20),
                (self._build_move_event, 12),
                (self._build_count_event, 14),
                (self._build_shipped_event, 10),
                (self._build_order_created_event, 8),
                (self._build_order_completed_event, 6),
            ]
        if load_ratio > 0.72:
            weights = [
                (operation, max(2, weight - 18) if operation is self._build_receive_event else weight)
                for operation, weight in weights
            ]
            weights = [
                (operation, weight + 10 if operation in {self._build_shipped_event, self._build_order_completed_event} else weight)
                for operation, weight in weights
            ]
        elif load_ratio < 0.22:
            weights = [
                (operation, weight + 12 if operation is self._build_receive_event else max(2, weight - 4))
                for operation, weight in weights
            ]
        choices = [operation for operation, _ in weights]
        weights_only = [weight for _, weight in weights]
        return self._rng.choices(choices, weights=weights_only, k=1)[0]

    def _build_receive_event(self, event_time: datetime) -> dict[str, object]:
        product_id = self._rng.choice(self._products)
        zone_id = self._choose_zone_for_receiving()
        if zone_id is None:
            return None
        quantity = min(self._rng.randint(8, 28), self._zone_remaining_capacity(zone_id))
        if quantity <= 0:
            return None
        supplier_id = self._rng.choice(self._suppliers)
        return self._apply_receive(product_id, zone_id, quantity, event_time, supplier_id)

    def _build_shipped_event(self, event_time: datetime) -> dict[str, object] | None:
        choice = self._pick_inventory_with_available(minimum=8)
        if choice is None:
            return None
        product_id, zone_id, position = choice
        quantity = self._rng.randint(1, min(14, position.available))
        return self._apply_ship(product_id, zone_id, quantity, event_time)

    def _build_move_event(self, event_time: datetime) -> dict[str, object] | None:
        choice = self._pick_inventory_with_available(minimum=12)
        if choice is None:
            return None
        product_id, from_zone_id, position = choice
        other_zones = [zone_id for zone_id in self._zones if zone_id != from_zone_id]
        self._rng.shuffle(other_zones)
        for to_zone_id in other_zones:
            if self._zone_remaining_capacity(to_zone_id) <= 0:
                continue
            quantity = min(self._rng.randint(4, 20), position.available, self._zone_remaining_capacity(to_zone_id))
            if quantity > 0:
                return self._apply_move(product_id, from_zone_id, to_zone_id, quantity, event_time)
        return None

    def _build_reserved_event(self, event_time: datetime) -> dict[str, object] | None:
        choice = self._pick_inventory_with_available(minimum=5)
        if choice is None:
            return None
        product_id, zone_id, position = choice
        quantity = self._rng.randint(1, min(8, position.available))
        return self._apply_reserve(product_id, zone_id, quantity, event_time)

    def _build_release_event(self, event_time: datetime) -> dict[str, object] | None:
        choice = self._pick_inventory_with_reserved(minimum=2)
        if choice is None:
            return None
        product_id, zone_id, position = choice
        quantity = self._rng.randint(1, min(6, position.reserved_manual))
        return self._apply_release(product_id, zone_id, quantity, event_time)

    def _build_count_event(self, event_time: datetime) -> dict[str, object] | None:
        product_id = self._rng.choice(self._products)
        zone_id = self._rng.choice(list(self._zones))
        position = self._get_position(product_id, zone_id)
        delta = self._rng.randint(-10, 12)
        counted_quantity = max(0, position.available + delta)
        if counted_quantity + position.reserved > self._zones[zone_id]:
            return None
        return self._apply_count(product_id, zone_id, counted_quantity, event_time)

    def _build_order_created_event(self, event_time: datetime) -> dict[str, object] | None:
        items: list[SimulatedOrderItem] = []
        attempts = 0
        target_items = 1 if self._rng.random() < 0.72 else 2
        while len(items) < target_items and attempts < 12:
            attempts += 1
            choice = self._pick_inventory_with_available(minimum=4)
            if choice is None:
                break
            product_id, zone_id, position = choice
            quantity = self._rng.randint(1, min(5, position.available))
            candidate = SimulatedOrderItem(product_id=product_id, zone_id=zone_id, quantity=quantity)
            if candidate not in items:
                items.append(candidate)
        if not items:
            return None
        return self._apply_order_created(items, event_time)

    def _build_order_completed_event(self, event_time: datetime) -> dict[str, object] | None:
        if not self._open_orders:
            return None
        order = self._rng.choice(list(self._open_orders.values()))
        return self._apply_order_completed(order.order_id, event_time)

    def _apply_receive(
        self,
        product_id: str,
        zone_id: str,
        quantity: int,
        event_time: datetime,
        supplier_id: str,
    ) -> dict[str, object]:
        position = self._get_position(product_id, zone_id)
        quantity = min(quantity, self._zone_remaining_capacity(zone_id))
        if quantity <= 0:
            raise RuntimeError(f"Zone {zone_id} has no remaining capacity for receive event")
        position.available += quantity
        position.supplier_id = supplier_id
        return {
            "event_id": str(uuid.uuid4()),
            "event_type": WarehouseEventType.PRODUCT_RECEIVED.value,
            "occurred_at": self._ts_ms(event_time),
            "product_id": product_id,
            "zone_id": zone_id,
            "quantity": quantity,
            "supplier_id": supplier_id,
        }

    def _apply_ship(self, product_id: str, zone_id: str, quantity: int, event_time: datetime) -> dict[str, object]:
        position = self._get_position(product_id, zone_id)
        position.available -= quantity
        return {
            "event_id": str(uuid.uuid4()),
            "event_type": WarehouseEventType.PRODUCT_SHIPPED.value,
            "occurred_at": self._ts_ms(event_time),
            "product_id": product_id,
            "zone_id": zone_id,
            "quantity": quantity,
        }

    def _apply_move(
        self,
        product_id: str,
        from_zone_id: str,
        to_zone_id: str,
        quantity: int,
        event_time: datetime,
    ) -> dict[str, object]:
        source = self._get_position(product_id, from_zone_id)
        target = self._get_position(product_id, to_zone_id)
        source.available -= quantity
        target.available += quantity
        if target.supplier_id is None:
            target.supplier_id = source.supplier_id
        return {
            "event_id": str(uuid.uuid4()),
            "event_type": WarehouseEventType.PRODUCT_MOVED.value,
            "occurred_at": self._ts_ms(event_time),
            "product_id": product_id,
            "from_zone_id": from_zone_id,
            "to_zone_id": to_zone_id,
            "quantity": quantity,
        }

    def _apply_reserve(self, product_id: str, zone_id: str, quantity: int, event_time: datetime) -> dict[str, object]:
        position = self._get_position(product_id, zone_id)
        position.available -= quantity
        position.reserved_manual += quantity
        return {
            "event_id": str(uuid.uuid4()),
            "event_type": WarehouseEventType.PRODUCT_RESERVED.value,
            "occurred_at": self._ts_ms(event_time),
            "product_id": product_id,
            "zone_id": zone_id,
            "quantity": quantity,
        }

    def _apply_release(self, product_id: str, zone_id: str, quantity: int, event_time: datetime) -> dict[str, object]:
        position = self._get_position(product_id, zone_id)
        position.reserved_manual -= quantity
        position.available += quantity
        return {
            "event_id": str(uuid.uuid4()),
            "event_type": WarehouseEventType.PRODUCT_RELEASED.value,
            "occurred_at": self._ts_ms(event_time),
            "product_id": product_id,
            "zone_id": zone_id,
            "quantity": quantity,
        }

    def _apply_count(self, product_id: str, zone_id: str, counted_quantity: int, event_time: datetime) -> dict[str, object]:
        position = self._get_position(product_id, zone_id)
        position.available = counted_quantity
        return {
            "event_id": str(uuid.uuid4()),
            "event_type": WarehouseEventType.INVENTORY_COUNTED.value,
            "occurred_at": self._ts_ms(event_time),
            "product_id": product_id,
            "zone_id": zone_id,
            "counted_quantity": counted_quantity,
        }

    def _apply_order_created(self, items: list[SimulatedOrderItem], event_time: datetime) -> dict[str, object]:
        order_id = f"ORD-{event_time.strftime('%Y%m%d')}-{uuid.uuid4().hex[:8]}"
        for item in items:
            position = self._get_position(item.product_id, item.zone_id)
            position.available -= item.quantity
            position.reserved_order += item.quantity
        routing_key = items[0].product_id
        self._open_orders[order_id] = SimulatedOrder(
            order_id=order_id,
            items=items,
            created_at=event_time,
            routing_key=routing_key,
        )
        return {
            "event_id": str(uuid.uuid4()),
            "event_type": WarehouseEventType.ORDER_CREATED.value,
            "occurred_at": self._ts_ms(event_time),
            "order_id": order_id,
            "_routing_key": routing_key,
            "items": [
                {
                    "product_id": item.product_id,
                    "zone_id": item.zone_id,
                    "quantity": item.quantity,
                }
                for item in items
            ],
        }

    def _apply_order_completed(self, order_id: str, event_time: datetime) -> dict[str, object]:
        order = self._open_orders.pop(order_id)
        for item in order.items:
            position = self._get_position(item.product_id, item.zone_id)
            position.reserved_order -= item.quantity
        return {
            "event_id": str(uuid.uuid4()),
            "event_type": WarehouseEventType.ORDER_COMPLETED.value,
            "occurred_at": self._ts_ms(event_time),
            "order_id": order_id,
            "_routing_key": order.routing_key,
        }

    def _pick_inventory_with_available(self, minimum: int) -> tuple[str, str, SimulatedInventory] | None:
        candidates: list[tuple[str, str, SimulatedInventory]] = []
        for product_id, zones in self._inventory.items():
            for zone_id, position in zones.items():
                if position.available >= minimum:
                    candidates.append((product_id, zone_id, position))
        if not candidates:
            return None
        return self._rng.choice(candidates)

    def _pick_inventory_with_reserved(self, minimum: int) -> tuple[str, str, SimulatedInventory] | None:
        candidates: list[tuple[str, str, SimulatedInventory]] = []
        for product_id, zones in self._inventory.items():
            for zone_id, position in zones.items():
                if position.reserved_manual >= minimum:
                    candidates.append((product_id, zone_id, position))
        if not candidates:
            return None
        return self._rng.choice(candidates)

    def _choose_zone_for_receiving(self) -> str | None:
        scored = sorted(
            [zone_id for zone_id in self._zones if self._zone_remaining_capacity(zone_id) > 0],
            key=lambda zone_id: (
                self._zone_load_ratio(zone_id),
                zone_id != "ZONE-LIVE-A",
            ),
        )
        return scored[0] if scored else None

    def _zone_load_ratio(self, zone_id: str) -> float:
        return self._zone_total(zone_id) / self._zones[zone_id]

    def _zone_total(self, zone_id: str) -> int:
        total = 0
        for zones in self._inventory.values():
            if zone_id in zones:
                total += zones[zone_id].total
        return total

    def _zone_remaining_capacity(self, zone_id: str) -> int:
        return max(self._zones[zone_id] - self._zone_total(zone_id), 0)

    def _global_load_ratio(self) -> float:
        total_capacity = sum(self._zones.values())
        total_load = sum(self._zone_total(zone_id) for zone_id in self._zones)
        return total_load / total_capacity

    def _get_position(self, product_id: str, zone_id: str) -> SimulatedInventory:
        zone_positions = self._inventory[product_id]
        if zone_id not in zone_positions:
            zone_positions[zone_id] = SimulatedInventory()
        return zone_positions[zone_id]

    @staticmethod
    def _ts_ms(dt: datetime) -> int:
        return int(dt.timestamp() * 1000)
