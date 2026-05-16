"""Thin wrapper over shared observability primitives for the WMS service."""

from common.observability import install_http_metrics, render_metrics

__all__ = ["install_http_metrics", "render_metrics"]
