from __future__ import annotations

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..mappers import room_to_response, player_to_response, room_detail_to_response
from ...domain.constants import ErrorMessage
from ...domain.models import Room, RoomPlayer
from ...domain.schemas import RoomResponse, RoomDetailResponse, RoomPlayerResponse
from ...infrastructure.repository import get_players_in_room, get_blind_levels, get_room_by_code
from shared.core.db.crud import fetch_or_404

class RoomQueryService:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def get_room(self, room_id: str) -> RoomDetailResponse:
        room = await fetch_or_404(
            self.db, Room,
            filter_column=Room.room_id,
            filter_value=room_id,
            detail=ErrorMessage.ROOM_NOT_FOUND,
        )

        players = await get_players_in_room(self.db, room.room_id)
        levels = await get_blind_levels(self.db, room.room_id)

        return room_detail_to_response(room, players, levels)

    async def get_room_by_code(self, code: str) -> RoomDetailResponse:
        room = await get_room_by_code(self.db, code)
        if room is None:
            raise HTTPException(status_code=404, detail=ErrorMessage.INVALID_CODE)

        players = await get_players_in_room(self.db, room.room_id)
        levels = await get_blind_levels(self.db, room.room_id)

        return room_detail_to_response(room, players, levels)

    async def list_rooms(self, limit: int, offset: int = 0, status: str | None = None) -> list[RoomResponse]:
        stmt = select(Room).order_by(Room.created_at.desc()).limit(limit).offset(offset)
        if status:
            stmt = stmt.where(Room.status == status)

        res = await self.db.execute(stmt)
        return [room_to_response(r) for r in res.scalars().all()]

    async def get_player(self, player_id: str) -> RoomPlayerResponse:
        player = await fetch_or_404(
            self.db, RoomPlayer,
            filter_column=RoomPlayer.player_id,
            filter_value=player_id,
            detail=ErrorMessage.PLAYER_NOT_FOUND,
        )
        return player_to_response(player)