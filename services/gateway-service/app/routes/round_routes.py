from __future__ import annotations

from fastapi import APIRouter

from ..clients.service_client import game_client
from ..utils.proxy import forward_response

router = APIRouter(prefix="/rounds", tags=["rounds"])

@router.get("/{round_id}")
async def get_round(round_id: str):
    resp = await game_client.get(f"/rounds/{round_id}")
    return forward_response(resp)

@router.post("/{round_id}/winner")
async def declare_winner(round_id: str, body: dict):
    resp = await game_client.post(f"/rounds/{round_id}/winner", json=body)
    return forward_response(resp)