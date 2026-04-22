from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from ...application.commands.bet_command_service import BetCommandService
from ...infrastructure.db import SessionLocal
from shared.schemas.bets import PlaceBet, BetResponse
from shared.core.db.session import make_get_db

bet_command_router = APIRouter()
get_db = make_get_db(SessionLocal)

@bet_command_router.post("/bets", response_model=BetResponse)
async def place_bet(data: PlaceBet, db: AsyncSession = Depends(get_db)):
    return await BetCommandService(db).place_bet(data)