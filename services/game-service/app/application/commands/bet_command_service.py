from __future__ import annotations

import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from ..mappers import bet_to_response
from ...domain.constants import (
    BetAction, DataKey, ErrorMessage, GameEventType, LedgerEntryType,
    VALID_BET_ACTIONS,
)
from ...domain.action_pipeline import apply_action
from ...domain.events import build_event
from ...domain.exceptions import IllegalAction
from ...domain.models import Bet, HandLedgerEntry, OutboxEvent, Round, RoundPlayer
from ...infrastructure.repository import get_round_players, fetch_or_raise
from shared.core.outbox.helpers import add_outbox_event
from shared.core.db.session import atomic
from shared.schemas.bets import BetResponse, PlaceBet


class BetCommandService:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def place_bet(self, data: PlaceBet) -> BetResponse:
        action_upper = data.action.upper()

        if action_upper not in VALID_BET_ACTIONS:
            raise IllegalAction(f"Invalid bet action: {data.action}")

        game_round = await fetch_or_raise(
            self.db, Round,
            filter_column=Round.round_id,
            filter_value=data.round_id,
            detail=ErrorMessage.ROUND_NOT_FOUND,
        )
        round_players = await get_round_players(self.db, data.round_id)

        bet_id = str(uuid.uuid4())
        entry_id = str(uuid.uuid4())

        async with atomic(self.db):
            result = apply_action(
                game_round, round_players,
                data.player_id, action_upper, data.amount,
            )

            bet = Bet(
                bet_id=bet_id,
                round_id=data.round_id,
                player_id=data.player_id,
                action=result.action,
                amount=result.amount,
            )
            self.db.add(bet)

            ledger_entry = HandLedgerEntry(
                entry_id=entry_id,
                round_id=data.round_id,
                entry_type=LedgerEntryType.BET_PLACED,
                player_id=data.player_id,
                amount=result.amount,
                detail={"action": result.action, "bet_id": bet_id},
            )
            self.db.add(ledger_entry)

            event = build_event(
                GameEventType.BET_PLACED,
                {
                    DataKey.BET_ID: bet_id,
                    DataKey.ROUND_ID: data.round_id,
                    DataKey.PLAYER_ID: data.player_id,
                    DataKey.ACTION: result.action,
                    DataKey.AMOUNT: result.amount,
                },
            )
            add_outbox_event(self.db, OutboxEvent, event)

        await self.db.commit()
        await self.db.refresh(bet)

        return bet_to_response(bet)
