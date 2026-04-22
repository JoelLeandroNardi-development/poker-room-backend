from fastapi import APIRouter, Query, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from ...application.queries.room_query_service import RoomQueryService
from ...domain.schemas import RoomResponse, RoomDetailResponse
from ...infrastructure.db import SessionLocal
from shared.core.db.session import make_get_db

room_query_router = APIRouter()
get_db = make_get_db(SessionLocal)

@room_query_router.get("/rooms/{room_id}", response_model=RoomDetailResponse)
async def get_room(room_id: str, db: AsyncSession = Depends(get_db)):
    return await RoomQueryService(db).get_room(room_id)

@room_query_router.get("/rooms/code/{code}", response_model=RoomDetailResponse)
async def get_room_by_code(code: str, db: AsyncSession = Depends(get_db)):
    return await RoomQueryService(db).get_room_by_code(code)

@room_query_router.get("/rooms", response_model=list[RoomResponse])
async def list_rooms(
    limit: int = Query(50, ge=1, le=500),
    offset: int = Query(0, ge=0),
    status: str | None = Query(default=None),
    db: AsyncSession = Depends(get_db),
):
    return await RoomQueryService(db).list_rooms(limit, offset, status)