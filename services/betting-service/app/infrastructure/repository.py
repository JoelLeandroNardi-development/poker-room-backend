from __future__ import annotations

from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from ..domain.constants import BetAction
from ..domain.models import Bet


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


async def has_player_folded(db: AsyncSession, round_id: str, player_id: str) -> bool:
    res = await db.execute(
        select(Bet)
        .where(
            Bet.round_id == round_id,
            Bet.player_id == player_id,
            Bet.action == BetAction.FOLD,
        )
    )
    return res.scalar_one_or_none() is not None


async def get_player_total_bet(db: AsyncSession, round_id: str, player_id: str) -> int:
    res = await db.execute(
        select(func.coalesce(func.sum(Bet.amount), 0))
        .where(Bet.round_id == round_id, Bet.player_id == player_id)
    )
    return res.scalar_one()


async def get_last_action_for_player(db: AsyncSession, round_id: str, player_id: str) -> str | None:
    res = await db.execute(
        select(Bet.action)
        .where(Bet.round_id == round_id, Bet.player_id == player_id)
        .order_by(Bet.created_at.desc())
        .limit(1)
    )
    return res.scalar_one_or_none()
