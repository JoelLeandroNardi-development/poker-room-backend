from __future__ import annotations

from fastapi import APIRouter

from ..clients.service_client import game_client
from ..utils.proxy import forward_response

router = APIRouter(prefix="/bets", tags=["bets"])

@router.post("")
async def place_bet(body: dict):
    resp = await game_client.post("/bets", json=body)
    return forward_response(resp)

@router.get("/round/{round_id}")
async def get_bets_for_round(round_id: str):
    resp = await game_client.get(f"/bets/round/{round_id}")
    return forward_response(resp)

@router.get("/round/{round_id}/pot")
async def get_pot(round_id: str):
    resp = await game_client.get(f"/bets/round/{round_id}/pot")
    return forward_response(resp)

@router.get("/round/{round_id}/players")
async def get_player_summaries(round_id: str):
    resp = await game_client.get(f"/bets/round/{round_id}/players")
    return forward_response(resp)