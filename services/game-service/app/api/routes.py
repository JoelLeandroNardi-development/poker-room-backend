from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from ..application.commands.game_command_service import GameCommandService
from ..application.queries.game_query_service import GameQueryService
from ..domain.schemas import (
    StartGame, GameResponse, RoundResponse,
    DeclareWinner, DeclareWinnerResponse,
    AdvanceBlindsResponse, EndGameResponse,
)
from ..infrastructure.db import SessionLocal
from shared.core.db.session import make_get_db

router = APIRouter()
get_db = make_get_db(SessionLocal)


@router.post("/games", response_model=GameResponse)
async def start_game(data: StartGame, db: AsyncSession = Depends(get_db)):
    return await GameCommandService(db).start_game(data)


@router.get("/games/{game_id}", response_model=GameResponse)
async def get_game(game_id: str, db: AsyncSession = Depends(get_db)):
    return await GameQueryService(db).get_game(game_id)


@router.get("/games/room/{room_id}", response_model=GameResponse | None)
async def get_game_for_room(room_id: str, db: AsyncSession = Depends(get_db)):
    return await GameQueryService(db).get_game_for_room(room_id)


@router.post("/games/{game_id}/rounds", response_model=RoundResponse)
async def start_round(game_id: str, db: AsyncSession = Depends(get_db)):
    return await GameCommandService(db).start_round(game_id)


@router.get("/games/{game_id}/rounds", response_model=list[RoundResponse])
async def list_rounds(game_id: str, db: AsyncSession = Depends(get_db)):
    return await GameQueryService(db).list_rounds(game_id)


@router.get("/games/{game_id}/rounds/active", response_model=RoundResponse | None)
async def get_active_round(game_id: str, db: AsyncSession = Depends(get_db)):
    return await GameQueryService(db).get_active_round(game_id)


@router.get("/rounds/{round_id}", response_model=RoundResponse)
async def get_round(round_id: str, db: AsyncSession = Depends(get_db)):
    return await GameQueryService(db).get_round(round_id)


@router.post("/rounds/{round_id}/winner", response_model=DeclareWinnerResponse)
async def declare_winner(round_id: str, data: DeclareWinner, db: AsyncSession = Depends(get_db)):
    return await GameCommandService(db).declare_winner(round_id, data)


@router.post("/games/{game_id}/advance-blinds", response_model=AdvanceBlindsResponse)
async def advance_blinds(game_id: str, db: AsyncSession = Depends(get_db)):
    return await GameCommandService(db).advance_blinds(game_id)


@router.post("/games/{game_id}/end", response_model=EndGameResponse)
async def end_game(game_id: str, db: AsyncSession = Depends(get_db)):
    return await GameCommandService(db).end_game(game_id)
