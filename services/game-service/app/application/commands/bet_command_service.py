from __future__ import annotations

import uuid

from fastapi import HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from ..mappers import bet_to_response
from ...domain.constants import (
    BetAction, DataKey, ErrorMessage, GameEventType, VALID_BET_ACTIONS,
)
from ...domain.events import build_event
from ...domain.models import Bet, OutboxEvent, Round, RoundPlayer
from ...domain.validator import HandContext, PlayerState, validate_bet
from ...infrastructure.repository import get_round_players, get_pot_total
from shared.core.outbox.helpers import add_outbox_event
from shared.core.db.crud import fetch_or_404
from shared.core.db.session import atomic
from shared.schemas.bets import BetResponse, PlaceBet


class BetCommandService:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def _build_hand_context(self, round_id: str) -> HandContext:
        game_round = await fetch_or_404(
            self.db, Round,
            filter_column=Round.round_id,
            filter_value=round_id,
            detail=ErrorMessage.ROUND_NOT_FOUND,
        )
        round_players = await get_round_players(self.db, round_id)

        players = [
            PlayerState(
                player_id=rp.player_id,
                seat_number=rp.seat_number,
                stack_remaining=rp.stack_remaining,
                committed_this_street=rp.committed_this_street,
                committed_this_hand=rp.committed_this_hand,
                has_folded=rp.has_folded,
                is_all_in=rp.is_all_in,
                is_active_in_hand=rp.is_active_in_hand,
            )
            for rp in round_players
        ]

        return HandContext(
            round_id=game_round.round_id,
            status=game_round.status,
            street=game_round.street,
            acting_player_id=game_round.acting_player_id,
            current_highest_bet=game_round.current_highest_bet,
            minimum_raise_amount=game_round.minimum_raise_amount,
            is_action_closed=game_round.is_action_closed,
            players=players,
        )

    async def place_bet(self, data: PlaceBet) -> BetResponse:
        action_upper = data.action.upper()

        if action_upper not in VALID_BET_ACTIONS:
            raise HTTPException(status_code=422, detail=ErrorMessage.INVALID_ACTION)

        ctx = await self._build_hand_context(data.round_id)
        result = validate_bet(ctx, data.player_id, action_upper, data.amount)

        bet_id = str(uuid.uuid4())

        async with atomic(self.db):
            bet = Bet(
                bet_id=bet_id,
                round_id=data.round_id,
                player_id=data.player_id,
                action=result.action,
                amount=result.amount,
            )
            self.db.add(bet)

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
