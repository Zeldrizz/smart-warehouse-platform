"""Domain models and processing result containers."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any, Literal


def utc_now() -> datetime:
    return datetime.now(UTC)


@dataclass(frozen=True)
class InventoryKey:
    product_id: str
    zone_id: str


@dataclass
class InventoryState:
    product_id: str
    zone_id: str
    available_quantity: int = 0
    reserved_quantity: int = 0
    last_event_ts: int = 0
    supplier_id: str | None = None
    updated_at: datetime = field(default_factory=utc_now)

    @property
    def total_quantity(self) -> int:
        return self.available_quantity + self.reserved_quantity


@dataclass
class ProductTotalsState:
    product_id: str
    total_available_quantity: int = 0
    total_reserved_quantity: int = 0
    last_aggregated_event_ts: int = 0
    updated_at: datetime = field(default_factory=utc_now)


@dataclass
class ZoneInfo:
    zone_id: str
    zone_name: str
    capacity: int


@dataclass(frozen=True)
class OrderItemData:
    product_id: str
    zone_id: str
    quantity: int


@dataclass
class OrderState:
    order_id: str
    status: str
    items: list[OrderItemData]
    created_at: datetime
    updated_at: datetime
    last_event_ts: int


@dataclass(frozen=True)
class KafkaMetadata:
    partition: int
    offset: int


@dataclass
class EventContext:
    event: dict[str, Any]
    raw_json: str
    event_id: str
    event_type: str
    occurred_at: int
    schema_variant: str
    metadata: KafkaMetadata


@dataclass
class ProcessResult:
    action: Literal["applied", "duplicate", "stale", "dlq"]
    outcome: str
    error_code: str | None = None
    error_reason: str | None = None


class DomainValidationError(Exception):
    def __init__(self, error_code: str, message: str) -> None:
        super().__init__(message)
        self.error_code = error_code
        self.message = message

