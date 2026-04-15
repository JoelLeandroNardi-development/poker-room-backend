from __future__ import annotations

import uuid

from fastapi import HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from ..mappers import bet_to_response
from ...domain.constants import (
    BetAction, BetEventType, DataKey, ErrorMessage, VALID_BET_ACTIONS,
)
from ...domain.events import build_event
from ...domain.models import Bet, OutboxEvent
from ...domain.schemas import BetResponse, PlaceBet
from ...infrastructure.repository import (
    get_pot_total, has_player_folded,
)
from shared.core.outbox.helpers import add_outbox_event

class BetCommandService:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def place_bet(self, data: PlaceBet) -> BetResponse:
        action_upper = data.action.upper()

        if action_upper not in VALID_BET_ACTIONS:
            raise HTTPException(status_code=422, detail=ErrorMessage.INVALID_ACTION)

        if await has_player_folded(self.db, data.round_id, data.player_id):
            raise HTTPException(status_code=400, detail=ErrorMessage.PLAYER_ALREADY_FOLDED)

        if action_upper == BetAction.RAISE and data.amount <= 0:
            raise HTTPException(status_code=400, detail=ErrorMessage.RAISE_AMOUNT_TOO_LOW)

        amount = data.amount
        if action_upper == BetAction.FOLD:
            amount = 0
        elif action_upper == BetAction.CHECK:
            amount = 0

        bet_id = str(uuid.uuid4())

        bet = Bet(
            bet_id=bet_id,
            round_id=data.round_id,
            player_id=data.player_id,
            action=action_upper,
            amount=amount,
        )
        self.db.add(bet)

        event = build_event(
            BetEventType.PLACED,
            {
                DataKey.BET_ID: bet_id,
                DataKey.ROUND_ID: data.round_id,
                DataKey.PLAYER_ID: data.player_id,
                DataKey.ACTION: action_upper,
                DataKey.AMOUNT: amount,
            },
        )
        add_outbox_event(self.db, OutboxEvent, event)

        await self.db.commit()
        await self.db.refresh(bet)

        new_pot = await get_pot_total(self.db, data.round_id)
        pot_event = build_event(
            BetEventType.POT_UPDATED,
            {
                DataKey.ROUND_ID: data.round_id,
                DataKey.POT_AMOUNT: new_pot,
            },
        )
        add_outbox_event(self.db, OutboxEvent, pot_event)
        await self.db.commit()

        return bet_to_response(bet)