from __future__ import annotations

from fastapi import FastAPI

from .config import SERVICE_NAME
from .routes.auth_routes import router as auth_router
from .routes.user_routes import router as user_router
from .routes.room_routes import router as room_router
from .routes.player_routes import router as player_router
from .routes.game_routes import router as game_router
from .routes.round_routes import router as round_router
from .routes.bet_routes import router as bet_router

app = FastAPI(title="Poker Room Gateway")

app.include_router(auth_router)
app.include_router(user_router)
app.include_router(room_router)
app.include_router(player_router)
app.include_router(game_router)
app.include_router(round_router)
app.include_router(bet_router)

@app.get("/health")
async def health():
    return {"status": "ok", "service": SERVICE_NAME}