from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from ...application.queries.game_query_service import GameQueryService
from ...domain.schemas import (
    GameResponse, RoundResponse, ReplayResponse, TimelineResponse, 
    SettlementExplanationResponse, ConsistencyCheckResponse, TableStateResponse,
)
from ...infrastructure.db import SessionLocal
from shared.core.db.session import make_get_db

game_query_router = APIRouter()
get_db = make_get_db(SessionLocal)

@game_query_router.get("/games/{game_id}", response_model=GameResponse)
async def get_game(game_id: str, db: AsyncSession = Depends(get_db)):
    return await GameQueryService(db).get_game(game_id)

@game_query_router.get("/games/room/{room_id}", response_model=GameResponse | None)
async def get_game_for_room(room_id: str, db: AsyncSession = Depends(get_db)):
    return await GameQueryService(db).get_game_for_room(room_id)

@game_query_router.get("/games/{game_id}/rounds", response_model=list[RoundResponse])
async def list_rounds(game_id: str, db: AsyncSession = Depends(get_db)):
    return await GameQueryService(db).list_rounds(game_id)

@game_query_router.get("/games/{game_id}/rounds/active", response_model=RoundResponse | None)
async def get_active_round(game_id: str, db: AsyncSession = Depends(get_db)):
    return await GameQueryService(db).get_active_round(game_id)

@game_query_router.get("/rounds/{round_id}", response_model=RoundResponse)
async def get_round(round_id: str, db: AsyncSession = Depends(get_db)):
    return await GameQueryService(db).get_round(round_id)

@game_query_router.get("/rounds/{round_id}/replay", response_model=ReplayResponse)
async def get_replay(round_id: str, db: AsyncSession = Depends(get_db)):
    return await GameQueryService(db).get_replay(round_id)

@game_query_router.get("/rounds/{round_id}/timeline", response_model=TimelineResponse)
async def get_timeline(round_id: str, db: AsyncSession = Depends(get_db)):
    return await GameQueryService(db).get_timeline(round_id)

@game_query_router.get("/rounds/{round_id}/settlement-explanation", response_model=SettlementExplanationResponse)
async def get_settlement_explanation(round_id: str, db: AsyncSession = Depends(get_db)):
    return await GameQueryService(db).get_settlement_explanation(round_id)

@game_query_router.get("/rounds/{round_id}/consistency-check", response_model=ConsistencyCheckResponse)
async def check_consistency(round_id: str, db: AsyncSession = Depends(get_db)):
    return await GameQueryService(db).check_consistency(round_id)

@game_query_router.get("/rounds/{round_id}/table-state", response_model=TableStateResponse)
async def get_table_state(round_id: str, db: AsyncSession = Depends(get_db)):
    return await GameQueryService(db).get_table_state(round_id)