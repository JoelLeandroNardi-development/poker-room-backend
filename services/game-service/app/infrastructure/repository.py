from __future__ import annotations

from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from ..domain.constants import GameStatus, RoundStatus
from ..domain.models import Game, Round


async def get_active_game_for_room(db: AsyncSession, room_id: str) -> Game | None:
    res = await db.execute(
        select(Game).where(Game.room_id == room_id, Game.status == GameStatus.ACTIVE)
    )
    return res.scalar_one_or_none()


async def get_latest_round(db: AsyncSession, game_id: str) -> Round | None:
    res = await db.execute(
        select(Round)
        .where(Round.game_id == game_id)
        .order_by(Round.round_number.desc())
        .limit(1)
    )
    return res.scalar_one_or_none()


async def get_active_round(db: AsyncSession, game_id: str) -> Round | None:
    res = await db.execute(
        select(Round)
        .where(Round.game_id == game_id, Round.status == RoundStatus.ACTIVE)
    )
    return res.scalar_one_or_none()


async def count_rounds(db: AsyncSession, game_id: str) -> int:
    res = await db.execute(
        select(func.count(Round.id)).where(Round.game_id == game_id)
    )
    return res.scalar_one()


async def get_rounds_for_game(db: AsyncSession, game_id: str) -> list[Round]:
    res = await db.execute(
        select(Round)
        .where(Round.game_id == game_id)
        .order_by(Round.round_number.asc())
    )
    return list(res.scalars().all())
