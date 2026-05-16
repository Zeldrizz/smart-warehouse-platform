"""HTTP request and response schemas for the WMS service."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Annotated, Literal, Union

from pydantic import BaseModel, Field


def utc_now_ms() -> int:
    return int(datetime.now(timezone.utc).timestamp() * 1000)


class OrderItemRequest(BaseModel):
    product_id: str = Field(..., min_length=1, max_length=100)
    zone_id: str = Field(..., min_length=1, max_length=100)
    quantity: int


class EventResponse(BaseModel):
    event_id: str
    status: str = "accepted"


class GeneratorStatusResponse(BaseModel):
    enabled: bool
    phase: str
    paused: bool
    started_at: int | None = None
    live_events_published: int
    last_event_id: str | None = None
    last_event_type: str | None = None
    last_occurred_at: int | None = None


class BaseEventRequest(BaseModel):
    event_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    occurred_at: int = Field(default_factory=utc_now_ms, description="UTC time in ms since epoch")
    event_type: str


class ProductReceivedRequest(BaseEventRequest):
    event_type: Literal["PRODUCT_RECEIVED"]
    product_id: str = Field(..., min_length=1, max_length=100)
    zone_id: str = Field(..., min_length=1, max_length=100)
    quantity: int
    supplier_id: str | None = Field(default=None, min_length=1, max_length=100)
    schema_version: Literal["v1", "v2"] = "v2"


class ProductShippedRequest(BaseEventRequest):
    event_type: Literal["PRODUCT_SHIPPED"]
    product_id: str = Field(..., min_length=1, max_length=100)
    zone_id: str = Field(..., min_length=1, max_length=100)
    quantity: int


class ProductMovedRequest(BaseEventRequest):
    event_type: Literal["PRODUCT_MOVED"]
    product_id: str = Field(..., min_length=1, max_length=100)
    from_zone_id: str = Field(..., min_length=1, max_length=100)
    to_zone_id: str = Field(..., min_length=1, max_length=100)
    quantity: int


class ProductReservedRequest(BaseEventRequest):
    event_type: Literal["PRODUCT_RESERVED"]
    product_id: str = Field(..., min_length=1, max_length=100)
    zone_id: str = Field(..., min_length=1, max_length=100)
    quantity: int


class ProductReleasedRequest(BaseEventRequest):
    event_type: Literal["PRODUCT_RELEASED"]
    product_id: str = Field(..., min_length=1, max_length=100)
    zone_id: str = Field(..., min_length=1, max_length=100)
    quantity: int


class InventoryCountedRequest(BaseEventRequest):
    event_type: Literal["INVENTORY_COUNTED"]
    product_id: str = Field(..., min_length=1, max_length=100)
    zone_id: str = Field(..., min_length=1, max_length=100)
    counted_quantity: int


class OrderCreatedRequest(BaseEventRequest):
    event_type: Literal["ORDER_CREATED"]
    order_id: str = Field(..., min_length=1, max_length=100)
    items: list[OrderItemRequest] = Field(..., min_length=1)


class OrderCompletedRequest(BaseEventRequest):
    event_type: Literal["ORDER_COMPLETED"]
    order_id: str = Field(..., min_length=1, max_length=100)


WarehouseEventRequest = Annotated[
    Union[
        ProductReceivedRequest,
        ProductShippedRequest,
        ProductMovedRequest,
        ProductReservedRequest,
        ProductReleasedRequest,
        InventoryCountedRequest,
        OrderCreatedRequest,
        OrderCompletedRequest,
    ],
    Field(discriminator="event_type"),
]
