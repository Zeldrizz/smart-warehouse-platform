"""Cassandra repository for warehouse state projections."""

from __future__ import annotations

import logging
import time
from collections import namedtuple
from datetime import UTC, date, datetime

from cassandra import ConsistencyLevel
from cassandra.cluster import BatchStatement, Cluster
from cassandra.policies import RoundRobinPolicy
from cassandra.query import BatchType, dict_factory

from app.config import settings
from app.domain.models import EventContext, InventoryKey, InventoryState, OrderItemData, OrderState, ProductTotalsState, ZoneInfo
from app.metrics import cassandra_write_errors_total

logger = logging.getLogger(__name__)

OrderItemUDT = namedtuple("OrderItemUDT", ["product_id", "zone_id", "quantity"])


class WarehouseRepository:
    """Thin Cassandra repository with QUORUM reads/writes."""

    def __init__(self) -> None:
        self._cluster: Cluster | None = None
        self._session = None
        self._connect_with_retry()
        self._prepare_statements()

    def _connect_with_retry(self) -> None:
        last_error: Exception | None = None
        contact_points = settings.cassandra_contact_points.split(",")
        for attempt in range(1, 31):
            try:
                cluster = Cluster(
                    contact_points=contact_points,
                    port=settings.cassandra_port,
                    load_balancing_policy=RoundRobinPolicy(),
                    protocol_version=5,
                )
                cluster.register_user_type(settings.cassandra_keyspace, "order_item", OrderItemUDT)
                session = cluster.connect()
                session.row_factory = dict_factory
                session.execute("SELECT release_version FROM system.local")
                self._cluster = cluster
                self._session = session
                logger.info("Connected to Cassandra keyspace=%s", settings.cassandra_keyspace)
                return
            except Exception as exc:
                last_error = exc
                logger.warning("Cassandra connection attempt %s/30 failed: %s", attempt, exc)
                time.sleep(3)
        raise RuntimeError("Unable to connect to Cassandra") from last_error

    def _prepare(self, query: str):
        statement = self._session.prepare(query)
        statement.consistency_level = ConsistencyLevel.QUORUM
        return statement

    def _prepare_statements(self) -> None:
        self._get_zone_stmt = self._prepare(
            "SELECT zone_id, zone_name, capacity "
            f"FROM {settings.cassandra_keyspace}.zones_by_id WHERE zone_id = ?"
        )
        self._get_inventory_stmt = self._prepare(
            "SELECT product_id, zone_id, available_quantity, reserved_quantity, "
            "last_event_ts, supplier_id, updated_at "
            f"FROM {settings.cassandra_keyspace}.inventory_by_product_zone WHERE product_id = ? AND zone_id = ?"
        )
        self._get_zone_inventory_stmt = self._prepare(
            "SELECT zone_id, product_id, available_quantity, reserved_quantity, "
            "last_event_ts, supplier_id, updated_at "
            f"FROM {settings.cassandra_keyspace}.inventory_by_zone WHERE zone_id = ?"
        )
        self._get_total_stmt = self._prepare(
            "SELECT product_id, total_available_quantity, total_reserved_quantity, "
            "last_aggregated_event_ts, updated_at "
            f"FROM {settings.cassandra_keyspace}.inventory_totals_by_product WHERE product_id = ?"
        )
        self._get_order_stmt = self._prepare(
            "SELECT order_id, status, items, created_at, updated_at, last_event_ts "
            f"FROM {settings.cassandra_keyspace}.orders_by_id WHERE order_id = ?"
        )
        self._is_processed_stmt = self._prepare(
            f"SELECT event_id FROM {settings.cassandra_keyspace}.processed_events_by_id WHERE event_id = ?"
        )
        self._upsert_product_zone_stmt = self._prepare(
            f"INSERT INTO {settings.cassandra_keyspace}.inventory_by_product_zone "
            "(product_id, zone_id, available_quantity, reserved_quantity, last_event_ts, supplier_id, updated_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)"
        )
        self._upsert_by_product_stmt = self._prepare(
            f"INSERT INTO {settings.cassandra_keyspace}.inventory_by_product "
            "(product_id, zone_id, available_quantity, reserved_quantity, last_event_ts, supplier_id, updated_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)"
        )
        self._upsert_by_zone_stmt = self._prepare(
            f"INSERT INTO {settings.cassandra_keyspace}.inventory_by_zone "
            "(zone_id, product_id, available_quantity, reserved_quantity, last_event_ts, supplier_id, updated_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)"
        )
        self._upsert_total_stmt = self._prepare(
            f"INSERT INTO {settings.cassandra_keyspace}.inventory_totals_by_product "
            "(product_id, total_available_quantity, total_reserved_quantity, last_aggregated_event_ts, updated_at) "
            "VALUES (?, ?, ?, ?, ?)"
        )
        self._upsert_order_stmt = self._prepare(
            f"INSERT INTO {settings.cassandra_keyspace}.orders_by_id "
            "(order_id, status, items, created_at, updated_at, last_event_ts) "
            "VALUES (?, ?, ?, ?, ?, ?)"
        )
        self._insert_processed_stmt = self._prepare(
            f"INSERT INTO {settings.cassandra_keyspace}.processed_events_by_id "
            "(event_id, event_type, processed_at, kafka_partition, kafka_offset, schema_variant) "
            "VALUES (?, ?, ?, ?, ?, ?)"
        )
        self._insert_history_stmt = self._prepare(
            f"INSERT INTO {settings.cassandra_keyspace}.event_history_by_day "
            "(event_date, processed_at, event_id, event_type, outcome, error_reason, error_code, "
            "schema_variant, kafka_partition, kafka_offset, raw_payload, occurred_at_ms) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)"
        )
        self._select_history_stmt = self._prepare(
            f"SELECT event_id, event_type, outcome, error_code, error_reason, occurred_at_ms "
            f"FROM {settings.cassandra_keyspace}.event_history_by_day WHERE event_date = ?"
        )

    def healthcheck(self) -> bool:
        try:
            self._session.execute("SELECT release_version FROM system.local")
            return True
        except Exception as exc:
            logger.warning("Cassandra healthcheck failed: %s", exc)
            return False

    def get_zone(self, zone_id: str) -> ZoneInfo | None:
        row = self._session.execute(self._get_zone_stmt, (zone_id,)).one()
        if not row:
            return None
        return ZoneInfo(zone_id=row["zone_id"], zone_name=row["zone_name"], capacity=row["capacity"])

    def get_inventory(self, key: InventoryKey) -> InventoryState | None:
        row = self._session.execute(self._get_inventory_stmt, (key.product_id, key.zone_id)).one()
        if not row:
            return None
        return InventoryState(
            product_id=row["product_id"],
            zone_id=row["zone_id"],
            available_quantity=row["available_quantity"],
            reserved_quantity=row["reserved_quantity"],
            last_event_ts=row["last_event_ts"],
            supplier_id=row.get("supplier_id"),
            updated_at=row["updated_at"],
        )

    def get_zone_inventory(self, zone_id: str) -> list[InventoryState]:
        rows = self._session.execute(self._get_zone_inventory_stmt, (zone_id,))
        return [
            InventoryState(
                product_id=row["product_id"],
                zone_id=row["zone_id"],
                available_quantity=row["available_quantity"],
                reserved_quantity=row["reserved_quantity"],
                last_event_ts=row["last_event_ts"],
                supplier_id=row.get("supplier_id"),
                updated_at=row["updated_at"],
            )
            for row in rows
        ]

    def get_product_total(self, product_id: str) -> ProductTotalsState | None:
        row = self._session.execute(self._get_total_stmt, (product_id,)).one()
        if not row:
            return None
        return ProductTotalsState(
            product_id=row["product_id"],
            total_available_quantity=row["total_available_quantity"],
            total_reserved_quantity=row["total_reserved_quantity"],
            last_aggregated_event_ts=row["last_aggregated_event_ts"],
            updated_at=row["updated_at"],
        )

    def get_order(self, order_id: str) -> OrderState | None:
        row = self._session.execute(self._get_order_stmt, (order_id,)).one()
        if not row:
            return None
        items = [
            OrderItemData(
                product_id=getattr(item, "product_id", item[0] if isinstance(item, tuple) else item["product_id"]),
                zone_id=getattr(item, "zone_id", item[1] if isinstance(item, tuple) else item["zone_id"]),
                quantity=getattr(item, "quantity", item[2] if isinstance(item, tuple) else item["quantity"]),
            )
            for item in row["items"]
        ]
        return OrderState(
            order_id=row["order_id"],
            status=row["status"],
            items=items,
            created_at=row["created_at"],
            updated_at=row["updated_at"],
            last_event_ts=row["last_event_ts"],
        )

    def is_event_processed(self, event_id: str) -> bool:
        return self._session.execute(self._is_processed_stmt, (event_id,)).one() is not None

    def get_event_history_for_date(self, target_date: date) -> list[dict]:
        rows = self._session.execute(self._select_history_stmt, (target_date,))
        return list(rows)

    def apply_state_change(
        self,
        inventory_rows: list[InventoryState],
        total_rows: list[ProductTotalsState],
        order_state: OrderState | None,
        context: EventContext,
        outcome: str,
        error_code: str | None = None,
        error_reason: str | None = None,
    ) -> None:
        processed_at = datetime.now(UTC)
        batch = BatchStatement(batch_type=BatchType.LOGGED, consistency_level=ConsistencyLevel.QUORUM)
        for row in inventory_rows:
            values = (
                row.product_id,
                row.zone_id,
                row.available_quantity,
                row.reserved_quantity,
                row.last_event_ts,
                row.supplier_id,
                row.updated_at,
            )
            batch.add(self._upsert_product_zone_stmt, values)
            batch.add(self._upsert_by_product_stmt, values)
            batch.add(
                self._upsert_by_zone_stmt,
                (
                    row.zone_id,
                    row.product_id,
                    row.available_quantity,
                    row.reserved_quantity,
                    row.last_event_ts,
                    row.supplier_id,
                    row.updated_at,
                ),
            )
        for total in total_rows:
            batch.add(
                self._upsert_total_stmt,
                (
                    total.product_id,
                    total.total_available_quantity,
                    total.total_reserved_quantity,
                    total.last_aggregated_event_ts,
                    total.updated_at,
                ),
            )
        if order_state is not None:
            batch.add(
                self._upsert_order_stmt,
                (
                    order_state.order_id,
                    order_state.status,
                    [OrderItemUDT(item.product_id, item.zone_id, item.quantity) for item in order_state.items],
                    order_state.created_at,
                    order_state.updated_at,
                    order_state.last_event_ts,
                ),
            )
        batch.add(
            self._insert_processed_stmt,
            (
                context.event_id,
                context.event_type,
                processed_at,
                context.metadata.partition,
                context.metadata.offset,
                context.schema_variant,
            ),
        )
        batch.add(
            self._insert_history_stmt,
            (
                datetime.fromtimestamp(context.occurred_at / 1000, UTC).date(),
                processed_at,
                context.event_id,
                context.event_type,
                outcome,
                error_reason,
                error_code,
                context.schema_variant,
                context.metadata.partition,
                context.metadata.offset,
                context.raw_json,
                context.occurred_at,
            ),
        )
        try:
            self._session.execute(batch)
        except Exception:
            cassandra_write_errors_total.inc()
            raise

    def close(self) -> None:
        if self._session is not None:
            self._session.shutdown()
        if self._cluster is not None:
            self._cluster.shutdown()

