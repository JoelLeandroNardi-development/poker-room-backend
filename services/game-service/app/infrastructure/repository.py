from __future__ import annotations

from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from ..domain.constants import GameStatus, RoundStatus
from ..domain.models import Bet, Game, Round, RoundPlayer, RoundPayout, HandLedgerEntry

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

async def get_ledger_entries(db: AsyncSession, round_id: str) -> list[HandLedgerEntry]:
    res = await db.execute(
        select(HandLedgerEntry)
        .where(HandLedgerEntry.round_id == round_id)
        .order_by(HandLedgerEntry.id.asc())
    )
    return list(res.scalars().all())

async def get_ledger_entry_by_id(db: AsyncSession, entry_id: str) -> HandLedgerEntry | None:
    res = await db.execute(
        select(HandLedgerEntry)
        .where(HandLedgerEntry.entry_id == entry_id)
    )
    return res.scalar_one_or_none()


# ── Betting queries ──────────────────────────────────────────────

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