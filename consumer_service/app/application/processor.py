"""Business logic for applying warehouse events to Cassandra state."""

from __future__ import annotations

from collections import defaultdict
from dataclasses import replace
from datetime import UTC, datetime

from app.domain.models import (
    DomainValidationError,
    EventContext,
    InventoryKey,
    InventoryState,
    OrderItemData,
    OrderState,
    ProcessResult,
    ProductTotalsState,
)
from app.infrastructure.cassandra_repository import WarehouseRepository


def empty_inventory(key: InventoryKey) -> InventoryState:
    return InventoryState(product_id=key.product_id, zone_id=key.zone_id)


class EventProcessor:
    def __init__(self, repository: WarehouseRepository) -> None:
        self._repository = repository

    def process(self, context: EventContext) -> ProcessResult:
        event = context.event
        event_type = context.event_type

        if self._repository.is_event_processed(context.event_id):
            return ProcessResult(action="duplicate", outcome="DUPLICATE")

        try:
            if event_type == "PRODUCT_RECEIVED":
                return self._process_product_received(context)
            if event_type == "PRODUCT_SHIPPED":
                return self._process_product_shipped(context)
            if event_type == "PRODUCT_MOVED":
                return self._process_product_moved(context)
            if event_type == "PRODUCT_RESERVED":
                return self._process_product_reserved(context)
            if event_type == "PRODUCT_RELEASED":
                return self._process_product_released(context)
            if event_type == "INVENTORY_COUNTED":
                return self._process_inventory_counted(context)
            if event_type == "ORDER_CREATED":
                return self._process_order_created(context)
            if event_type == "ORDER_COMPLETED":
                return self._process_order_completed(context)
            raise DomainValidationError("UNKNOWN_EVENT_TYPE", f"Unsupported event type: {event_type}")
        except DomainValidationError as exc:
            return ProcessResult(
                action="dlq",
                outcome="DLQ",
                error_code=exc.error_code,
                error_reason=exc.message,
            )

    def _process_product_received(self, context: EventContext) -> ProcessResult:
        event = context.event
        quantity = self._require_positive(event.get("quantity"), "quantity")
        key = InventoryKey(
            product_id=self._require_text(event.get("product_id"), "product_id"),
            zone_id=self._require_text(event.get("zone_id"), "zone_id"),
        )
        current = self._get_inventory(key)
        if self._is_stale(context.occurred_at, [current.last_event_ts]):
            return ProcessResult(action="stale", outcome="STALE", error_code="STALE_EVENT", error_reason="Older event ignored")
        updated = replace(
            current,
            available_quantity=current.available_quantity + quantity,
            last_event_ts=context.occurred_at,
            supplier_id=event.get("supplier_id"),
            updated_at=datetime.now(UTC),
        )
        self._validate_zone_capacities({key.zone_id: [updated]}, {key.zone_id: [current]})
        totals = self._build_totals([current], [updated], context.occurred_at)
        self._repository.apply_state_change([updated], totals, None, context, outcome="APPLIED")
        return ProcessResult(action="applied", outcome="APPLIED")

    def _process_product_shipped(self, context: EventContext) -> ProcessResult:
        event = context.event
        quantity = self._require_positive(event.get("quantity"), "quantity")
        key = InventoryKey(
            product_id=self._require_text(event.get("product_id"), "product_id"),
            zone_id=self._require_text(event.get("zone_id"), "zone_id"),
        )
        current = self._get_inventory(key)
        if self._is_stale(context.occurred_at, [current.last_event_ts]):
            return ProcessResult(action="stale", outcome="STALE", error_code="STALE_EVENT", error_reason="Older event ignored")
        if current.available_quantity < quantity:
            raise DomainValidationError("INSUFFICIENT_AVAILABLE", f"Available stock {current.available_quantity} is smaller than requested shipment {quantity}")
        updated = replace(
            current,
            available_quantity=current.available_quantity - quantity,
            last_event_ts=context.occurred_at,
            updated_at=datetime.now(UTC),
        )
        self._validate_zone_capacities({key.zone_id: [updated]}, {key.zone_id: [current]})
        totals = self._build_totals([current], [updated], context.occurred_at)
        self._repository.apply_state_change([updated], totals, None, context, outcome="APPLIED")
        return ProcessResult(action="applied", outcome="APPLIED")

    def _process_product_reserved(self, context: EventContext) -> ProcessResult:
        event = context.event
        quantity = self._require_positive(event.get("quantity"), "quantity")
        key = InventoryKey(
            product_id=self._require_text(event.get("product_id"), "product_id"),
            zone_id=self._require_text(event.get("zone_id"), "zone_id"),
        )
        current = self._get_inventory(key)
        if self._is_stale(context.occurred_at, [current.last_event_ts]):
            return ProcessResult(action="stale", outcome="STALE", error_code="STALE_EVENT", error_reason="Older event ignored")
        if current.available_quantity < quantity:
            raise DomainValidationError("INSUFFICIENT_AVAILABLE", f"Available stock {current.available_quantity} is smaller than requested reserve {quantity}")
        updated = replace(
            current,
            available_quantity=current.available_quantity - quantity,
            reserved_quantity=current.reserved_quantity + quantity,
            last_event_ts=context.occurred_at,
            updated_at=datetime.now(UTC),
        )
        self._validate_zone_capacities({key.zone_id: [updated]}, {key.zone_id: [current]})
        totals = self._build_totals([current], [updated], context.occurred_at)
        self._repository.apply_state_change([updated], totals, None, context, outcome="APPLIED")
        return ProcessResult(action="applied", outcome="APPLIED")

    def _process_product_released(self, context: EventContext) -> ProcessResult:
        event = context.event
        quantity = self._require_positive(event.get("quantity"), "quantity")
        key = InventoryKey(
            product_id=self._require_text(event.get("product_id"), "product_id"),
            zone_id=self._require_text(event.get("zone_id"), "zone_id"),
        )
        current = self._get_inventory(key)
        if self._is_stale(context.occurred_at, [current.last_event_ts]):
            return ProcessResult(action="stale", outcome="STALE", error_code="STALE_EVENT", error_reason="Older event ignored")
        if current.reserved_quantity < quantity:
            raise DomainValidationError("INSUFFICIENT_RESERVED", f"Reserved stock {current.reserved_quantity} is smaller than requested release {quantity}")
        updated = replace(
            current,
            available_quantity=current.available_quantity + quantity,
            reserved_quantity=current.reserved_quantity - quantity,
            last_event_ts=context.occurred_at,
            updated_at=datetime.now(UTC),
        )
        self._validate_zone_capacities({key.zone_id: [updated]}, {key.zone_id: [current]})
        totals = self._build_totals([current], [updated], context.occurred_at)
        self._repository.apply_state_change([updated], totals, None, context, outcome="APPLIED")
        return ProcessResult(action="applied", outcome="APPLIED")

    def _process_inventory_counted(self, context: EventContext) -> ProcessResult:
        event = context.event
        counted_quantity = self._require_non_negative(event.get("counted_quantity"), "counted_quantity")
        key = InventoryKey(
            product_id=self._require_text(event.get("product_id"), "product_id"),
            zone_id=self._require_text(event.get("zone_id"), "zone_id"),
        )
        current = self._get_inventory(key)
        if self._is_stale(context.occurred_at, [current.last_event_ts]):
            return ProcessResult(action="stale", outcome="STALE", error_code="STALE_EVENT", error_reason="Older event ignored")
        updated = replace(
            current,
            available_quantity=counted_quantity,
            last_event_ts=context.occurred_at,
            updated_at=datetime.now(UTC),
        )
        self._validate_zone_capacities({key.zone_id: [updated]}, {key.zone_id: [current]})
        totals = self._build_totals([current], [updated], context.occurred_at)
        self._repository.apply_state_change([updated], totals, None, context, outcome="APPLIED")
        return ProcessResult(action="applied", outcome="APPLIED")

    def _process_product_moved(self, context: EventContext) -> ProcessResult:
        event = context.event
        quantity = self._require_positive(event.get("quantity"), "quantity")
        product_id = self._require_text(event.get("product_id"), "product_id")
        from_zone_id = self._require_text(event.get("from_zone_id"), "from_zone_id")
        to_zone_id = self._require_text(event.get("to_zone_id"), "to_zone_id")
        if from_zone_id == to_zone_id:
            raise DomainValidationError("INVALID_MOVE", "Source and target zone must be different")

        source_key = InventoryKey(product_id=product_id, zone_id=from_zone_id)
        target_key = InventoryKey(product_id=product_id, zone_id=to_zone_id)
        source = self._get_inventory(source_key)
        target = self._get_inventory(target_key)
        if self._is_stale(context.occurred_at, [source.last_event_ts, target.last_event_ts]):
            return ProcessResult(action="stale", outcome="STALE", error_code="STALE_EVENT", error_reason="Older event ignored")
        if source.available_quantity < quantity:
            raise DomainValidationError("INSUFFICIENT_AVAILABLE", f"Available stock {source.available_quantity} is smaller than requested move {quantity}")

        updated_source = replace(
            source,
            available_quantity=source.available_quantity - quantity,
            last_event_ts=context.occurred_at,
            updated_at=datetime.now(UTC),
        )
        updated_target = replace(
            target,
            available_quantity=target.available_quantity + quantity,
            last_event_ts=context.occurred_at,
            supplier_id=target.supplier_id or source.supplier_id,
            updated_at=datetime.now(UTC),
        )
        self._validate_zone_capacities(
            {
                from_zone_id: [updated_source],
                to_zone_id: [updated_target],
            },
            {
                from_zone_id: [source],
                to_zone_id: [target],
            },
        )
        totals = self._build_totals([source, target], [updated_source, updated_target], context.occurred_at)
        self._repository.apply_state_change([updated_source, updated_target], totals, None, context, outcome="APPLIED")
        return ProcessResult(action="applied", outcome="APPLIED")

    def _process_order_created(self, context: EventContext) -> ProcessResult:
        event = context.event
        order_id = self._require_text(event.get("order_id"), "order_id")
        items = self._normalize_items(event.get("items"))
        existing_order = self._repository.get_order(order_id)
        if existing_order is not None:
            if context.occurred_at < existing_order.last_event_ts:
                return ProcessResult(action="stale", outcome="STALE", error_code="STALE_EVENT", error_reason="Older event ignored")
            raise DomainValidationError("ORDER_ALREADY_EXISTS", f"Order {order_id} already exists")

        current_rows, updated_rows = self._reserve_order_items(items, context.occurred_at)
        totals = self._build_totals(current_rows, updated_rows, context.occurred_at)
        now = datetime.now(UTC)
        order_state = OrderState(
            order_id=order_id,
            status="CREATED",
            items=items,
            created_at=now,
            updated_at=now,
            last_event_ts=context.occurred_at,
        )
        self._repository.apply_state_change(updated_rows, totals, order_state, context, outcome="APPLIED")
        return ProcessResult(action="applied", outcome="APPLIED")

    def _process_order_completed(self, context: EventContext) -> ProcessResult:
        order_id = self._require_text(context.event.get("order_id"), "order_id")
        order_state = self._repository.get_order(order_id)
        if order_state is None:
            raise DomainValidationError("ORDER_NOT_FOUND", f"Order {order_id} does not exist")
        if context.occurred_at < order_state.last_event_ts:
            return ProcessResult(action="stale", outcome="STALE", error_code="STALE_EVENT", error_reason="Older event ignored")
        if order_state.status != "CREATED":
            raise DomainValidationError("ORDER_NOT_COMPLETABLE", f"Order {order_id} has status {order_state.status}")

        current_rows: list[InventoryState] = []
        updated_rows: list[InventoryState] = []
        grouped = self._group_items(order_state.items)
        for key, quantity in grouped.items():
            current = self._get_inventory(key)
            if current.reserved_quantity < quantity:
                raise DomainValidationError("INSUFFICIENT_RESERVED", f"Reserved stock {current.reserved_quantity} is smaller than shipment {quantity}")
            current_rows.append(current)
            updated_rows.append(
                replace(
                    current,
                    reserved_quantity=current.reserved_quantity - quantity,
                    last_event_ts=context.occurred_at,
                    updated_at=datetime.now(UTC),
                )
            )
        self._validate_zone_capacities(self._rows_by_zone(updated_rows), self._rows_by_zone(current_rows))
        totals = self._build_totals(current_rows, updated_rows, context.occurred_at)
        completed_order = replace(
            order_state,
            status="COMPLETED",
            updated_at=datetime.now(UTC),
            last_event_ts=context.occurred_at,
        )
        self._repository.apply_state_change(updated_rows, totals, completed_order, context, outcome="APPLIED")
        return ProcessResult(action="applied", outcome="APPLIED")

    def _reserve_order_items(self, items: list[OrderItemData], occurred_at: int) -> tuple[list[InventoryState], list[InventoryState]]:
        current_rows: list[InventoryState] = []
        updated_rows: list[InventoryState] = []
        grouped = self._group_items(items)
        for key, quantity in grouped.items():
            current = self._get_inventory(key)
            if current.available_quantity < quantity:
                raise DomainValidationError("INSUFFICIENT_AVAILABLE", f"Available stock {current.available_quantity} is smaller than requested reserve {quantity}")
            current_rows.append(current)
            updated_rows.append(
                replace(
                    current,
                    available_quantity=current.available_quantity - quantity,
                    reserved_quantity=current.reserved_quantity + quantity,
                    last_event_ts=occurred_at,
                    updated_at=datetime.now(UTC),
                )
            )
        self._validate_zone_capacities(self._rows_by_zone(updated_rows), self._rows_by_zone(current_rows))
        return current_rows, updated_rows

    def _group_items(self, items: list[OrderItemData]) -> dict[InventoryKey, int]:
        grouped: dict[InventoryKey, int] = defaultdict(int)
        for item in items:
            grouped[InventoryKey(item.product_id, item.zone_id)] += item.quantity
        return grouped

    def _rows_by_zone(self, rows: list[InventoryState]) -> dict[str, list[InventoryState]]:
        grouped: dict[str, list[InventoryState]] = defaultdict(list)
        for row in rows:
            grouped[row.zone_id].append(row)
        return grouped

    def _build_totals(
        self,
        current_rows: list[InventoryState],
        updated_rows: list[InventoryState],
        occurred_at: int,
    ) -> list[ProductTotalsState]:
        current_map = {(row.product_id, row.zone_id): row for row in current_rows}
        updated_map = {(row.product_id, row.zone_id): row for row in updated_rows}
        deltas: dict[str, tuple[int, int]] = defaultdict(lambda: (0, 0))
        for composite_key in set(current_map) | set(updated_map):
            before = current_map.get(composite_key)
            after = updated_map.get(composite_key)
            product_id = composite_key[0]
            delta_available = (after.available_quantity if after else 0) - (before.available_quantity if before else 0)
            delta_reserved = (after.reserved_quantity if after else 0) - (before.reserved_quantity if before else 0)
            old_available, old_reserved = deltas[product_id]
            deltas[product_id] = (old_available + delta_available, old_reserved + delta_reserved)

        totals: list[ProductTotalsState] = []
        for product_id, (delta_available, delta_reserved) in deltas.items():
            current_total = self._repository.get_product_total(product_id) or ProductTotalsState(product_id=product_id)
            updated_total = ProductTotalsState(
                product_id=product_id,
                total_available_quantity=current_total.total_available_quantity + delta_available,
                total_reserved_quantity=current_total.total_reserved_quantity + delta_reserved,
                last_aggregated_event_ts=max(current_total.last_aggregated_event_ts, occurred_at),
                updated_at=datetime.now(UTC),
            )
            if updated_total.total_available_quantity < 0 or updated_total.total_reserved_quantity < 0:
                raise DomainValidationError("NEGATIVE_TOTALS", f"Totals for {product_id} would become negative")
            totals.append(updated_total)
        return totals

    def _validate_zone_capacities(
        self,
        updated_rows_by_zone: dict[str, list[InventoryState]],
        current_rows_by_zone: dict[str, list[InventoryState]],
    ) -> None:
        impacted_zones = set(updated_rows_by_zone) | set(current_rows_by_zone)
        for zone_id in impacted_zones:
            zone = self._repository.get_zone(zone_id)
            if zone is None:
                raise DomainValidationError("ZONE_NOT_FOUND", f"Zone {zone_id} not found")
            current_total = sum(row.total_quantity for row in self._repository.get_zone_inventory(zone_id))
            replaced_total = current_total

            current_by_key = {(row.product_id, row.zone_id): row for row in current_rows_by_zone.get(zone_id, [])}
            updated_by_key = {(row.product_id, row.zone_id): row for row in updated_rows_by_zone.get(zone_id, [])}
            for composite_key in set(current_by_key) | set(updated_by_key):
                old = current_by_key.get(composite_key)
                new = updated_by_key.get(composite_key)
                replaced_total += (new.total_quantity if new else 0) - (old.total_quantity if old else 0)

            if replaced_total > zone.capacity:
                raise DomainValidationError(
                    "ZONE_CAPACITY_EXCEEDED",
                    f"Zone {zone_id} would exceed capacity {zone.capacity}: total={replaced_total}",
                )

    def _get_inventory(self, key: InventoryKey) -> InventoryState:
        return self._repository.get_inventory(key) or empty_inventory(key)

    def _normalize_items(self, raw_items) -> list[OrderItemData]:
        if not raw_items:
            raise DomainValidationError("EMPTY_ORDER", "Order items must not be empty")
        items: list[OrderItemData] = []
        for item in raw_items:
            product_id = self._require_text(item.get("product_id"), "items.product_id")
            zone_id = self._require_text(item.get("zone_id"), "items.zone_id")
            quantity = self._require_positive(item.get("quantity"), "items.quantity")
            items.append(OrderItemData(product_id=product_id, zone_id=zone_id, quantity=quantity))
        return items

    @staticmethod
    def _is_stale(event_ts: int, last_event_values: list[int]) -> bool:
        return any(last_ts and event_ts < last_ts for last_ts in last_event_values)

    @staticmethod
    def _require_text(value, field_name: str) -> str:
        if not isinstance(value, str) or not value.strip():
            raise DomainValidationError("MISSING_FIELD", f"Field {field_name} must be a non-empty string")
        return value

    @staticmethod
    def _require_positive(value, field_name: str) -> int:
        if not isinstance(value, int) or value <= 0:
            raise DomainValidationError("VALIDATION_ERROR", f"Invalid {field_name}: {value} (must be positive)")
        return value

    @staticmethod
    def _require_non_negative(value, field_name: str) -> int:
        if not isinstance(value, int) or value < 0:
            raise DomainValidationError("VALIDATION_ERROR", f"Invalid {field_name}: {value} (must be non-negative)")
        return value

