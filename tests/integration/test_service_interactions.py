"""Integration tests that validate inter-service communication on the real stack."""

from __future__ import annotations

import time

import pytest

from conftest import CONSUMER_SERVICE_URL, KAFKA_DLQ_TOPIC, PROMETHEUS_URL, WMS_SERVICE_URL, build_dlq_consumer


def post_event(http_client, payload: dict):
    response = http_client.post(f"{WMS_SERVICE_URL}/api/v1/events", json=payload)
    assert response.status_code == 202, response.text
    body = response.json()
    assert body["status"] == "accepted"
    assert body["event_id"] == payload["event_id"]
    return response


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


def get_inventory(session, product_id: str, zone_id: str):
    row = session.execute(
        "SELECT product_id, zone_id, available_quantity, reserved_quantity "
        "FROM inventory_by_product_zone WHERE product_id = %s AND zone_id = %s",
        (product_id, zone_id),
    ).one()
    assert row is not None, f"Missing inventory row for {product_id}/{zone_id}"
    return row


@pytest.mark.usefixtures("wait_for_services")
class TestServiceInteractions:
    def test_wms_event_flows_through_consumer_to_cassandra(self, http_client, cassandra_session, unique_suffix: str):
        product_id = f"SKU-INT-{unique_suffix}"
        post_event(http_client, {
            "event_id": f"{product_id}-recv",
            "event_type": "PRODUCT_RECEIVED",
            "occurred_at": int(time.time() * 1000),
            "product_id": product_id,
            "zone_id": "ZONE-A",
            "quantity": 21,
        })

        def _assert_projection():
            row = get_inventory(cassandra_session, product_id, "ZONE-A")
            assert row["available_quantity"] == 21
            assert row["reserved_quantity"] == 0

        wait_until(_assert_projection)

    def test_invalid_event_goes_to_dlq_and_consumer_keeps_processing(self, http_client, cassandra_session, unique_suffix: str):
        invalid_event_id = f"invalid-{unique_suffix}"
        invalid_product = f"SKU-DLQ-{unique_suffix}"
        post_event(http_client, {
            "event_id": invalid_event_id,
            "event_type": "PRODUCT_SHIPPED",
            "occurred_at": int(time.time() * 1000),
            "product_id": invalid_product,
            "zone_id": "ZONE-A",
            "quantity": -5,
        })

        consumer = build_dlq_consumer()
        consumer.subscribe([KAFKA_DLQ_TOPIC])
        try:
            found = False
            deadline = time.time() + 45
            while time.time() < deadline:
                msg = consumer.poll(2.0)
                if msg is None or msg.error():
                    continue
                value = msg.value()
                if value["event_id"] == invalid_event_id:
                    assert value["error_code"] == "VALIDATION_ERROR"
                    assert invalid_event_id in value["original_event_json"]
                    found = True
                    break
            assert found, f"DLQ event for {invalid_event_id} not found"
        finally:
            consumer.close()

        valid_product = f"SKU-AFTER-DLQ-{unique_suffix}"
        post_event(http_client, {
            "event_id": f"after-dlq-{unique_suffix}",
            "event_type": "PRODUCT_RECEIVED",
            "occurred_at": int(time.time() * 1000) + 1000,
            "product_id": valid_product,
            "zone_id": "ZONE-A",
            "quantity": 10,
        })
        wait_until(lambda: assert_inventory(cassandra_session, valid_product, "ZONE-A", 10, 0))

    def test_services_expose_prometheus_metrics_and_prometheus_scrapes_them(self, http_client):
        wms_metrics = http_client.get(f"{WMS_SERVICE_URL}/metrics")
        assert wms_metrics.status_code == 200
        assert "http_requests_total" in wms_metrics.text

        consumer_metrics = http_client.get(f"{CONSUMER_SERVICE_URL}/metrics")
        assert consumer_metrics.status_code == 200
        for metric_name in (
            "http_requests_total",
            "http_request_duration_seconds",
            "event_end_to_end_delay_seconds",
        ):
            assert metric_name in consumer_metrics.text

        def _assert_scrape_targets():
            response = http_client.get(
                f"{PROMETHEUS_URL}/api/v1/query",
                params={"query": 'up{job=~"wms-service|consumer-service"}'},
            )
            assert response.status_code == 200
            result = response.json()["data"]["result"]
            assert len(result) == 2
            assert all(item["value"][1] == "1" for item in result)

        wait_until(_assert_scrape_targets)


def assert_inventory(session, product_id: str, zone_id: str, available: int, reserved: int) -> None:
    row = get_inventory(session, product_id, zone_id)
    assert row["available_quantity"] == available
    assert row["reserved_quantity"] == reserved
