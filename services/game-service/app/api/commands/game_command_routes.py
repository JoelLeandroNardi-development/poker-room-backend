from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from ...application.commands.game_command_service import GameCommandService
from ...domain.schemas import (
    StartGame, StartRoundRequest, GameResponse, RoundResponse, DeclareWinner, DeclareWinnerResponse, ResolveHandRequest, 
    ResolveHandResponse, AdvanceBlindsResponse, AdvanceStreetResponse, EndGameResponse,
)
from ...infrastructure.db import SessionLocal
from shared.core.db.session import make_get_db

game_command_router = APIRouter()
get_db = make_get_db(SessionLocal)

@game_command_router.post("/games", response_model=GameResponse)
async def start_game(data: StartGame, db: AsyncSession = Depends(get_db)):
    return await GameCommandService(db).start_game(data)

@game_command_router.post("/games/{game_id}/rounds", response_model=RoundResponse)
async def start_round(game_id: str, data: StartRoundRequest, db: AsyncSession = Depends(get_db)):
    return await GameCommandService(db).start_round(game_id, data)

@game_command_router.post("/rounds/{round_id}/resolve", response_model=ResolveHandResponse)
async def resolve_hand(round_id: str, data: ResolveHandRequest, db: AsyncSession = Depends(get_db)):
    return await GameCommandService(db).resolve_hand(round_id, data)

@game_command_router.post("/rounds/{round_id}/advance-street", response_model=AdvanceStreetResponse)
async def advance_street(round_id: str, db: AsyncSession = Depends(get_db)):
    return await GameCommandService(db).advance_street(round_id)

@game_command_router.post("/rounds/{round_id}/winner", response_model=DeclareWinnerResponse)
async def declare_winner(round_id: str, data: DeclareWinner, db: AsyncSession = Depends(get_db)):
    return await GameCommandService(db).declare_winner(round_id, data)

@game_command_router.post("/games/{game_id}/advance-blinds", response_model=AdvanceBlindsResponse)
async def advance_blinds(game_id: str, db: AsyncSession = Depends(get_db)):
    return await GameCommandService(db).advance_blinds(game_id)

@game_command_router.post("/games/{game_id}/end", response_model=EndGameResponse)
async def end_game(game_id: str, db: AsyncSession = Depends(get_db)):
    return await GameCommandService(db).end_game(game_id)