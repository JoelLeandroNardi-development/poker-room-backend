from fastapi import APIRouter, Query, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from ..application.commands.room_command_service import RoomCommandService
from ..application.queries.room_query_service import RoomQueryService
from ..domain.schemas import (
    CreateRoom, JoinRoom, SetBlindStructure,
    RoomResponse, RoomPlayerResponse, RoomDetailResponse,
    UpdateChips, DeleteRoomResponse,
)
from ..infrastructure.db import SessionLocal
from shared.core.db.session import make_get_db

router = APIRouter()
get_db = make_get_db(SessionLocal)

@router.post("/rooms", response_model=RoomResponse)
async def create_room(data: CreateRoom, db: AsyncSession = Depends(get_db)):
    return await RoomCommandService(db).create_room(data)

@router.get("/rooms/{room_id}", response_model=RoomDetailResponse)
async def get_room(room_id: str, db: AsyncSession = Depends(get_db)):
    return await RoomQueryService(db).get_room(room_id)

@router.get("/rooms/code/{code}", response_model=RoomDetailResponse)
async def get_room_by_code(code: str, db: AsyncSession = Depends(get_db)):
    return await RoomQueryService(db).get_room_by_code(code)

@router.get("/rooms", response_model=list[RoomResponse])
async def list_rooms(
    limit: int = Query(50, ge=1, le=500),
    offset: int = Query(0, ge=0),
    status: str | None = Query(default=None),
    db: AsyncSession = Depends(get_db),
):
    return await RoomQueryService(db).list_rooms(limit, offset, status)

@router.post("/rooms/join/{code}", response_model=RoomPlayerResponse)
async def join_room(code: str, data: JoinRoom, db: AsyncSession = Depends(get_db)):
    return await RoomCommandService(db).join_room_by_code(code, data)

@router.put("/rooms/{room_id}/blinds", response_model=RoomDetailResponse)
async def set_blind_structure(room_id: str, data: SetBlindStructure, db: AsyncSession = Depends(get_db)):
    return await RoomCommandService(db).set_blind_structure(room_id, data)

@router.put("/players/{player_id}/chips", response_model=RoomPlayerResponse)
async def update_player_chips(player_id: str, data: UpdateChips, db: AsyncSession = Depends(get_db)):
    return await RoomCommandService(db).update_player_chips(player_id, data)

@router.post("/players/{player_id}/eliminate", response_model=RoomPlayerResponse)
async def eliminate_player(player_id: str, db: AsyncSession = Depends(get_db)):
    return await RoomCommandService(db).eliminate_player(player_id)

@router.get("/players/{player_id}", response_model=RoomPlayerResponse)
async def get_player(player_id: str, db: AsyncSession = Depends(get_db)):
    return await RoomQueryService(db).get_player(player_id)

@router.delete("/rooms/{room_id}", response_model=DeleteRoomResponse)
async def delete_room(room_id: str, db: AsyncSession = Depends(get_db)):
    return await RoomCommandService(db).delete_room(room_id)
