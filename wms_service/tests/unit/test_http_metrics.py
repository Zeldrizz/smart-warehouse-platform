"""Unit tests for shared HTTP Prometheus middleware."""

from __future__ import annotations

from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient

from common.observability import install_http_metrics, render_metrics


def test_http_metrics_capture_status_and_error_type_labels() -> None:
    app = FastAPI()
    install_http_metrics(app, "wms-unit")

    @app.get("/ok")
    async def ok() -> dict[str, str]:
        return {"status": "ok"}

    @app.get("/boom")
    async def boom() -> None:
        raise HTTPException(status_code=503, detail="downstream unavailable")

    @app.get("/validate")
    async def validate(limit: int) -> dict[str, int]:
        return {"limit": limit}

    client = TestClient(app)
    assert client.get("/ok").status_code == 200
    assert client.get("/boom").status_code == 503
    assert client.get("/validate", params={"limit": "not-an-int"}).status_code == 422

    metrics_text = render_metrics()[0].decode("utf-8")
    request_lines = [line for line in metrics_text.splitlines() if line.startswith("http_requests_total")]
    error_lines = [line for line in metrics_text.splitlines() if line.startswith("http_request_errors_total")]

    assert any('service="wms-unit"' in line and 'endpoint="/ok"' in line and 'status="200"' in line for line in request_lines)
    assert any(
        'service="wms-unit"' in line and 'endpoint="/boom"' in line and 'error_type="service_unavailable"' in line
        for line in error_lines
    )
    assert any(
        'service="wms-unit"' in line and 'endpoint="/validate"' in line and 'error_type="validation_error"' in line
        for line in error_lines
    )
