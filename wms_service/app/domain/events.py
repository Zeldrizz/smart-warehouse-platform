"""Warehouse event records shared by manual publishing and synthetic generation."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any


class WarehouseEventType(str, Enum):
    PRODUCT_RECEIVED = "PRODUCT_RECEIVED"
    PRODUCT_SHIPPED = "PRODUCT_SHIPPED"
    PRODUCT_MOVED = "PRODUCT_MOVED"
    PRODUCT_RESERVED = "PRODUCT_RESERVED"
    PRODUCT_RELEASED = "PRODUCT_RELEASED"
    INVENTORY_COUNTED = "INVENTORY_COUNTED"
    ORDER_CREATED = "ORDER_CREATED"
    ORDER_COMPLETED = "ORDER_COMPLETED"


@dataclass(frozen=True)
class WarehouseEventEnvelope:
    record: dict[str, Any]
    schema_version: str
    routing_key: str


@dataclass(frozen=True)
class GeneratorSnapshot:
    enabled: bool
    phase: str
    paused: bool
    started_at: int | None
    live_events_published: int
    last_event_id: str | None
    last_event_type: str | None
    last_occurred_at: int | None
