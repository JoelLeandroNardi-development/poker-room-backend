from __future__ import annotations

from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from ...domain.models import RoomPlayer

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

async def player_name_exists_in_room(db: AsyncSession, room_id: str, player_name: str) -> bool:
    res = await db.execute(
        select(RoomPlayer)
        .where(RoomPlayer.room_id == room_id, RoomPlayer.player_name == player_name)
    )
    return res.scalar_one_or_none() is not None