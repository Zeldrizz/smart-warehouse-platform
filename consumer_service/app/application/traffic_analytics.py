"""Builds business traffic series from Cassandra event audit rows."""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from app.infrastructure.cassandra_repository import WarehouseRepository


@dataclass(frozen=True)
class TrafficPoint:
    timestamp: str
    total_events: int
    applied_events: int
    dlq_events: int
    stale_events: int
    duplicate_events: int
    by_type: dict[str, int]


class TrafficAnalyticsService:
    def __init__(self, repository: WarehouseRepository) -> None:
        self._repository = repository

    def build_hourly_traffic(self, days: int) -> dict[str, object]:
        now = datetime.now(UTC).replace(minute=0, second=0, microsecond=0)
        lookback_start = now - timedelta(days=days)
        buckets: dict[datetime, Counter[str]] = {}

        cursor_date = lookback_start.date()
        while cursor_date <= now.date():
            for row in self._repository.get_event_history_for_date(cursor_date):
                occurred_at_ms = row.get("occurred_at_ms")
                if occurred_at_ms is None:
                    continue
                bucket_time = datetime.fromtimestamp(occurred_at_ms / 1000, UTC).replace(
                    minute=0,
                    second=0,
                    microsecond=0,
                )
                if bucket_time < lookback_start or bucket_time > now:
                    continue
                bucket = buckets.setdefault(bucket_time, Counter())
                bucket["total"] += 1
                bucket[row["outcome"].lower()] += 1
                bucket[f"type:{row['event_type']}"] += 1
            cursor_date += timedelta(days=1)

        if buckets:
            start = min(buckets)
        else:
            start = now - timedelta(hours=1)

        series: list[TrafficPoint] = []
        bucket_time = start
        while bucket_time <= now:
            bucket = buckets.get(bucket_time, Counter())
            by_type = {
                key.removeprefix("type:"): value
                for key, value in bucket.items()
                if key.startswith("type:")
            }
            series.append(
                TrafficPoint(
                    timestamp=bucket_time.isoformat(),
                    total_events=bucket.get("total", 0),
                    applied_events=bucket.get("applied", 0),
                    dlq_events=bucket.get("dlq", 0),
                    stale_events=bucket.get("stale", 0),
                    duplicate_events=bucket.get("duplicate", 0),
                    by_type=by_type,
                )
            )
            bucket_time += timedelta(hours=1)

        return {
            "bucket": "hour",
            "from": start.isoformat(),
            "to": now.isoformat(),
            "series": [point.__dict__ for point in series],
            "summary": {
                "days": days,
                "total_events": sum(point.total_events for point in series),
                "applied_events": sum(point.applied_events for point in series),
                "dlq_events": sum(point.dlq_events for point in series),
            },
        }
