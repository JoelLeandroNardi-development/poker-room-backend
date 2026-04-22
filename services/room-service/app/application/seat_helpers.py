from __future__ import annotations

from fastapi import HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from ..domain.constants import ErrorMessage
from ..domain.models import Room, RoomPlayer
from ..domain.schemas import ReorderSeats
from ..infrastructure.repositories.room_player_repository import get_next_seat_number, seat_number_exists_in_room

async def resolve_join_seat(db: AsyncSession, room: Room, requested_seat: int | None) -> int:
    seat_number = requested_seat or await get_next_seat_number(db, room.room_id)

    if seat_number > room.max_players:
        raise HTTPException(status_code=400, detail=ErrorMessage.INVALID_SEAT)
    if await seat_number_exists_in_room(db, room.room_id, seat_number):
        raise HTTPException(status_code=409, detail=ErrorMessage.SEAT_TAKEN)

    return seat_number

def validate_seat_assignments(
    room: Room,
    data: ReorderSeats,
    player_map: dict[str, RoomPlayer],
) -> None:
    player_ids = [assignment.player_id for assignment in data.assignments]
    seat_numbers = [assignment.seat_number for assignment in data.assignments]

    if len(set(player_ids)) != len(player_ids):
        raise HTTPException(status_code=400, detail=ErrorMessage.DUPLICATE_PLAYER_ASSIGNMENT)
    if len(set(seat_numbers)) != len(seat_numbers):
        raise HTTPException(status_code=400, detail=ErrorMessage.DUPLICATE_SEAT_ASSIGNMENT)
    if any(seat > room.max_players for seat in seat_numbers):
        raise HTTPException(status_code=400, detail=ErrorMessage.INVALID_SEAT)
    if any(player_id not in player_map for player_id in player_ids):
        raise HTTPException(status_code=400, detail=ErrorMessage.PLAYER_NOT_IN_ROOM)