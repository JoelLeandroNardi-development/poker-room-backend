from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.responses import JSONResponse
from starlette.requests import Request

from .api.routes import router
from .domain.exceptions import (
    DomainError, DuplicateActionError, IdempotencyConflict,
    NotFound, PlayerNotInHand, StaleStateError,
)
from .infrastructure.config import SERVICE_NAME
from .infrastructure.logging import configure_logging, get_logger
from .infrastructure.middleware import CorrelationIdMiddleware
from .infrastructure.messaging import publisher, RABBIT_URL, EXCHANGE_NAME
from .infrastructure.outbox_worker import run_outbox_forever, outbox_stats

configure_logging()
logger = get_logger("game-service")

_stop = asyncio.Event()
_outbox_task: asyncio.Task | None = None

@asynccontextmanager
async def lifespan(app: FastAPI):
    global _outbox_task

    logger.info("starting up", service=SERVICE_NAME)

    try:
        await publisher.start()
    except Exception as e:
        logger.warning(f"publisher start failed (ok): {type(e).__name__}: {e}", service=SERVICE_NAME)

    _outbox_task = asyncio.create_task(run_outbox_forever(_stop))

    yield

    logger.info("shutting down", service=SERVICE_NAME)
    _stop.set()

    if _outbox_task:
        _outbox_task.cancel()

    try:
        await publisher.close()
    except Exception:
        pass

app = FastAPI(title="Game Service", lifespan=lifespan)
app.add_middleware(CorrelationIdMiddleware)
app.include_router(router)

@app.exception_handler(DomainError)
async def _domain_error_handler(_request: Request, exc: DomainError) -> JSONResponse:
    if isinstance(exc, NotFound):
        status = 404
    elif isinstance(exc, PlayerNotInHand) and "not in this hand" in exc.message:
        status = 404
    elif isinstance(exc, StaleStateError):
        status = 409
        logger.warning("stale state rejection", error=exc.message)
    elif isinstance(exc, DuplicateActionError):
        status = 409
        logger.warning("duplicate action rejected", error=exc.message)
    elif isinstance(exc, IdempotencyConflict):
        status = 409
        logger.warning("idempotency conflict", error=exc.message)
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