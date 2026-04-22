from __future__ import annotations

import secrets
import string

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ...domain.constants import CODE_LENGTH
from ...domain.models import Room, BlindLevel

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

async def get_blind_levels(db: AsyncSession, room_id: str) -> list[BlindLevel]:
    res = await db.execute(
        select(BlindLevel)
        .where(BlindLevel.room_id == room_id)
        .order_by(BlindLevel.level.asc())
    )
    return list(res.scalars().all())