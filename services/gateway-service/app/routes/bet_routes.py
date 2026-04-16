from __future__ import annotations

from fastapi import APIRouter

from ..clients.service_client import game_client
from ..utils.proxy import forward_response
from shared.schemas.bets import PlaceBet, BetResponse, PotResponse, PlayerBetSummary

router = APIRouter(prefix="/bets", tags=["bets"])

@router.post("", response_model=BetResponse)
async def place_bet(data: PlaceBet):
    resp = await game_client.post("/bets", json=data.model_dump(exclude_none=True))
    return forward_response(resp)

@router.get("/round/{round_id}", response_model=list[BetResponse])
async def get_bets_for_round(round_id: str):
    resp = await game_client.get(f"/bets/round/{round_id}")
    return forward_response(resp)

@router.get("/round/{round_id}/pot", response_model=PotResponse)
async def get_pot(round_id: str):
    resp = await game_client.get(f"/bets/round/{round_id}/pot")
    return forward_response(resp)

@router.get("/round/{round_id}/players", response_model=list[PlayerBetSummary])
async def get_player_summaries(round_id: str):
    resp = await game_client.get(f"/bets/round/{round_id}/players")
    return forward_response(resp)
