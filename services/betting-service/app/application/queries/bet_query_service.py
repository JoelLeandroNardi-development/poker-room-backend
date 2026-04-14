from __future__ import annotations

from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from ..mappers import bet_to_response
from ...domain.constants import BetAction
from ...domain.models import Bet
from ...domain.schemas import BetResponse, PotResponse, PlayerBetSummary
from ...infrastructure.repository import get_bets_for_round, get_pot_total


class BetQueryService:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def get_bets_for_round(self, round_id: str) -> list[BetResponse]:
        bets = await get_bets_for_round(self.db, round_id)
        return [bet_to_response(b) for b in bets]

    async def get_pot(self, round_id: str) -> PotResponse:
        bets = await get_bets_for_round(self.db, round_id)
        total = await get_pot_total(self.db, round_id)
        return PotResponse(
            round_id=round_id,
            total_pot=total,
            bets=[bet_to_response(b) for b in bets],
        )

    async def get_player_summaries(self, round_id: str) -> list[PlayerBetSummary]:
        bets = await get_bets_for_round(self.db, round_id)

        player_data: dict[str, dict] = {}
        for bet in bets:
            pid = bet.player_id
            if pid not in player_data:
                player_data[pid] = {
                    "player_id": pid,
                    "total_bet": 0,
                    "last_action": bet.action,
                    "is_folded": False,
                }
            player_data[pid]["total_bet"] += bet.amount
            player_data[pid]["last_action"] = bet.action
            if bet.action == BetAction.FOLD:
                player_data[pid]["is_folded"] = True

        return [PlayerBetSummary(**d) for d in player_data.values()]
