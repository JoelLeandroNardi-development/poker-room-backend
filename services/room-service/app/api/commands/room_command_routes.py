from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from ...application.commands.room_command_service import RoomCommandService
from ...domain.schemas import (
    CreateRoom, SetBlindStructure, RoomResponse, 
    RoomDetailResponse, DeleteRoomResponse, ReorderSeats,
)
from ...infrastructure.db import SessionLocal
from shared.core.db.session import make_get_db

room_command_router = APIRouter()
get_db = make_get_db(SessionLocal)

@room_command_router.post("/rooms", response_model=RoomResponse)
async def create_room(data: CreateRoom, db: AsyncSession = Depends(get_db)):
    return await RoomCommandService(db).create_room(data)

@room_command_router.put("/rooms/{room_id}/blinds", response_model=RoomDetailResponse)
async def set_blind_structure(room_id: str, data: SetBlindStructure, db: AsyncSession = Depends(get_db)):
    return await RoomCommandService(db).set_blind_structure(room_id, data)

@room_command_router.put("/rooms/{room_id}/seats", response_model=RoomDetailResponse)
async def reorder_seats(room_id: str, data: ReorderSeats, db: AsyncSession = Depends(get_db)):
    return await RoomCommandService(db).reorder_seats(room_id, data)

@room_command_router.delete("/rooms/{room_id}", response_model=DeleteRoomResponse)
async def delete_room(room_id: str, db: AsyncSession = Depends(get_db)):
    return await RoomCommandService(db).delete_room(room_id)