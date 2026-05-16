#!/bin/bash
set -euo pipefail

WMS_URL="${WMS_URL:-http://localhost:8001}"
CONSUMER_URL="${CONSUMER_URL:-http://localhost:8002}"

echo "Waiting for live synthetic traffic to accumulate..."

export DEMO_WMS_GENERATOR_URL="${WMS_URL}/api/v1/generator/status"
export DEMO_CONSUMER_TRAFFIC_URL="${CONSUMER_URL}/api/v1/analytics/traffic?days=14"

python3 - <<'PY'
import json
import os
import time
import urllib.request

WMS_URL = os.environ["DEMO_WMS_GENERATOR_URL"]
CONSUMER_URL = os.environ["DEMO_CONSUMER_TRAFFIC_URL"]

for _ in range(120):
    status = json.load(urllib.request.urlopen(WMS_URL))
    if status["phase"] == "live" and status["live_events_published"] >= 40:
        traffic = json.load(urllib.request.urlopen(CONSUMER_URL))
        nonzero = sum(1 for point in traffic["series"] if point["total_events"] > 0)
        if traffic["summary"]["total_events"] >= 20:
            print(json.dumps({
                "generator_phase": status["phase"],
                "generator_started_at": status["started_at"],
                "live_events_published": status["live_events_published"],
                "analytics_total_events": traffic["summary"]["total_events"],
                "analytics_active_buckets": nonzero,
                "analytics_window_from": traffic["from"],
                "analytics_window_to": traffic["to"],
                "analytics_current_hour": traffic["series"][-1]["total_events"],
            }, indent=2))
            break
    time.sleep(2)
else:
    raise SystemExit("Generator did not accumulate enough live traffic in time")
PY

echo
echo "Open the dashboard in a browser:"
echo "  http://localhost:8002/traffic-dashboard"
echo
echo "Or inspect the raw endpoints:"
echo "  curl -sS ${WMS_URL}/api/v1/generator/status"
echo "  curl -sS ${CONSUMER_URL}/api/v1/analytics/traffic?days=14"
