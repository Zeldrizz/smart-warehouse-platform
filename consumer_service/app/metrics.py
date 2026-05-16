"""Thin wrapper over shared observability primitives for the consumer service."""

from common.observability import (
    cassandra_write_errors_total,
    consumer_lag,
    dlq_events_total,
    event_end_to_end_delay_seconds,
    event_processing_duration_seconds,
    events_processed_total,
    install_http_metrics,
    render_metrics,
)

__all__ = [
    "cassandra_write_errors_total",
    "consumer_lag",
    "dlq_events_total",
    "event_end_to_end_delay_seconds",
    "event_processing_duration_seconds",
    "events_processed_total",
    "install_http_metrics",
    "render_metrics",
]
