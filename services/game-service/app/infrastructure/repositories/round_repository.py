from __future__ import annotations

from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from ...domain.constants import RoundStatus
from ...domain.models import Round, RoundPlayer, RoundPayout

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

async def get_round_players(db: AsyncSession, round_id: str) -> list[RoundPlayer]:
    res = await db.execute(
        select(RoundPlayer)
        .where(RoundPlayer.round_id == round_id)
        .order_by(RoundPlayer.seat_number.asc())
    )
    return list(res.scalars().all())

async def get_round_payouts(db: AsyncSession, round_id: str) -> list[RoundPayout]:
    res = await db.execute(
        select(RoundPayout)
        .where(RoundPayout.round_id == round_id)
        .order_by(RoundPayout.pot_index.asc(), RoundPayout.id.asc())
    )
    return list(res.scalars().all())