from __future__ import annotations

from fastapi import APIRouter, Query

from ..clients.service_client import room_client
from ..utils.proxy import forward_response
from shared.schemas.rooms import (
    CreateRoom, JoinRoom, SetBlindStructure, UpdateChips,
    RoomResponse, RoomDetailResponse, RoomPlayerResponse, DeleteRoomResponse,
    ReorderSeats,
)

router = APIRouter(prefix="/rooms", tags=["rooms"])

@router.post("", response_model=RoomResponse)
async def create_room(data: CreateRoom):
    resp = await room_client.post("/rooms", json=data.model_dump())
    return forward_response(resp)

@router.get("/{room_id}", response_model=RoomDetailResponse)
async def get_room(room_id: str):
    resp = await room_client.get(f"/rooms/{room_id}")
    return forward_response(resp)

@router.get("/code/{code}", response_model=RoomDetailResponse)
async def get_room_by_code(code: str):
    resp = await room_client.get(f"/rooms/code/{code}")
    return forward_response(resp)

@router.get("", response_model=list[RoomResponse])
async def list_rooms(
    limit: int = Query(50, ge=1, le=500),
    offset: int = Query(0, ge=0),
    status: str | None = Query(default=None),
):
    params = {"limit": limit, "offset": offset}
    if status:
        params["status"] = status
    resp = await room_client.get("/rooms", params=params)
    return forward_response(resp)

@router.post("/join/{code}", response_model=RoomPlayerResponse)
async def join_room(code: str, data: JoinRoom):
    resp = await room_client.post(f"/rooms/join/{code}", json=data.model_dump())
    return forward_response(resp)

@router.put("/{room_id}/blinds", response_model=RoomDetailResponse)
async def set_blind_structure(room_id: str, data: SetBlindStructure):
    resp = await room_client.put(f"/rooms/{room_id}/blinds", json=data.model_dump())
    return forward_response(resp)

@router.put("/{room_id}/seats", response_model=RoomDetailResponse)
async def reorder_seats(room_id: str, data: ReorderSeats):
    resp = await room_client.put(f"/rooms/{room_id}/seats", json=data.model_dump())
    return forward_response(resp)

@router.delete("/{room_id}", response_model=DeleteRoomResponse)
async def delete_room(room_id: str):
    resp = await room_client.delete(f"/rooms/{room_id}")
    return forward_response(resp)