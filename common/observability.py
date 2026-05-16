"""Shared Prometheus metrics and HTTP instrumentation helpers."""

from __future__ import annotations

import time
from typing import Callable

from fastapi import FastAPI, Request
from prometheus_client import CONTENT_TYPE_LATEST, Counter, Gauge, Histogram, generate_latest


HTTP_REQUEST_DURATION_BUCKETS = (0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0)
EVENT_PROCESSING_DURATION_BUCKETS = (0.01, 0.05, 0.1, 0.25, 0.5, 1, 2, 5, 10)
EVENT_END_TO_END_DELAY_BUCKETS = (0.05, 0.1, 0.25, 0.5, 1, 2, 5, 10, 20, 30, 60)

http_requests_total = Counter(
    "http_requests_total",
    "Total HTTP requests served by service endpoints",
    ["service", "method", "endpoint", "status"],
)

http_request_errors_total = Counter(
    "http_request_errors_total",
    "Total HTTP requests that finished with an error status or exception",
    ["service", "method", "endpoint", "error_type"],
)

http_request_duration_seconds = Histogram(
    "http_request_duration_seconds",
    "HTTP request latency in seconds",
    ["service", "method", "endpoint"],
    buckets=HTTP_REQUEST_DURATION_BUCKETS,
)

consumer_lag = Gauge(
    "consumer_lag",
    "Committed consumer lag per partition for warehouse-events",
    ["partition"],
)

events_processed_total = Counter(
    "events_processed_total",
    "Total number of terminally handled warehouse events",
    ["event_type"],
)

event_processing_duration_seconds = Histogram(
    "event_processing_duration_seconds",
    "End-to-end processing time spent inside the consumer worker per message",
    buckets=EVENT_PROCESSING_DURATION_BUCKETS,
)

event_end_to_end_delay_seconds = Histogram(
    "event_end_to_end_delay_seconds",
    "Delay between event publication timestamp and terminal processing completion",
    ["event_type"],
    buckets=EVENT_END_TO_END_DELAY_BUCKETS,
)

cassandra_write_errors_total = Counter(
    "cassandra_write_errors_total",
    "Total number of Cassandra write failures",
)

dlq_events_total = Counter(
    "dlq_events_total",
    "Total number of events sent to Dead Letter Queue",
    ["error_code"],
)


def render_metrics() -> tuple[bytes, str]:
    return generate_latest(), CONTENT_TYPE_LATEST


def install_http_metrics(app: FastAPI, service_name: str) -> None:
    @app.middleware("http")
    async def prometheus_http_middleware(request: Request, call_next: Callable):
        method = request.method.upper()
        started_at = time.perf_counter()
        try:
            response = await call_next(request)
        except Exception:
            duration = time.perf_counter() - started_at
            endpoint = _resolve_endpoint_label(request)
            http_requests_total.labels(service_name, method, endpoint, "500").inc()
            http_request_errors_total.labels(service_name, method, endpoint, "unhandled_exception").inc()
            http_request_duration_seconds.labels(service_name, method, endpoint).observe(duration)
            raise

        duration = time.perf_counter() - started_at
        endpoint = _resolve_endpoint_label(request)
        status = str(response.status_code)
        http_requests_total.labels(service_name, method, endpoint, status).inc()
        if response.status_code >= 400:
            http_request_errors_total.labels(
                service_name,
                method,
                endpoint,
                _resolve_error_type(response.status_code),
            ).inc()
        http_request_duration_seconds.labels(service_name, method, endpoint).observe(duration)
        return response


def _resolve_endpoint_label(request: Request) -> str:
    route = request.scope.get("route")
    if route is not None:
        path = getattr(route, "path_format", None) or getattr(route, "path", None)
        if path:
            return path
    return request.url.path


def _resolve_error_type(status_code: int) -> str:
    if status_code == 422:
        return "validation_error"
    if status_code == 503:
        return "service_unavailable"
    return f"http_{status_code}"
