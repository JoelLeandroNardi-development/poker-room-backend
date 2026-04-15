from __future__ import annotations

from fastapi import APIRouter

from ..clients.service_client import room_client
from ..utils.proxy import forward_response
from shared.schemas.rooms import RoomPlayerResponse, UpdateChips

router = APIRouter(prefix="/players", tags=["players"])

@router.get("/{player_id}", response_model=RoomPlayerResponse)
async def get_player(player_id: str):
    resp = await room_client.get(f"/players/{player_id}")
    return forward_response(resp)

@router.put("/{player_id}/chips", response_model=RoomPlayerResponse)
async def update_player_chips(player_id: str, data: UpdateChips):
    resp = await room_client.put(f"/players/{player_id}/chips", json=data.model_dump())
    return forward_response(resp)

@router.post("/{player_id}/eliminate", response_model=RoomPlayerResponse)
async def eliminate_player(player_id: str):
    resp = await room_client.post(f"/players/{player_id}/eliminate")
    return forward_response(resp)