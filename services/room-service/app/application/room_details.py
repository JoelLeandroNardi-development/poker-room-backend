from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from .mappers import room_detail_to_response
from ..domain.models import Room
from ..domain.schemas import RoomDetailResponse
from ..infrastructure.repository import get_blind_levels, get_players_in_room

async def build_room_detail_response(
    db: AsyncSession,
    room: Room,
) -> RoomDetailResponse:
    players = await get_players_in_room(db, room.room_id)
    levels = await get_blind_levels(db, room.room_id)
    return room_detail_to_response(room, players, levels)