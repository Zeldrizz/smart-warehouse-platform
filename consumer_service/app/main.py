"""FastAPI app hosting the consumer health and analytics endpoints."""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.api.routes import bind_runtime, router
from app.metrics import initialize_consumer_metric_series, install_http_metrics
from app.runtime import ConsumerRuntime

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)

runtime: ConsumerRuntime | None = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    global runtime
    runtime = ConsumerRuntime.build()
    bind_runtime(runtime)
    runtime.worker.start()
    yield
    if runtime is not None:
        runtime.worker.stop()
        runtime.dlq_producer.close()
        runtime.repository.close()


app = FastAPI(
    title="Smart Warehouse Consumer Service",
    description="Stateful Kafka consumer that projects warehouse state to Cassandra",
    version="1.0.0",
    lifespan=lifespan,
)
install_http_metrics(app, "consumer-service")
initialize_consumer_metric_series()
app.include_router(router)
