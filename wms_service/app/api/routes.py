"""HTTP routes for manual warehouse publishing and generator control."""

from __future__ import annotations

import logging

from fastapi import APIRouter, HTTPException, Response

from app.api.schemas import EventResponse, GeneratorStatusResponse, WarehouseEventRequest
from app.config import settings
from app.metrics import render_metrics
from app.runtime import WMSRuntime

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1", tags=["warehouse-events"])
system_router = APIRouter(tags=["system"])

_runtime: WMSRuntime | None = None


def bind_runtime(runtime: WMSRuntime) -> None:
    global _runtime
    _runtime = runtime


def get_runtime() -> WMSRuntime:
    if _runtime is None:
        raise RuntimeError("WMS runtime is not initialized")
    return _runtime


@router.post("/events", response_model=EventResponse, status_code=202)
async def publish_event(request: WarehouseEventRequest) -> EventResponse:
    try:
        envelope = get_runtime().publisher.publish_request(request)
        return EventResponse(event_id=envelope.record["event_id"])
    except Exception as exc:
        logger.exception("Failed to publish warehouse event %s", request.event_id)
        raise HTTPException(status_code=503, detail="Kafka or Schema Registry unavailable") from exc


@router.get("/health")
async def health() -> dict[str, object]:
    runtime = get_runtime()
    try:
        runtime.producer.healthcheck()
        return {
            "status": "healthy",
            "service": "wms-service",
            "generator_enabled": settings.generator_enabled,
            "generator": runtime.generator.snapshot().__dict__,
        }
    except Exception as exc:
        logger.warning("WMS healthcheck failed: %s", exc)
        raise HTTPException(status_code=503, detail="producer unhealthy") from exc


@router.get("/generator/status", response_model=GeneratorStatusResponse)
async def generator_status() -> GeneratorStatusResponse:
    return GeneratorStatusResponse(**get_runtime().generator.snapshot().__dict__)


@router.post("/generator/pause", response_model=GeneratorStatusResponse)
async def pause_generator() -> GeneratorStatusResponse:
    runtime = get_runtime()
    runtime.generator.pause()
    return GeneratorStatusResponse(**runtime.generator.snapshot().__dict__)


@router.post("/generator/resume", response_model=GeneratorStatusResponse)
async def resume_generator() -> GeneratorStatusResponse:
    runtime = get_runtime()
    runtime.generator.resume()
    return GeneratorStatusResponse(**runtime.generator.snapshot().__dict__)


@system_router.get("/metrics")
async def metrics() -> Response:
    payload, content_type = render_metrics()
    return Response(content=payload, media_type=content_type)
