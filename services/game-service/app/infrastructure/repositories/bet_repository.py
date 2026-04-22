from __future__ import annotations

from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from ...domain.models import Bet

async def get_bets_for_round(db: AsyncSession, round_id: str) -> list[Bet]:
    res = await db.execute(
        select(Bet)
        .where(Bet.round_id == round_id)
        .order_by(Bet.created_at.asc())
    )
    return list(res.scalars().all())

async def get_pot_total(db: AsyncSession, round_id: str) -> int:
    res = await db.execute(
        select(func.coalesce(func.sum(Bet.amount), 0))
        .where(Bet.round_id == round_id)
    )
    return res.scalar_one()