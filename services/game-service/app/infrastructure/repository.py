from __future__ import annotations

from sqlalchemy import select, func, update
from sqlalchemy.ext.asyncio import AsyncSession

from ..domain.constants import GameStatus, RoundStatus
from ..domain.exceptions import NotFound, StaleStateError
from ..domain.models import Bet, Game, Round, RoundPlayer, RoundPayout, HandLedgerEntry
from .logging import get_logger

logger = get_logger("game-service.repository")

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

async def cas_update_round(
    db: AsyncSession,
    game_round: Round,
    expected_version: int,
) -> None:
    saved_autoflush = db.autoflush
    db.autoflush = False
    try:
        result = await db.execute(
            update(Round)
            .where(Round.round_id == game_round.round_id)
            .where(Round.state_version == expected_version)
            .values(
                pot_amount=game_round.pot_amount,
                current_highest_bet=game_round.current_highest_bet,
                minimum_raise_amount=game_round.minimum_raise_amount,
                acting_player_id=game_round.acting_player_id,
                last_aggressor_seat=game_round.last_aggressor_seat,
                is_action_closed=game_round.is_action_closed,
                state_version=game_round.state_version,
                street=game_round.street,
                status=game_round.status,
                completed_at=game_round.completed_at,
            )
        )
    finally:
        db.autoflush = saved_autoflush
    if result.rowcount == 0:
        logger.warning(
            "CAS conflict - stale version",
            round_id=game_round.round_id,
            expected_version=expected_version,
            attempted_version=game_round.state_version,
        )
        raise StaleStateError(
            f"Concurrent update on round {game_round.round_id}: "
            f"expected state_version={expected_version}"
        )