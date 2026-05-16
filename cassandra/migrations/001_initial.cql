CREATE KEYSPACE IF NOT EXISTS warehouse
WITH replication = {'class': 'NetworkTopologyStrategy', 'dc1': 3};

USE warehouse;

CREATE TYPE IF NOT EXISTS order_item (
    product_id text,
    zone_id text,
    quantity int
);

CREATE TABLE IF NOT EXISTS zones_by_id (
    zone_id text,
    zone_name text,
    capacity int,
    created_at timestamp,
    updated_at timestamp,
    PRIMARY KEY ((zone_id))
);

CREATE TABLE IF NOT EXISTS inventory_by_product_zone (
    product_id text,
    zone_id text,
    available_quantity int,
    reserved_quantity int,
    last_event_ts bigint,
    updated_at timestamp,
    PRIMARY KEY ((product_id, zone_id))
);

CREATE TABLE IF NOT EXISTS inventory_by_product (
    product_id text,
    zone_id text,
    available_quantity int,
    reserved_quantity int,
    last_event_ts bigint,
    updated_at timestamp,
    PRIMARY KEY ((product_id), zone_id)
);

CREATE TABLE IF NOT EXISTS inventory_by_zone (
    zone_id text,
    product_id text,
    available_quantity int,
    reserved_quantity int,
    last_event_ts bigint,
    updated_at timestamp,
    PRIMARY KEY ((zone_id), product_id)
);

CREATE TABLE IF NOT EXISTS inventory_totals_by_product (
    product_id text,
    total_available_quantity int,
    total_reserved_quantity int,
    last_aggregated_event_ts bigint,
    updated_at timestamp,
    PRIMARY KEY ((product_id))
);

CREATE TABLE IF NOT EXISTS orders_by_id (
    order_id text,
    status text,
    items list<frozen<order_item>>,
    created_at timestamp,
    updated_at timestamp,
    last_event_ts bigint,
    PRIMARY KEY ((order_id))
);

CREATE TABLE IF NOT EXISTS processed_events_by_id (
    event_id text,
    event_type text,
    processed_at timestamp,
    kafka_partition int,
    kafka_offset bigint,
    schema_variant text,
    PRIMARY KEY ((event_id))
);

CREATE TABLE IF NOT EXISTS event_history_by_day (
    event_date date,
    processed_at timestamp,
    event_id text,
    event_type text,
    outcome text,
    error_reason text,
    error_code text,
    schema_variant text,
    kafka_partition int,
    kafka_offset bigint,
    raw_payload text,
    PRIMARY KEY ((event_date), processed_at, event_id)
) WITH CLUSTERING ORDER BY (processed_at DESC, event_id ASC);

INSERT INTO zones_by_id (zone_id, zone_name, capacity, created_at, updated_at)
VALUES ('ZONE-A', 'Inbound / Picking Zone A', 10000, toTimestamp(now()), toTimestamp(now()));

INSERT INTO zones_by_id (zone_id, zone_name, capacity, created_at, updated_at)
VALUES ('ZONE-B', 'Reserve Zone B', 10000, toTimestamp(now()), toTimestamp(now()));

INSERT INTO zones_by_id (zone_id, zone_name, capacity, created_at, updated_at)
VALUES ('ZONE-C', 'Inventory Audit Zone C', 8000, toTimestamp(now()), toTimestamp(now()));
