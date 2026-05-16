from __future__ import annotations

import os
import time
from pathlib import Path

from cassandra import InvalidRequest
from cassandra.cluster import Cluster
from cassandra.policies import RoundRobinPolicy


def parse_statements(path: Path) -> list[str]:
    statements: list[str] = []
    current: list[str] = []
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("--"):
            continue
        current.append(raw_line)
        if line.endswith(";"):
            statements.append("\n".join(current).strip().rstrip(";"))
            current = []
    tail = "\n".join(current).strip()
    if tail:
        statements.append(tail.rstrip(";"))
    return statements


def main() -> None:
    contact_points = os.getenv("CASSANDRA_CONTACT_POINTS", "cassandra-1,cassandra-2,cassandra-3").split(",")
    port = int(os.getenv("CASSANDRA_PORT", "9042"))
    migration_dir = Path("/migrations")

    last_error: Exception | None = None
    cluster = None
    session = None
    for attempt in range(1, 31):
        try:
            cluster = Cluster(
                contact_points=contact_points,
                port=port,
                load_balancing_policy=RoundRobinPolicy(),
                protocol_version=5,
            )
            session = cluster.connect()
            session.execute("SELECT cluster_name FROM system.local")
            print(f"Connected to Cassandra on attempt {attempt}")
            break
        except Exception as exc:  # pragma: no cover - exercised only in container startup
            last_error = exc
            print(f"Cassandra not ready yet (attempt {attempt}/30): {exc}")
            time.sleep(5)
    else:
        raise RuntimeError("Could not connect to Cassandra cluster") from last_error

    try:
        for migration_path in sorted(migration_dir.glob("*.cql")):
            print(f"Applying migration {migration_path.name}")
            for statement in parse_statements(migration_path):
                try:
                    session.execute(statement)
                except InvalidRequest as exc:
                    if "already exists" in str(exc):
                        print(f"Skipping already-applied statement: {statement[:80]}...")
                        continue
                    raise
        print("All Cassandra migrations applied successfully")
    finally:
        session.shutdown()
        cluster.shutdown()


if __name__ == "__main__":
    main()
