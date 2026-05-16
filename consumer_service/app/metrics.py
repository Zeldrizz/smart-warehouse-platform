"""Thin wrapper over shared observability primitives for the consumer service."""

from common.observability import (
    cassandra_write_errors_total,
    consumer_lag,
    dlq_events_total,
    event_end_to_end_delay_seconds,
    event_processing_duration_seconds,
    events_processed_total,
    initialize_consumer_lag_partitions,
    initialize_event_metric_series,
    initialize_http_metric_series,
    install_http_metrics,
    render_metrics,
)


KNOWN_WAREHOUSE_EVENT_TYPES = (
    "PRODUCT_RECEIVED",
    "PRODUCT_SHIPPED",
    "PRODUCT_MOVED",
    "PRODUCT_RESERVED",
    "PRODUCT_RELEASED",
    "INVENTORY_COUNTED",
    "ORDER_CREATED",
    "ORDER_COMPLETED",
)


def initialize_consumer_metric_series() -> None:
    initialize_http_metric_series(
        "consumer-service",
        request_series=(
            ("GET", "/health", "200"),
            ("GET", "/api/health", "200"),
            ("GET", "/metrics", "200"),
            ("POST", "/admin/consumer/pause", "200"),
            ("POST", "/api/admin/consumer/pause", "200"),
            ("POST", "/admin/consumer/resume", "200"),
            ("POST", "/api/admin/consumer/resume", "200"),
            ("GET", "/api/v1/analytics/traffic", "200"),
            ("GET", "/traffic-dashboard", "200"),
        ),
        error_series=(
            ("GET", "/health", "service_unavailable"),
            ("GET", "/api/health", "service_unavailable"),
            ("GET", "/api/v1/analytics/traffic", "http_400"),
        ),
    )
    initialize_event_metric_series(KNOWN_WAREHOUSE_EVENT_TYPES)
    initialize_consumer_lag_partitions(range(3))

__all__ = [
    "cassandra_write_errors_total",
    "consumer_lag",
    "dlq_events_total",
    "event_end_to_end_delay_seconds",
    "event_processing_duration_seconds",
    "events_processed_total",
    "initialize_consumer_metric_series",
    "install_http_metrics",
    "render_metrics",
]
