"""Reusable helpers for recording actions in command services.

Centralizes UUID generation, Bet row creation, ledger entry
writing, and outbox event emission so that command services
stay thin and DRY.
"""

from __future__ import annotations

import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from ..domain.constants import DataKey, GameEventType, LedgerEntryType
from ..domain.events import build_event
from ..domain.models import Bet, HandLedgerEntry, OutboxEvent
from shared.core.outbox.helpers import add_outbox_event


def record_bet_action(
    db: AsyncSession,
    *,
    round_id: str,
    player_id: str,
    action: str,
    amount: int,
    idempotency_key: str | None = None,
) -> tuple[Bet, HandLedgerEntry]:
    """Create a Bet row and a BET_PLACED ledger entry, add to session.

    Also emits a ``BET_PLACED`` outbox event.

    Returns the (Bet, HandLedgerEntry) pair for callers that need
    to reference them (e.g. for the HTTP response).
    """
    bet_id = str(uuid.uuid4())
    entry_id = str(uuid.uuid4())

    bet = Bet(
        bet_id=bet_id,
        round_id=round_id,
        player_id=player_id,
        action=action,
        amount=amount,
        idempotency_key=idempotency_key,
    )
    db.add(bet)

    ledger_entry = HandLedgerEntry(
        entry_id=entry_id,
        round_id=round_id,
        entry_type=LedgerEntryType.BET_PLACED,
        player_id=player_id,
        amount=amount,
        detail={"action": action, "bet_id": bet_id},
    )
    db.add(ledger_entry)

    event = build_event(
        GameEventType.BET_PLACED,
        {
            DataKey.BET_ID: bet_id,
            DataKey.ROUND_ID: round_id,
            DataKey.PLAYER_ID: player_id,
            DataKey.ACTION: action,
            DataKey.AMOUNT: amount,
        },
    )
    add_outbox_event(db, OutboxEvent, event)

    return bet, ledger_entry


def append_ledger_entry(
    db: AsyncSession,
    *,
    round_id: str,
    entry_type: str,
    player_id: str | None = None,
    amount: int | None = None,
    detail: dict | None = None,
    original_entry_id: str | None = None,
    dealer_id: str | None = None,
) -> HandLedgerEntry:
    """Create and add a single HandLedgerEntry to the session."""
    entry = HandLedgerEntry(
        entry_id=str(uuid.uuid4()),
        round_id=round_id,
        entry_type=entry_type,
        player_id=player_id,
        amount=amount,
        detail=detail,
        original_entry_id=original_entry_id,
        dealer_id=dealer_id,
    )
    db.add(entry)
    return entry
