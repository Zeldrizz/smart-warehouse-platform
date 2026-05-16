"""Helpers for serving the traffic dashboard page."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path


@lru_cache(maxsize=1)
def load_traffic_dashboard_html() -> str:
    template_path = Path(__file__).with_name("templates") / "traffic_dashboard.html"
    return template_path.read_text(encoding="utf-8")
