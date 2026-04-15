from __future__ import annotations

from fastapi import APIRouter

from ..clients.service_client import room_client
from ..utils.proxy import forward_response

router = APIRouter(prefix="/players", tags=["players"])

@router.get("/{player_id}")
async def get_player(player_id: str):
    resp = await room_client.get(f"/players/{player_id}")
    return forward_response(resp)

@router.put("/{player_id}/chips")
async def update_player_chips(player_id: str, body: dict):
    resp = await room_client.put(f"/players/{player_id}/chips", json=body)
    return forward_response(resp)

@router.post("/{player_id}/eliminate")
async def eliminate_player(player_id: str):
    resp = await room_client.post(f"/players/{player_id}/eliminate")
    return forward_response(resp)