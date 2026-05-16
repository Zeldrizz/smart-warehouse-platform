"""End-to-end scenario that exercises the complete warehouse workflow."""

from __future__ import annotations

import time

import pytest

from conftest import WMS_SERVICE_URL


def wait_until(assertion, timeout: float = 45.0, step: float = 1.5) -> None:
    deadline = time.time() + timeout
    last_error = None
    while time.time() < deadline:
        try:
            assertion()
            return
        except AssertionError as exc:
            last_error = exc
            time.sleep(step)
    if last_error:
        raise last_error
    raise AssertionError("Condition was not met in time")


def post_event(http_client, payload: dict) -> dict:
    response = http_client.post(f"{WMS_SERVICE_URL}/api/v1/events", json=payload)
    assert response.status_code == 202, response.text
    body = response.json()
    assert body["event_id"] == payload["event_id"]
    assert body["status"] == "accepted"
    return body


def get_inventory(session, product_id: str, zone_id: str):
    row = session.execute(
        "SELECT product_id, zone_id, available_quantity, reserved_quantity "
        "FROM inventory_by_product_zone WHERE product_id = %s AND zone_id = %s",
        (product_id, zone_id),
    ).one()
    assert row is not None, f"Missing inventory row for {product_id}/{zone_id}"
    return row


@pytest.mark.usefixtures("wait_for_services")
def test_full_warehouse_user_scenario(http_client, cassandra_session, unique_suffix: str):
    product_id = f"SKU-E2E-{unique_suffix}"
    order_id = f"ORDER-{unique_suffix}"
    base_ts = int(time.time() * 1000)

    post_event(http_client, {
        "event_id": f"{product_id}-recv",
        "event_type": "PRODUCT_RECEIVED",
        "occurred_at": base_ts,
        "product_id": product_id,
        "zone_id": "ZONE-A",
        "quantity": 100,
    })
    wait_until(lambda: assert_inventory(cassandra_session, product_id, "ZONE-A", 100, 0))

    post_event(http_client, {
        "event_id": f"{product_id}-reserve",
        "event_type": "PRODUCT_RESERVED",
        "occurred_at": base_ts + 1000,
        "product_id": product_id,
        "zone_id": "ZONE-A",
        "quantity": 30,
    })
    wait_until(lambda: assert_inventory(cassandra_session, product_id, "ZONE-A", 70, 30))

    post_event(http_client, {
        "event_id": f"{product_id}-move",
        "event_type": "PRODUCT_MOVED",
        "occurred_at": base_ts + 2000,
        "product_id": product_id,
        "from_zone_id": "ZONE-A",
        "to_zone_id": "ZONE-B",
        "quantity": 20,
    })
    wait_until(lambda: assert_inventory(cassandra_session, product_id, "ZONE-A", 50, 30))
    wait_until(lambda: assert_inventory(cassandra_session, product_id, "ZONE-B", 20, 0))

    post_event(http_client, {
        "event_id": f"{order_id}-create",
        "event_type": "ORDER_CREATED",
        "occurred_at": base_ts + 3000,
        "order_id": order_id,
        "items": [{"product_id": product_id, "zone_id": "ZONE-A", "quantity": 15}],
    })
    wait_until(lambda: assert_inventory(cassandra_session, product_id, "ZONE-A", 35, 45))

    post_event(http_client, {
        "event_id": f"{order_id}-complete",
        "event_type": "ORDER_COMPLETED",
        "occurred_at": base_ts + 4000,
        "order_id": order_id,
    })
    wait_until(lambda: assert_inventory(cassandra_session, product_id, "ZONE-A", 35, 30))

    totals = cassandra_session.execute(
        "SELECT total_available_quantity, total_reserved_quantity "
        "FROM inventory_totals_by_product WHERE product_id = %s",
        (product_id,),
    ).one()
    assert totals["total_available_quantity"] == 55
    assert totals["total_reserved_quantity"] == 30

    order = cassandra_session.execute(
        "SELECT status FROM orders_by_id WHERE order_id = %s",
        (order_id,),
    ).one()
    assert order["status"] == "COMPLETED"

    zone_b = get_inventory(cassandra_session, product_id, "ZONE-B")
    assert zone_b["available_quantity"] == 20
    assert zone_b["reserved_quantity"] == 0


def assert_inventory(session, product_id: str, zone_id: str, available: int, reserved: int) -> None:
    row = get_inventory(session, product_id, zone_id)
    assert row["available_quantity"] == available
    assert row["reserved_quantity"] == reserved
