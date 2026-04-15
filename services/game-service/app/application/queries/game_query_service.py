from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..mappers import game_to_response, round_to_response
from ...domain.constants import ErrorMessage, GameStatus
from ...domain.models import Game, Round
from ...domain.schemas import GameResponse, RoundResponse
from ...infrastructure.repository import (
    get_rounds_for_game, get_active_round, get_round_players, get_round_payouts, fetch_or_raise,
)

class GameQueryService:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def get_game(self, game_id: str) -> GameResponse:
        game = await fetch_or_raise(
            self.db, Game,
            filter_column=Game.game_id,
            filter_value=game_id,
            detail=ErrorMessage.GAME_NOT_FOUND,
        )
        return game_to_response(game)

    async def get_game_for_room(self, room_id: str) -> GameResponse | None:
        res = await self.db.execute(
            select(Game)
            .where(Game.room_id == room_id, Game.status == GameStatus.ACTIVE)
        )
        game = res.scalar_one_or_none()
        if game is None:
            return None
        return game_to_response(game)

    async def list_rounds(self, game_id: str) -> list[RoundResponse]:
        rounds = await get_rounds_for_game(self.db, game_id)
        result = []
        for r in rounds:
            players = await get_round_players(self.db, r.round_id)
            payouts = await get_round_payouts(self.db, r.round_id)
            result.append(round_to_response(r, players, payouts))
        return result

    async def get_round(self, round_id: str) -> RoundResponse:
        game_round = await fetch_or_raise(
            self.db, Round,
            filter_column=Round.round_id,
            filter_value=round_id,
            detail=ErrorMessage.ROUND_NOT_FOUND,
        )
        players = await get_round_players(self.db, round_id)
        payouts = await get_round_payouts(self.db, round_id)
        return round_to_response(game_round, players, payouts)

    async def get_active_round(self, game_id: str) -> RoundResponse | None:
        game_round = await get_active_round(self.db, game_id)
        if game_round is None:
            return None
        players = await get_round_players(self.db, game_round.round_id)
        payouts = await get_round_payouts(self.db, game_round.round_id)
        return round_to_response(game_round, players, payouts)
