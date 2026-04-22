from __future__ import annotations

import secrets
import string

from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from ..domain.constants import CODE_LENGTH
from ..domain.models import Room, RoomPlayer, BlindLevel

async def generate_unique_code(db: AsyncSession) -> str:
    chars = string.ascii_uppercase + string.digits
    for _ in range(100):
        code = "".join(secrets.choice(chars) for _ in range(CODE_LENGTH))
        res = await db.execute(select(Room).where(Room.code == code))
        if res.scalar_one_or_none() is None:
            return code
    raise RuntimeError("Failed to generate unique room code after 100 attempts")

async def get_room_by_code(db: AsyncSession, code: str) -> Room | None:
    res = await db.execute(select(Room).where(Room.code == code.upper()))
    return res.scalar_one_or_none()

async def get_players_in_room(db: AsyncSession, room_id: str) -> list[RoomPlayer]:
    res = await db.execute(
        select(RoomPlayer)
        .where(RoomPlayer.room_id == room_id)
        .order_by(RoomPlayer.seat_number.asc())
    )
    return list(res.scalars().all())

async def count_players_in_room(db: AsyncSession, room_id: str) -> int:
    res = await db.execute(
        select(func.count(RoomPlayer.id)).where(RoomPlayer.room_id == room_id)
    )
    return res.scalar_one()

async def get_next_seat_number(db: AsyncSession, room_id: str) -> int:
    res = await db.execute(
        select(func.max(RoomPlayer.seat_number)).where(RoomPlayer.room_id == room_id)
    )
    max_seat = res.scalar_one()
    return (max_seat or 0) + 1

async def seat_number_exists_in_room(db: AsyncSession, room_id: str, seat_number: int) -> bool:
    res = await db.execute(
        select(RoomPlayer)
        .where(RoomPlayer.room_id == room_id, RoomPlayer.seat_number == seat_number)
    )
    return res.scalar_one_or_none() is not None

async def get_blind_levels(db: AsyncSession, room_id: str) -> list[BlindLevel]:
    res = await db.execute(
        select(BlindLevel)
        .where(BlindLevel.room_id == room_id)
        .order_by(BlindLevel.level.asc())
    )
    return list(res.scalars().all())

async def player_name_exists_in_room(db: AsyncSession, room_id: str, player_name: str) -> bool:
    res = await db.execute(
        select(RoomPlayer)
        .where(RoomPlayer.room_id == room_id, RoomPlayer.player_name == player_name)
    )
    return res.scalar_one_or_none() is not None
