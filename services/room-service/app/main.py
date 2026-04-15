from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
from fastapi import FastAPI

from .api.routes import router
from .infrastructure.config import SERVICE_LOG_PREFIX, SERVICE_NAME
from .infrastructure.messaging import publisher, RABBIT_URL, EXCHANGE_NAME
from .infrastructure.outbox_worker import run_outbox_forever, outbox_stats

_stop = asyncio.Event()
_outbox_task: asyncio.Task | None = None

@asynccontextmanager
async def lifespan(app: FastAPI):
    global _outbox_task

    print(f"{SERVICE_LOG_PREFIX} starting up...")

    try:
        await publisher.start()
    except Exception as e:
        print(f"{SERVICE_LOG_PREFIX} publisher start failed (ok): {type(e).__name__}: {e}")

    _outbox_task = asyncio.create_task(run_outbox_forever(_stop))

    yield

    print(f"{SERVICE_LOG_PREFIX} shutting down...")
    _stop.set()

    if _outbox_task:
        _outbox_task.cancel()

    try:
        await publisher.close()
    except Exception:
        pass

app = FastAPI(title="Room Service", lifespan=lifespan)
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