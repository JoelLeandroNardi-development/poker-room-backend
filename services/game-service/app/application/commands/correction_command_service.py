"""Service methods for dealer corrections on a Texas Hold'em hand.

Each correction appends a new *immutable* ledger entry that
references the original entry it amends.  The authoritative hand
state is always derived by replaying the full ledger.
"""

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy.ext.asyncio import AsyncSession

from ..action_helpers import append_ledger_entry
from ...domain.constants import (
    CORRECTION_ENTRY_TYPES, DataKey, ErrorMessage, GameEventType,
    LedgerEntryType, RoundStatus,
)
from ...domain.events import build_event
from ...domain.exceptions import (
    CannotReverseCorrection, EntryAlreadyReversed, LedgerEntryNotFound,
    RoundAlreadyActive, RoundNotCompleted,
)
from ...domain.hand_ledger import LedgerRow, rebuild_hand_state, HandState
from ...domain.models import HandLedgerEntry, OutboxEvent, Round, RoundPlayer
from ...infrastructure.repository import (
    get_ledger_entries, get_ledger_entry_by_id, get_round_players, fetch_or_raise,
)
from shared.core.db.session import atomic
from shared.core.outbox.helpers import add_outbox_event


class CorrectionCommandService:
    def __init__(self, db: AsyncSession):
        self.db = db

    # ── Queries ──────────────────────────────────────────────────────

    async def get_hand_state(self, round_id: str) -> HandState:
        """Rebuild the current hand state from the ledger."""
        rows = await get_ledger_entries(self.db, round_id)
        ledger = [
            LedgerRow(
                entry_id=r.entry_id,
                entry_type=r.entry_type,
                player_id=r.player_id,
                amount=r.amount,
                detail=r.detail,
                original_entry_id=r.original_entry_id,
            )
            for r in rows
        ]
        return rebuild_hand_state(ledger)

    async def get_ledger(self, round_id: str) -> list[HandLedgerEntry]:
        """Return the full immutable ledger for a round."""
        return await get_ledger_entries(self.db, round_id)

    # ── Corrections ──────────────────────────────────────────────────

    async def reverse_action(
        self, round_id: str, original_entry_id: str, *, dealer_id: str | None = None, reason: str | None = None,
    ) -> HandLedgerEntry:
        """Reverse a previous bet / blind / ante entry."""
        game_round = await fetch_or_raise(
            self.db, Round, filter_column=Round.round_id,
            filter_value=round_id, detail=ErrorMessage.ROUND_NOT_FOUND,
        )

        original = await get_ledger_entry_by_id(self.db, original_entry_id)
        if original is None or original.round_id != round_id:
            raise LedgerEntryNotFound("Ledger entry not found")

        # Guard: cannot reverse a correction entry or an already-reversed entry
        if original.entry_type in CORRECTION_ENTRY_TYPES:
            raise CannotReverseCorrection("Cannot reverse a correction entry")

        existing_entries = await get_ledger_entries(self.db, round_id)
        reversed_ids = {
            e.original_entry_id for e in existing_entries
            if e.entry_type == LedgerEntryType.ACTION_REVERSED
        }
        if original_entry_id in reversed_ids:
            raise EntryAlreadyReversed("This ledger entry has already been reversed")

        async with atomic(self.db):
            entry = append_ledger_entry(
                self.db,
                round_id=round_id,
                entry_type=LedgerEntryType.ACTION_REVERSED,
                player_id=original.player_id,
                amount=original.amount,
                detail={"reason": reason} if reason else None,
                original_entry_id=original_entry_id,
                dealer_id=dealer_id,
            )

            # Project reversal onto mutable state so Round/RoundPlayer
            # stays consistent with the ledger.
            reversed_amount = original.amount or 0
            if original.player_id and reversed_amount > 0:
                round_players = await get_round_players(self.db, round_id)
                rp = next((p for p in round_players if p.player_id == original.player_id), None)
                if rp is not None:
                    rp.stack_remaining += reversed_amount
                    rp.committed_this_street = max(0, rp.committed_this_street - reversed_amount)
                    rp.committed_this_hand = max(0, rp.committed_this_hand - reversed_amount)
                game_round.pot_amount = max(0, game_round.pot_amount - reversed_amount)

            self._emit_correction_event(game_round, entry)

        await self.db.commit()
        return entry

    async def adjust_stack(
        self, round_id: str, player_id: str, amount: int,
        *, dealer_id: str | None = None, reason: str | None = None,
    ) -> HandLedgerEntry:
        """Apply an ad-hoc chip adjustment to a player's stack."""
        game_round = await fetch_or_raise(
            self.db, Round, filter_column=Round.round_id,
            filter_value=round_id, detail=ErrorMessage.ROUND_NOT_FOUND,
        )

        async with atomic(self.db):
            entry = append_ledger_entry(
                self.db,
                round_id=round_id,
                entry_type=LedgerEntryType.STACK_ADJUSTED,
                player_id=player_id,
                amount=amount,
                detail={"reason": reason} if reason else None,
                dealer_id=dealer_id,
            )
            # Apply the adjustment to the live RoundPlayer row
            round_players = await get_round_players(self.db, round_id)
            rp = next((p for p in round_players if p.player_id == player_id), None)
            if rp is not None:
                rp.stack_remaining += amount
            self._emit_correction_event(game_round, entry)

        await self.db.commit()
        return entry

    async def reopen_hand(
        self, round_id: str, *, dealer_id: str | None = None, reason: str | None = None,
    ) -> HandLedgerEntry:
        """Re-open a completed round so the dealer can make corrections."""
        game_round = await fetch_or_raise(
            self.db, Round, filter_column=Round.round_id,
            filter_value=round_id, detail=ErrorMessage.ROUND_NOT_FOUND,
        )

        if game_round.status != RoundStatus.COMPLETED:
            raise RoundNotCompleted("Round must be completed before applying this correction")

        async with atomic(self.db):
            game_round.status = RoundStatus.ACTIVE
            game_round.is_action_closed = False
            game_round.completed_at = None
            entry = append_ledger_entry(
                self.db,
                round_id=round_id,
                entry_type=LedgerEntryType.HAND_REOPENED,
                dealer_id=dealer_id,
                detail={"reason": reason} if reason else None,
            )
            self._emit_correction_event(game_round, entry)

        await self.db.commit()
        return entry

    async def correct_payout(
        self, round_id: str,
        old_player_id: str, old_amount: int,
        new_player_id: str, new_amount: int,
        *, dealer_id: str | None = None, reason: str | None = None,
    ) -> HandLedgerEntry:
        """Correct a mis-assigned payout: debit old winner, credit new."""
        game_round = await fetch_or_raise(
            self.db, Round, filter_column=Round.round_id,
            filter_value=round_id, detail=ErrorMessage.ROUND_NOT_FOUND,
        )

        async with atomic(self.db):
            entry = append_ledger_entry(
                self.db,
                round_id=round_id,
                entry_type=LedgerEntryType.PAYOUT_CORRECTED,
                player_id=new_player_id,
                amount=new_amount,
                detail={
                    "old_player_id": old_player_id,
                    "old_amount": old_amount,
                    "reason": reason,
                },
                dealer_id=dealer_id,
            )
            round_players = await get_round_players(self.db, round_id)
            player_map = {rp.player_id: rp for rp in round_players}

            old_rp = player_map.get(old_player_id)
            if old_rp is not None:
                old_rp.stack_remaining -= old_amount

            new_rp = player_map.get(new_player_id)
            if new_rp is not None:
                new_rp.stack_remaining += new_amount

            self._emit_correction_event(game_round, entry)

        await self.db.commit()
        return entry

    # ── Helpers ──────────────────────────────────────────────────────

    def _emit_correction_event(self, game_round: Round, entry: HandLedgerEntry) -> None:
        event = build_event(
            GameEventType.CORRECTION_APPLIED,
            {
                DataKey.GAME_ID: game_round.game_id,
                DataKey.ROUND_ID: game_round.round_id,
                "entry_id": entry.entry_id,
                "entry_type": entry.entry_type,
                "player_id": entry.player_id,
                "amount": entry.amount,
            },
        )
        add_outbox_event(self.db, OutboxEvent, event)
