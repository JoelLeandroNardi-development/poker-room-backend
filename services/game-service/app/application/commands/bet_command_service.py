from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..action_helpers import record_bet_action
from ..mappers import bet_to_response
from ...domain.constants import (
    BetAction, ErrorMessage, VALID_BET_ACTIONS,
)
from ...domain.action_pipeline import apply_action
from ...domain.exceptions import DuplicateActionError, IllegalAction
from ...domain.models import Bet, Round, RoundPlayer
from ...infrastructure.repository import get_round_players, fetch_or_raise
from shared.core.db.session import atomic
from shared.schemas.bets import BetResponse, PlaceBet


class BetCommandService:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def place_bet(self, data: PlaceBet) -> BetResponse:
        action_upper = data.action.upper()

        if action_upper not in VALID_BET_ACTIONS:
            raise IllegalAction(f"Invalid bet action: {data.action}")

        # ── Idempotency check ────────────────────────────────────
        if data.idempotency_key:
            existing = (
                await self.db.execute(
                    select(Bet).where(Bet.idempotency_key == data.idempotency_key)
                )
            ).scalar_one_or_none()
            if existing is not None:
                return bet_to_response(existing)

        game_round = await fetch_or_raise(
            self.db, Round,
            filter_column=Round.round_id,
            filter_value=data.round_id,
            detail=ErrorMessage.ROUND_NOT_FOUND,
        )
        round_players = await get_round_players(self.db, data.round_id)

        async with atomic(self.db):
            result = apply_action(
                game_round, round_players,
                data.player_id, action_upper, data.amount,
                expected_version=data.expected_version,
            )

            bet, _ledger = record_bet_action(
                self.db,
                round_id=data.round_id,
                player_id=data.player_id,
                action=result.action,
                amount=result.amount,
                idempotency_key=data.idempotency_key,
            )

        await self.db.commit()
        await self.db.refresh(bet)

        return bet_to_response(bet)
