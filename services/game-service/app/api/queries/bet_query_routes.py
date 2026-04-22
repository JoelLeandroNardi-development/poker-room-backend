from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from ...application.queries.bet_query_service import BetQueryService
from ...infrastructure.db import SessionLocal
from shared.schemas.bets import BetResponse, PotResponse, PlayerBetSummary
from shared.core.db.session import make_get_db

bet_query_router = APIRouter()
get_db = make_get_db(SessionLocal)

@bet_query_router.get("/bets/round/{round_id}", response_model=list[BetResponse])
async def get_bets_for_round(round_id: str, db: AsyncSession = Depends(get_db)):
    return await BetQueryService(db).get_bets_for_round(round_id)

@bet_query_router.get("/bets/round/{round_id}/pot", response_model=PotResponse)
async def get_pot(round_id: str, db: AsyncSession = Depends(get_db)):
    return await BetQueryService(db).get_pot(round_id)

@bet_query_router.get("/bets/round/{round_id}/players", response_model=list[PlayerBetSummary])
async def get_player_summaries(round_id: str, db: AsyncSession = Depends(get_db)):
    return await BetQueryService(db).get_player_summaries(round_id)