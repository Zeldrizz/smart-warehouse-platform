"""FastAPI application for the WMS producer service."""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.api.routes import bind_runtime, router, system_router
from app.metrics import install_http_metrics
from app.runtime import WMSRuntime

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)


runtime: WMSRuntime | None = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    global runtime
    runtime = WMSRuntime.build()
    bind_runtime(runtime)
    runtime.generator.start()
    yield
    if runtime is not None:
        await runtime.generator.stop()
        runtime.producer.flush()


app = FastAPI(
    title="Smart Warehouse WMS Service",
    description="HTTP API that publishes warehouse events to Kafka with Avro schemas",
    version="1.0.0",
    lifespan=lifespan,
)
install_http_metrics(app, "wms-service")
app.include_router(router)
app.include_router(system_router)
