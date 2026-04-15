from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.responses import JSONResponse
from starlette.requests import Request

from .api.routes import router
from .domain.exceptions import (
    DomainError, DuplicateActionError, NotFound, PlayerNotInHand, StaleStateError,
)
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

app = FastAPI(title="Game Service", lifespan=lifespan)
app.include_router(router)


@app.exception_handler(DomainError)
async def _domain_error_handler(_request: Request, exc: DomainError) -> JSONResponse:
    """Map domain exceptions to HTTP status codes at the API boundary."""
    if isinstance(exc, NotFound):
        status = 404
    elif isinstance(exc, PlayerNotInHand) and "not in this hand" in exc.message:
        status = 404
    elif isinstance(exc, StaleStateError):
        status = 409
    elif isinstance(exc, DuplicateActionError):
        status = 409
    else:
        status = 400
    return JSONResponse(status_code=status, content={"detail": exc.message})

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