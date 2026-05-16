"""Thin wrapper over shared observability primitives for the WMS service."""

from common.observability import initialize_http_metric_series, install_http_metrics, render_metrics


def initialize_wms_metric_series() -> None:
    initialize_http_metric_series(
        "wms-service",
        request_series=(
            ("POST", "/api/v1/events", "202"),
            ("GET", "/api/v1/health", "200"),
            ("GET", "/metrics", "200"),
            ("GET", "/api/v1/generator/status", "200"),
            ("POST", "/api/v1/generator/pause", "200"),
            ("POST", "/api/v1/generator/resume", "200"),
        ),
        error_series=(
            ("POST", "/api/v1/events", "service_unavailable"),
            ("POST", "/api/v1/events", "validation_error"),
            ("GET", "/api/v1/health", "service_unavailable"),
        ),
    )


__all__ = ["initialize_wms_metric_series", "install_http_metrics", "render_metrics"]
