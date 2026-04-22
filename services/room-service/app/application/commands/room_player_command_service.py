from __future__ import annotations

import uuid

from fastapi import HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from ..mappers import player_to_response
from ..seat_helpers import resolve_join_seat
from ...domain.constants import DataKey, ErrorMessage, RoomEventType, RoomStatus
from ...domain.events import build_event
from ...domain.models import OutboxEvent, RoomPlayer
from ...domain.schemas import JoinRoom, RoomPlayerResponse, UpdateChips
from ...infrastructure.repositories.room_repository import get_room_by_code
from ...infrastructure.repositories.room_player_repository import count_players_in_room, player_name_exists_in_room
from shared.core.outbox.helpers import add_outbox_event
from shared.core.db.crud import fetch_or_404

class RoomPlayerCommandService:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def join_room_by_code(self, code: str, data: JoinRoom) -> RoomPlayerResponse:
        room = await get_room_by_code(self.db, code)
        if room is None:
            raise HTTPException(status_code=404, detail=ErrorMessage.INVALID_CODE)

        if room.status != RoomStatus.WAITING:
            raise HTTPException(status_code=400, detail=ErrorMessage.ROOM_NOT_WAITING)

        player_count = await count_players_in_room(self.db, room.room_id)
        if player_count >= room.max_players:
            raise HTTPException(status_code=400, detail=ErrorMessage.ROOM_FULL)

        if await player_name_exists_in_room(self.db, room.room_id, data.player_name):
            raise HTTPException(status_code=409, detail=ErrorMessage.DUPLICATE_NAME)

        player_id = str(uuid.uuid4())
        seat_number = await resolve_join_seat(self.db, room, data.seat_number)

        player = RoomPlayer(
            room_id=room.room_id,
            player_id=player_id,
            player_name=data.player_name,
            seat_number=seat_number,
            chip_count=room.starting_chips,
            is_active=True,
            is_eliminated=False,
        )
        self.db.add(player)

        event = build_event(
            RoomEventType.PLAYER_JOINED,
            {
                DataKey.ROOM_ID: room.room_id,
                DataKey.PLAYER_ID: player_id,
                DataKey.PLAYER_NAME: data.player_name,
                DataKey.SEAT_NUMBER: seat_number,
                DataKey.CHIP_COUNT: room.starting_chips,
            },
        )
        add_outbox_event(self.db, OutboxEvent, event)

        await self.db.commit()
        await self.db.refresh(player)

        return player_to_response(player)

    async def update_player_chips(self, player_id: str, data: UpdateChips) -> RoomPlayerResponse:
        player = await fetch_or_404(
            self.db, RoomPlayer,
            filter_column=RoomPlayer.player_id,
            filter_value=player_id,
            detail=ErrorMessage.PLAYER_NOT_FOUND,
        )

        player.chip_count = data.chip_count

        event = build_event(
            RoomEventType.CHIPS_UPDATED,
            {
                DataKey.ROOM_ID: player.room_id,
                DataKey.PLAYER_ID: player.player_id,
                DataKey.CHIP_COUNT: data.chip_count,
            },
        )
        add_outbox_event(self.db, OutboxEvent, event)

        await self.db.commit()
        await self.db.refresh(player)

        return player_to_response(player)

    async def eliminate_player(self, player_id: str) -> RoomPlayerResponse:
        player = await fetch_or_404(
            self.db, RoomPlayer,
            filter_column=RoomPlayer.player_id,
            filter_value=player_id,
            detail=ErrorMessage.PLAYER_NOT_FOUND,
        )

        player.is_eliminated = True
        player.is_active = False
        player.chip_count = 0

        event = build_event(
            RoomEventType.PLAYER_ELIMINATED,
            {
                DataKey.ROOM_ID: player.room_id,
                DataKey.PLAYER_ID: player.player_id,
                DataKey.PLAYER_NAME: player.player_name,
            },
        )
        add_outbox_event(self.db, OutboxEvent, event)

        await self.db.commit()
        await self.db.refresh(player)

        return player_to_response(player)