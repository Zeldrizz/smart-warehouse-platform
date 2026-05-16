import http from "k6/http";
import { check, sleep } from "k6";

export const options = {
  scenarios: {
    publish: {
      executor: "constant-vus",
      vus: 10,
      duration: "30s",
      exec: "publishEvents",
    },
    health: {
      executor: "constant-vus",
      vus: 1,
      duration: "30s",
      exec: "healthcheck",
    },
  },
  thresholds: {
    http_req_failed: ["rate<0.01"],
    http_req_duration: ["p(95)<500"],
    "checks{scenario:health}": ["rate>0.99"],
  },
};

const baseUrl = __ENV.BASE_URL || "http://localhost:8001";

function buildPayload() {
  const batch = Math.floor(__ITER / 3);
  const productId = `LOAD-SKU-${__VU}-${batch}`;
  const eventIndex = __ITER % 3;
  const occurredAt = Date.now();

  if (eventIndex === 0) {
    return {
      event_id: `load-recv-${__VU}-${__ITER}`,
      event_type: "PRODUCT_RECEIVED",
      occurred_at: occurredAt,
      product_id: productId,
      zone_id: "ZONE-A",
      quantity: 50,
    };
  }

  if (eventIndex === 1) {
    return {
      event_id: `load-reserve-${__VU}-${__ITER}`,
      event_type: "PRODUCT_RESERVED",
      occurred_at: occurredAt,
      product_id: productId,
      zone_id: "ZONE-A",
      quantity: 10,
    };
  }

  return {
    event_id: `load-move-${__VU}-${__ITER}`,
    event_type: "PRODUCT_MOVED",
    occurred_at: occurredAt,
    product_id: productId,
    from_zone_id: "ZONE-A",
    to_zone_id: "ZONE-B",
    quantity: 5,
  };
}

export function publishEvents() {
  const payload = buildPayload();
  const response = http.post(`${baseUrl}/api/v1/events`, JSON.stringify(payload), {
    headers: { "Content-Type": "application/json" },
  });

  check(response, {
    "publish returned 202": (r) => r.status === 202,
    "publish body has accepted status": (r) => r.json("status") === "accepted",
  });

  sleep(0.2);
}

export function healthcheck() {
  const response = http.get(`${baseUrl}/api/v1/health`);
  check(response, {
    "health is 200": (r) => r.status === 200,
  });
  sleep(1);
}
