from __future__ import annotations

from fastapi import APIRouter, Query

from ..clients.service_client import room_client
from ..utils.proxy import forward_response

router = APIRouter(prefix="/rooms", tags=["rooms"])

@router.post("")
async def create_room(body: dict):
    resp = await room_client.post("/rooms", json=body)
    return forward_response(resp)

@router.get("/{room_id}")
async def get_room(room_id: str):
    resp = await room_client.get(f"/rooms/{room_id}")
    return forward_response(resp)

@router.get("/code/{code}")
async def get_room_by_code(code: str):
    resp = await room_client.get(f"/rooms/code/{code}")
    return forward_response(resp)

@router.get("")
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

@router.post("/join/{code}")
async def join_room(code: str, body: dict):
    resp = await room_client.post(f"/rooms/join/{code}", json=body)
    return forward_response(resp)

@router.put("/{room_id}/blinds")
async def set_blind_structure(room_id: str, body: dict):
    resp = await room_client.put(f"/rooms/{room_id}/blinds", json=body)
    return forward_response(resp)

@router.delete("/{room_id}")
async def delete_room(room_id: str):
    resp = await room_client.delete(f"/rooms/{room_id}")
    return forward_response(resp)