"""Shared fixtures for integration and end-to-end tests."""

from __future__ import annotations

import os
import time
import uuid

import httpx
import pytest
from cassandra.cluster import Cluster
from cassandra.policies import RoundRobinPolicy
from cassandra.query import dict_factory
from confluent_kafka.avro import AvroConsumer


WMS_SERVICE_URL = os.getenv("WMS_SERVICE_URL", "http://wms-service:8001")
CONSUMER_SERVICE_URL = os.getenv("CONSUMER_SERVICE_URL", "http://consumer-service:8002")
CASSANDRA_CONTACT_POINTS = os.getenv("CASSANDRA_CONTACT_POINTS", "cassandra-1").split(",")
CASSANDRA_PORT = int(os.getenv("CASSANDRA_PORT", "9042"))
CASSANDRA_KEYSPACE = os.getenv("CASSANDRA_KEYSPACE", "warehouse")
KAFKA_BROKERS = os.getenv("KAFKA_BROKERS", "kafka-1:29092,kafka-2:29093")
SCHEMA_REGISTRY_URL = os.getenv("SCHEMA_REGISTRY_URL", "http://schema-registry:8081")
KAFKA_DLQ_TOPIC = os.getenv("KAFKA_DLQ_TOPIC", "warehouse-events-dlq")
PROMETHEUS_URL = os.getenv("PROMETHEUS_URL", "http://prometheus:9090")


@pytest.fixture(scope="session")
def http_client() -> httpx.Client:
    return httpx.Client(timeout=30.0)


@pytest.fixture(scope="session")
def cassandra_session():
    cluster = Cluster(
        contact_points=CASSANDRA_CONTACT_POINTS,
        port=CASSANDRA_PORT,
        load_balancing_policy=RoundRobinPolicy(),
        protocol_version=5,
    )
    session = cluster.connect(CASSANDRA_KEYSPACE)
    session.row_factory = dict_factory
    yield session
    session.shutdown()
    cluster.shutdown()


@pytest.fixture(scope="session")
def wait_for_services(http_client: httpx.Client, cassandra_session):
    for url in (f"{WMS_SERVICE_URL}/api/v1/health", f"{CONSUMER_SERVICE_URL}/health"):
        for _ in range(90):
            try:
                response = http_client.get(url)
                if response.status_code == 200:
                    break
            except Exception:
                pass
            time.sleep(2)
        else:
            pytest.fail(f"Service {url} did not become healthy in time")
    cassandra_session.execute("SELECT now() FROM system.local")
    try:
        http_client.post(f"{WMS_SERVICE_URL}/api/v1/generator/pause")
    except Exception:
        pass


@pytest.fixture()
def unique_suffix() -> str:
    return uuid.uuid4().hex[:8]


@pytest.fixture(autouse=True)
def clean_warehouse_tables(cassandra_session):
    for table in (
        "inventory_by_product_zone",
        "inventory_by_product",
        "inventory_by_zone",
        "inventory_totals_by_product",
        "orders_by_id",
        "processed_events_by_id",
        "event_history_by_day",
    ):
        cassandra_session.execute(f"TRUNCATE {table}")
    yield


def build_dlq_consumer() -> AvroConsumer:
    return AvroConsumer(
        {
            "bootstrap.servers": KAFKA_BROKERS,
            "schema.registry.url": SCHEMA_REGISTRY_URL,
            "group.id": f"smart-warehouse-tests-dlq-{uuid.uuid4().hex[:8]}",
            "auto.offset.reset": "earliest",
            "enable.auto.commit": False,
        }
    )
