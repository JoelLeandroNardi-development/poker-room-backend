from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ...domain.constants import GameStatus
from ...domain.exceptions import NotFound
from ...domain.models import Game

async def fetch_or_raise(db: AsyncSession, model, *, filter_column, filter_value, detail: str = "Not found"):
    res = await db.execute(select(model).where(filter_column == filter_value))
    obj = res.scalar_one_or_none()
    if obj is None:
        raise NotFound(detail)
    return obj

async def get_active_game_for_room(db: AsyncSession, room_id: str) -> Game | None:
    res = await db.execute(
        select(Game).where(Game.room_id == room_id, Game.status == GameStatus.ACTIVE)
    )
    return res.scalar_one_or_none()