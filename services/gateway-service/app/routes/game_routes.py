from __future__ import annotations

from fastapi import APIRouter

from ..clients.service_client import game_client
from ..utils.proxy import forward_response

router = APIRouter(prefix="/games", tags=["games"])


@router.post("")
async def start_game(body: dict):
    resp = await game_client.post("/games", json=body)
    return forward_response(resp)


@router.get("/{game_id}")
async def get_game(game_id: str):
    resp = await game_client.get(f"/games/{game_id}")
    return forward_response(resp)


@router.get("/room/{room_id}")
async def get_game_for_room(room_id: str):
    resp = await game_client.get(f"/games/room/{room_id}")
    return forward_response(resp)


@router.post("/{game_id}/rounds")
async def start_round(game_id: str):
    resp = await game_client.post(f"/games/{game_id}/rounds")
    return forward_response(resp)


@router.get("/{game_id}/rounds")
async def list_rounds(game_id: str):
    resp = await game_client.get(f"/games/{game_id}/rounds")
    return forward_response(resp)


@router.get("/{game_id}/rounds/active")
async def get_active_round(game_id: str):
    resp = await game_client.get(f"/games/{game_id}/rounds/active")
    return forward_response(resp)


@router.post("/{game_id}/advance-blinds")
async def advance_blinds(game_id: str):
    resp = await game_client.post(f"/games/{game_id}/advance-blinds")
    return forward_response(resp)


@router.post("/{game_id}/end")
async def end_game(game_id: str):
    resp = await game_client.post(f"/games/{game_id}/end")
    return forward_response(resp)
