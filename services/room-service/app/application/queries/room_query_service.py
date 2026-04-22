from __future__ import annotations

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..mappers import room_to_response
from ..room_details import build_room_detail_response
from ...domain.constants import ErrorMessage
from ...domain.models import Room
from ...domain.schemas import RoomResponse, RoomDetailResponse
from ...infrastructure.repositories.room_repository import get_room_by_code
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

        return await build_room_detail_response(self.db, room)

    async def get_room_by_code(self, code: str) -> RoomDetailResponse:
        room = await get_room_by_code(self.db, code)
        if room is None:
            raise HTTPException(status_code=404, detail=ErrorMessage.INVALID_CODE)

        return await build_room_detail_response(self.db, room)

    async def list_rooms(self, limit: int, offset: int = 0, status: str | None = None) -> list[RoomResponse]:
        stmt = select(Room).order_by(Room.created_at.desc()).limit(limit).offset(offset)
        if status:
            stmt = stmt.where(Room.status == status)

        res = await self.db.execute(stmt)
        return [room_to_response(r) for r in res.scalars().all()]