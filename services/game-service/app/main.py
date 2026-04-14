from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
from fastapi import FastAPI

from .api.routes import router
from .infrastructure.config import (
    CONSUMER_RECONNECT_WAIT_SECONDS, QUEUE_NAME, ROUTING_KEYS,
    SERVICE_LOG_PREFIX, SERVICE_NAME,
)
from .infrastructure.event_consumer import start_consumer
from .infrastructure.messaging import publisher, RABBIT_URL, EXCHANGE_NAME
from .infrastructure.outbox_worker import run_outbox_forever, outbox_stats

_stop = asyncio.Event()
_consumer_conn = None
_outbox_task: asyncio.Task | None = None
_consumer_task: asyncio.Task | None = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    global _consumer_conn, _outbox_task, _consumer_task

    print(f"{SERVICE_LOG_PREFIX} starting up...")

    try:
        await publisher.start()
    except Exception as e:
        print(f"{SERVICE_LOG_PREFIX} publisher start failed (ok): {type(e).__name__}: {e}")

    _outbox_task = asyncio.create_task(run_outbox_forever(_stop))

    async def consumer_with_retry():
        global _consumer_conn
        while not _stop.is_set():
            try:
                _consumer_conn = await start_consumer()
                return
            except Exception as e:
                print(
                    f"{SERVICE_LOG_PREFIX} consumer connect failed, retrying in "
                    f"{CONSUMER_RECONNECT_WAIT_SECONDS}s: {e}"
                )
                try:
                    await asyncio.wait_for(_stop.wait(), timeout=CONSUMER_RECONNECT_WAIT_SECONDS)
                except asyncio.TimeoutError:
                    continue

    _consumer_task = asyncio.create_task(consumer_with_retry())

    yield

    print(f"{SERVICE_LOG_PREFIX} shutting down...")
    _stop.set()

    if _outbox_task:
        _outbox_task.cancel()

    if _consumer_task:
        _consumer_task.cancel()

    try:
        if _consumer_conn and not _consumer_conn.is_closed:
            await _consumer_conn.close()
    except Exception:
        pass

    try:
        await publisher.close()
    except Exception:
        pass


app = FastAPI(title="Game Service", lifespan=lifespan)
app.include_router(router)


@app.get("/health", response_model=dict[str, object])
async def health():
    return {
        "status": "ok",
        "service": SERVICE_NAME,
        "events_enabled": publisher.enabled,
        "exchange_name": EXCHANGE_NAME,
        "rabbit_url_set": bool(RABBIT_URL),
        "outbox": await outbox_stats(),
    }


@app.get("/debug/rabbit", response_model=dict[str, object])
async def debug_rabbit():
    return {
        "service": SERVICE_NAME,
        "rabbit_url_set": bool(RABBIT_URL),
        "exchange_name": EXCHANGE_NAME,
        "consumer": {
            "queue_name": QUEUE_NAME,
            "routing_keys": ROUTING_KEYS,
        },
    }
