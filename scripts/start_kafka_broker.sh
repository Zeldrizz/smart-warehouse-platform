#!/bin/bash
set -euo pipefail

BROKER_ID="${KAFKA_BROKER_ID:?KAFKA_BROKER_ID is required}"
ZK_CONNECT="${KAFKA_ZOOKEEPER_CONNECT:?KAFKA_ZOOKEEPER_CONNECT is required}"
BROKER_ZNODE="/brokers/ids/${BROKER_ID}"
MAX_WAIT_SECONDS="${KAFKA_STARTUP_MAX_WAIT_SECONDS:-90}"

wait_for_zookeeper() {
  local attempt=0

  while (( attempt < MAX_WAIT_SECONDS )); do
    if echo "ls /" | zookeeper-shell "${ZK_CONNECT}" >/tmp/zk_wait.log 2>&1; then
      return 0
    fi

    attempt=$((attempt + 2))
    sleep 2
  done

  echo "ZooKeeper did not become ready within ${MAX_WAIT_SECONDS}s" >&2
  cat /tmp/zk_wait.log >&2 || true
  return 1
}

cleanup_stale_broker_registration() {
  local delete_output

  delete_output="$(
    {
      echo "delete ${BROKER_ZNODE}"
    } | zookeeper-shell "${ZK_CONNECT}" 2>&1 || true
  )"

  echo "${delete_output}"
}

echo "Waiting for ZooKeeper at ${ZK_CONNECT}"
wait_for_zookeeper

echo "Cleaning stale broker znode ${BROKER_ZNODE} before Kafka startup"
cleanup_stale_broker_registration

exec /etc/confluent/docker/run
