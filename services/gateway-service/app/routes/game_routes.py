from __future__ import annotations

from fastapi import APIRouter

from ..clients.service_client import game_client
from ..utils.proxy import forward_response
from shared.schemas.games import (
    StartGame, GameResponse, RoundResponse,
    AdvanceBlindsResponse, EndGameResponse,
)

router = APIRouter(prefix="/games", tags=["games"])

@router.post("", response_model=GameResponse)
async def start_game(data: StartGame):
    resp = await game_client.post("/games", json=data.model_dump())
    return forward_response(resp)

@router.get("/{game_id}", response_model=GameResponse)
async def get_game(game_id: str):
    resp = await game_client.get(f"/games/{game_id}")
    return forward_response(resp)

@router.get("/room/{room_id}", response_model=GameResponse | None)
async def get_game_for_room(room_id: str):
    resp = await game_client.get(f"/games/room/{room_id}")
    return forward_response(resp)

@router.post("/{game_id}/rounds", response_model=RoundResponse)
async def start_round(game_id: str):
    resp = await game_client.post(f"/games/{game_id}/rounds")
    return forward_response(resp)

@router.get("/{game_id}/rounds", response_model=list[RoundResponse])
async def list_rounds(game_id: str):
    resp = await game_client.get(f"/games/{game_id}/rounds")
    return forward_response(resp)

@router.get("/{game_id}/rounds/active", response_model=RoundResponse | None)
async def get_active_round(game_id: str):
    resp = await game_client.get(f"/games/{game_id}/rounds/active")
    return forward_response(resp)

@router.post("/{game_id}/advance-blinds", response_model=AdvanceBlindsResponse)
async def advance_blinds(game_id: str):
    resp = await game_client.post(f"/games/{game_id}/advance-blinds")
    return forward_response(resp)

@router.post("/{game_id}/end", response_model=EndGameResponse)
async def end_game(game_id: str):
    resp = await game_client.post(f"/games/{game_id}/end")
    return forward_response(resp)