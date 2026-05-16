#!/usr/bin/env python3
"""Validate SLI-based Prometheus gates and save the queried evidence."""

from __future__ import annotations

import argparse
import json
import math
import time
import urllib.parse
import urllib.request
from pathlib import Path


QUERIES = {
    "api_availability": {
        "expr": 'sum(rate(http_requests_total{service="wms-service",endpoint="/api/v1/events",status=~"2.."}[5m])) / clamp_min(sum(rate(http_requests_total{service="wms-service",endpoint="/api/v1/events"}[5m])), 0.0001)',
        "comparison": "gte",
        "target": 0.995,
        "failure_threshold": 0.95,
        "unit": "ratio",
    },
    "wms_latency_p95_seconds": {
        "expr": 'histogram_quantile(0.95, sum by(le) (rate(http_request_duration_seconds_bucket{service="wms-service",endpoint="/api/v1/events"}[5m])))',
        "comparison": "lte",
        "target": 0.5,
        "failure_threshold": 1.0,
        "unit": "seconds",
    },
    "event_end_to_end_delay_p95_seconds": {
        "expr": "histogram_quantile(0.95, sum by(le) (rate(event_end_to_end_delay_seconds_bucket[5m])))",
        "comparison": "lte",
        "target": 5.0,
        "failure_threshold": 10.0,
        "unit": "seconds",
    },
}


def fetch_json(url: str) -> dict:
    with urllib.request.urlopen(url, timeout=15) as response:
        return json.load(response)


def instant_query(prometheus_url: str, expr: str) -> tuple[float | None, dict]:
    query = urllib.parse.urlencode({"query": expr})
    payload = fetch_json(f"{prometheus_url}/api/v1/query?{query}")
    result = payload.get("data", {}).get("result", [])
    if not result:
        return None, payload
    value = float(result[0]["value"][1])
    if math.isnan(value) or math.isinf(value):
        return None, payload
    return value, payload


def evaluate(comparison: str, actual: float, target: float) -> bool:
    if comparison == "gte":
        return actual >= target
    if comparison == "lte":
        return actual <= target
    raise ValueError(f"Unsupported comparison {comparison}")


def wait_for_metrics(prometheus_url: str, timeout_seconds: int) -> dict[str, tuple[float, dict]]:
    deadline = time.time() + timeout_seconds
    last_payloads: dict[str, dict] = {}
    while time.time() < deadline:
        results: dict[str, tuple[float, dict]] = {}
        missing = False
        for name, config in QUERIES.items():
            value, payload = instant_query(prometheus_url, config["expr"])
            last_payloads[name] = payload
            if value is None:
                missing = True
                break
            results[name] = (value, payload)
        if not missing:
            return results
        time.sleep(5)
    raise RuntimeError(f"Timed out waiting for Prometheus metrics: {json.dumps(last_payloads, ensure_ascii=False)}")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--prometheus-url", required=True)
    parser.add_argument("--alertmanager-url", required=True)
    parser.add_argument("--output-json", required=True)
    parser.add_argument("--timeout-seconds", type=int, default=90)
    args = parser.parse_args()

    results = wait_for_metrics(args.prometheus_url.rstrip("/"), args.timeout_seconds)
    prometheus_alerts = fetch_json(f"{args.prometheus_url.rstrip('/')}/api/v1/alerts")
    alertmanager_alerts = fetch_json(f"{args.alertmanager_url.rstrip('/')}/api/v2/alerts")

    report = {
        "generated_at_epoch_seconds": time.time(),
        "prometheus_url": args.prometheus_url,
        "alertmanager_url": args.alertmanager_url,
        "checks": {},
        "prometheus_alerts": prometheus_alerts,
        "alertmanager_alerts": alertmanager_alerts,
    }

    failures: list[str] = []
    for name, config in QUERIES.items():
        value, payload = results[name]
        passed = evaluate(config["comparison"], value, config["target"])
        report["checks"][name] = {
            "value": value,
            "comparison": config["comparison"],
            "target": config["target"],
            "failure_threshold": config["failure_threshold"],
            "unit": config["unit"],
            "passed": passed,
            "query": config["expr"],
            "raw_response": payload,
        }
        if not passed:
            failures.append(f"{name}: actual={value} target={config['comparison']} {config['target']}")

    output_path = Path(args.output_json)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")

    for name, data in report["checks"].items():
        print(f"{name}: value={data['value']:.6f} target={data['comparison']} {data['target']} passed={data['passed']}")

    if failures:
        print("Prometheus gates failed:")
        for failure in failures:
            print(f" - {failure}")
        return 1

    print(f"Prometheus gates passed. Evidence saved to {output_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
