from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from ...application.commands.room_player_command_service import RoomPlayerCommandService
from ...domain.schemas import JoinRoom, RoomPlayerResponse, UpdateChips
from ...infrastructure.db import SessionLocal
from shared.core.db.session import make_get_db

room_player_command_router = APIRouter()
get_db = make_get_db(SessionLocal)

@room_player_command_router.post("/rooms/join/{code}", response_model=RoomPlayerResponse)
async def join_room(code: str, data: JoinRoom, db: AsyncSession = Depends(get_db)):
    return await RoomPlayerCommandService(db).join_room_by_code(code, data)

@room_player_command_router.put("/players/{player_id}/chips", response_model=RoomPlayerResponse)
async def update_player_chips(player_id: str, data: UpdateChips, db: AsyncSession = Depends(get_db)):
    return await RoomPlayerCommandService(db).update_player_chips(player_id, data)

@room_player_command_router.post("/players/{player_id}/eliminate", response_model=RoomPlayerResponse)
async def eliminate_player(player_id: str, db: AsyncSession = Depends(get_db)):
    return await RoomPlayerCommandService(db).eliminate_player(player_id)