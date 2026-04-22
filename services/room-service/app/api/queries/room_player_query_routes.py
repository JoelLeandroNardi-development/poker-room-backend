from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from ...application.queries.room_player_query_service import RoomPlayerQueryService
from ...domain.schemas import RoomPlayerResponse
from ...infrastructure.db import SessionLocal
from shared.core.db.session import make_get_db

room_player_query_router = APIRouter()
get_db = make_get_db(SessionLocal)

@room_player_query_router.get("/players/{player_id}", response_model=RoomPlayerResponse)
async def get_player(player_id: str, db: AsyncSession = Depends(get_db)):
    return await RoomPlayerQueryService(db).get_player(player_id)