from __future__ import annotations

import uuid
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.responses import Response

from .clients.service_client import auth_client, user_client, room_client, game_client
from .config import SERVICE_NAME
from .infrastructure.table_state_events import table_state_event_consumer
from .routes.auth_routes import router as auth_router
from .routes.user_routes import router as user_router
from .routes.room_routes import router as room_router
from .routes.player_routes import router as player_router
from .routes.game_routes import router as game_router
from .routes.round_routes import router as round_router
from .routes.bet_routes import router as bet_router

CORRELATION_HEADER = "X-Correlation-ID"

class GatewayCorrelationMiddleware(BaseHTTPMiddleware):

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        cid = request.headers.get(CORRELATION_HEADER) or str(uuid.uuid4())
        request.state.correlation_id = cid
        response = await call_next(request)
        response.headers[CORRELATION_HEADER] = cid
        return response

@asynccontextmanager
async def lifespan(app: FastAPI):
    await table_state_event_consumer.start()
    try:
        yield
    finally:
        await table_state_event_consumer.stop()
        for client in (auth_client, user_client, room_client, game_client):
            await client.close()

app = FastAPI(
    title="Poker Room API",
    version="0.1.0",
    description="Unified API gateway for the Poker Room platform.",
    lifespan=lifespan,
)
app.add_middleware(GatewayCorrelationMiddleware)

app.include_router(auth_router)
app.include_router(user_router)
app.include_router(room_router)
app.include_router(player_router)
app.include_router(game_router)
app.include_router(round_router)
app.include_router(bet_router)

@app.get("/health")
async def health():
    return {
        "status": "ok",
        "service": SERVICE_NAME,
        "table_state_events_enabled": table_state_event_consumer.enabled,
    }