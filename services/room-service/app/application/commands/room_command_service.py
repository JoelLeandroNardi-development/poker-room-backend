from __future__ import annotations

import uuid

from fastapi import HTTPException
from sqlalchemy import delete
from sqlalchemy.ext.asyncio import AsyncSession

from ..mappers import room_to_response, player_to_response, blind_level_to_response
from ...domain.constants import (
    DataKey, ErrorMessage, ResponseMessage, RoomEventType, RoomStatus,
)
from ...domain.events import build_event
from ...domain.models import BlindLevel, OutboxEvent, Room, RoomPlayer
from ...domain.schemas import (
    CreateRoom, JoinRoom, SetBlindStructure,
    RoomResponse, RoomPlayerResponse, RoomDetailResponse,
    UpdateChips, DeleteRoomResponse,
)
from ...infrastructure.repository import (
    count_players_in_room,
    generate_unique_code,
    get_blind_levels,
    get_next_seat_number,
    get_players_in_room,
    player_name_exists_in_room,
    get_room_by_code,
)
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
        seat_number = await get_next_seat_number(self.db, room.room_id)

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

        players = await get_players_in_room(self.db, room_id)
        levels = await get_blind_levels(self.db, room_id)

        return RoomDetailResponse(
            room=room_to_response(room),
            players=[player_to_response(p) for p in players],
            blind_levels=[blind_level_to_response(bl) for bl in levels],
            starting_dealer_seat=room.starting_dealer_seat,
        )

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
