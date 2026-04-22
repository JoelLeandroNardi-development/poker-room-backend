from __future__ import annotations

import uuid

from fastapi import HTTPException
from sqlalchemy import delete
from sqlalchemy.ext.asyncio import AsyncSession

from ..mappers import room_to_response
from ..seat_helpers import validate_seat_assignments
from ..room_details import build_room_detail_response
from ...domain.constants import (
    DataKey, ErrorMessage, ResponseMessage, RoomEventType, RoomStatus,
)
from ...domain.events import build_event
from ...domain.models import BlindLevel, OutboxEvent, Room, RoomPlayer
from ...domain.schemas import (
    CreateRoom, SetBlindStructure, RoomResponse, 
    RoomDetailResponse, DeleteRoomResponse, ReorderSeats,
)
from ...infrastructure.repositories.room_repository import generate_unique_code
from ...infrastructure.repositories.room_player_repository import get_players_in_room
from shared.core.outbox.helpers import add_outbox_event
from shared.core.db.crud import fetch_or_404

class RoomCommandService:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def create_room(self, data: CreateRoom) -> RoomResponse:
        room_id = str(uuid.uuid4())
        code = await generate_unique_code(self.db)

        room = Room(
            room_id=room_id,
            code=code,
            name=data.name,
            status=RoomStatus.WAITING,
            max_players=data.max_players,
            starting_chips=data.starting_chips,
            antes_enabled=data.antes_enabled,
            starting_dealer_seat=1,
            created_by=data.created_by,
        )
        self.db.add(room)

        event = build_event(
            RoomEventType.CREATED,
            {
                DataKey.ROOM_ID: room_id,
                DataKey.CODE: code,
                DataKey.MAX_PLAYERS: data.max_players,
                DataKey.CREATED_BY: data.created_by,
            },
        )
        add_outbox_event(self.db, OutboxEvent, event)

        await self.db.commit()
        await self.db.refresh(room)

        return room_to_response(room)

    async def reorder_seats(self, room_id: str, data: ReorderSeats) -> RoomDetailResponse:
        room = await fetch_or_404(
            self.db, Room,
            filter_column=Room.room_id,
            filter_value=room_id,
            detail=ErrorMessage.ROOM_NOT_FOUND,
        )

        if room.status != RoomStatus.WAITING:
            raise HTTPException(status_code=400, detail=ErrorMessage.ROOM_NOT_WAITING)

        players = await get_players_in_room(self.db, room_id)
        player_map = {player.player_id: player for player in players}

        validate_seat_assignments(room, data, player_map)

        for assignment in data.assignments:
            player_map[assignment.player_id].seat_number = assignment.seat_number

        event = build_event(
            RoomEventType.SEATS_REORDERED,
            {
                DataKey.ROOM_ID: room_id,
                DataKey.ASSIGNMENTS: [
                    {
                        DataKey.PLAYER_ID: assignment.player_id,
                        DataKey.SEAT_NUMBER: assignment.seat_number,
                    }
                    for assignment in data.assignments
                ],
            },
        )
        add_outbox_event(self.db, OutboxEvent, event)

        await self.db.commit()
        await self.db.refresh(room)

        return await build_room_detail_response(self.db, room)

    async def set_blind_structure(self, room_id: str, data: SetBlindStructure) -> RoomDetailResponse:
        room = await fetch_or_404(
            self.db, Room,
            filter_column=Room.room_id,
            filter_value=room_id,
            detail=ErrorMessage.ROOM_NOT_FOUND,
        )

        if room.status != RoomStatus.WAITING:
            raise HTTPException(status_code=400, detail=ErrorMessage.ROOM_NOT_WAITING)

        await self.db.execute(
            delete(BlindLevel).where(BlindLevel.room_id == room_id)
        )

        for level_data in data.levels:
            bl = BlindLevel(
                room_id=room_id,
                level=level_data.level,
                small_blind=level_data.small_blind,
                big_blind=level_data.big_blind,
                ante=level_data.ante,
                duration_minutes=level_data.duration_minutes,
            )
            self.db.add(bl)

        room.starting_dealer_seat = data.starting_dealer_seat

        await self.db.commit()
        await self.db.refresh(room)

        return await build_room_detail_response(self.db, room)

    async def delete_room(self, room_id: str) -> DeleteRoomResponse:
        room = await fetch_or_404(
            self.db, Room,
            filter_column=Room.room_id,
            filter_value=room_id,
            detail=ErrorMessage.ROOM_NOT_FOUND,
        )

        await self.db.execute(delete(RoomPlayer).where(RoomPlayer.room_id == room_id))
        await self.db.execute(delete(BlindLevel).where(BlindLevel.room_id == room_id))
        await self.db.delete(room)
        await self.db.commit()

        return DeleteRoomResponse(message=ResponseMessage.DELETED, room_id=room_id)