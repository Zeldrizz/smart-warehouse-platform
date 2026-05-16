"""HTTP routes for health checks, metrics, control actions and traffic analytics."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Response
from fastapi.responses import HTMLResponse

from app.api.dashboard import load_traffic_dashboard_html
from app.config import settings
from app.metrics import render_metrics
from app.runtime import ConsumerRuntime

router = APIRouter()

_runtime: ConsumerRuntime | None = None


def bind_runtime(runtime: ConsumerRuntime) -> None:
    global _runtime
    _runtime = runtime


def get_runtime() -> ConsumerRuntime:
    if _runtime is None:
        raise RuntimeError("Consumer runtime is not initialized")
    return _runtime


@router.get("/health")
@router.get("/api/health")
async def health() -> dict[str, object]:
    worker = get_runtime().worker
    status = worker.status()
    payload = {"service": "consumer-service", **status}
    if status["kafka_ok"] and status["cassandra_ok"]:
        return {"status": "healthy", **payload}
    raise HTTPException(status_code=503, detail={"status": "unhealthy", **payload})


@router.get("/metrics")
async def metrics() -> Response:
    payload, content_type = render_metrics()
    return Response(content=payload, media_type=content_type)


@router.post("/admin/consumer/pause")
@router.post("/api/admin/consumer/pause")
async def pause_consumer() -> dict[str, object]:
    worker = get_runtime().worker
    worker.pause()
    return {"status": "paused", "service": "consumer-service", **worker.status()}


@router.post("/admin/consumer/resume")
@router.post("/api/admin/consumer/resume")
async def resume_consumer() -> dict[str, object]:
    worker = get_runtime().worker
    worker.resume()
    return {"status": "running", "service": "consumer-service", **worker.status()}


@router.get("/api/v1/analytics/traffic")
async def traffic_analytics(days: int = settings.analytics_lookback_days_default) -> dict[str, object]:
    if days < 1 or days > 30:
        raise HTTPException(status_code=400, detail="days must be between 1 and 30")
    return get_runtime().traffic_analytics.build_hourly_traffic(days)


@router.get("/traffic-dashboard", response_class=HTMLResponse)
async def traffic_dashboard() -> HTMLResponse:
    return HTMLResponse(load_traffic_dashboard_html())
