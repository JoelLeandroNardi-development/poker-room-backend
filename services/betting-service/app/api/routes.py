from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from ..application.commands.bet_command_service import BetCommandService
from ..application.queries.bet_query_service import BetQueryService
from ..domain.schemas import BetResponse, PlaceBet, PotResponse, PlayerBetSummary
from ..infrastructure.db import SessionLocal
from shared.core.db.session import make_get_db

router = APIRouter()
get_db = make_get_db(SessionLocal)


@router.post("/bets", response_model=BetResponse)
async def place_bet(data: PlaceBet, db: AsyncSession = Depends(get_db)):
    return await BetCommandService(db).place_bet(data)


@router.get("/bets/round/{round_id}", response_model=list[BetResponse])
async def get_bets_for_round(round_id: str, db: AsyncSession = Depends(get_db)):
    return await BetQueryService(db).get_bets_for_round(round_id)


@router.get("/bets/round/{round_id}/pot", response_model=PotResponse)
async def get_pot(round_id: str, db: AsyncSession = Depends(get_db)):
    return await BetQueryService(db).get_pot(round_id)


@router.get("/bets/round/{round_id}/players", response_model=list[PlayerBetSummary])
async def get_player_summaries(round_id: str, db: AsyncSession = Depends(get_db)):
    return await BetQueryService(db).get_player_summaries(round_id)
