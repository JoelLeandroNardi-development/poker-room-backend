"""Application-level orchestration for table runtime lifecycle.

Bridges the pure ``TableRuntime`` state machine in the domain layer
with persistence and API-facing commands.
"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..mappers import game_to_response
from ...domain.constants import GameStatus, ErrorMessage
from ...domain.exceptions import GameNotActive, NotFound
from ...domain.models import Game
from ...domain.table_runtime import (
    BlindClock, SeatStatus, TableRuntime, TableSeat, TableStatus,
)
from ...infrastructure.repository import fetch_or_raise
from ...infrastructure.room_config import load_room_snapshot
from shared.core.db.session import atomic


def _build_runtime_from_game(game: Game, seats: list[TableSeat]) -> TableRuntime:
    """Reconstruct a TableRuntime from the persisted Game row."""
    return TableRuntime(
        game_id=game.game_id,
        status=(
            TableStatus.RUNNING
            if game.status == GameStatus.ACTIVE
            else TableStatus(game.status)
            if game.status in {s.value for s in TableStatus}
            else TableStatus.WAITING
        ),
        seats=seats,
        blind_clock=BlindClock(current_level=game.current_blind_level),
        dealer_seat=game.current_dealer_seat,
    )


class TableRuntimeCommandService:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def _load_runtime(self, game_id: str) -> tuple[Game, TableRuntime]:
        game = await fetch_or_raise(
            self.db, Game,
            filter_column=Game.game_id,
            filter_value=game_id,
            detail=ErrorMessage.GAME_NOT_FOUND,
        )
        room_config = await load_room_snapshot(self.db, game_id)
        seats = [
            TableSeat(
                seat_number=p.seat_number,
                player_id=p.player_id,
                status=SeatStatus.ACTIVE,
                chip_count=p.chip_count,
            )
            for p in room_config.active_players
        ]
        runtime = _build_runtime_from_game(game, seats)
        return game, runtime

    async def pause_table(self, game_id: str) -> dict:
        game, runtime = await self._load_runtime(game_id)
        if game.status != GameStatus.ACTIVE:
            raise GameNotActive("Game is not in ACTIVE status")

        runtime.pause_session()

        async with atomic(self.db):
            game.status = GameStatus.PAUSED

        await self.db.commit()
        return {"game_id": game_id, "status": GameStatus.PAUSED}

    async def resume_table(self, game_id: str) -> dict:
        game, runtime = await self._load_runtime(game_id)
        if game.status != GameStatus.PAUSED:
            raise GameNotActive("Game is not paused")

        runtime.resume_session()

        async with atomic(self.db):
            game.status = GameStatus.ACTIVE

        await self.db.commit()
        return {"game_id": game_id, "status": GameStatus.ACTIVE}

    async def record_hand_completed(self, game_id: str) -> dict:
        """Called after resolve_hand to advance session counters."""
        game, runtime = await self._load_runtime(game_id)
        runtime.record_hand_completed()

        # Check if blind level should advance
        advanced = False
        if runtime.blind_clock.should_advance(hands_per_level=10):
            room_config = await load_room_snapshot(self.db, game_id)
            max_level = max((bl.level for bl in room_config.blind_levels), default=1)
            if game.current_blind_level < max_level:
                runtime.blind_clock.advance()
                async with atomic(self.db):
                    game.current_blind_level = runtime.blind_clock.current_level
                await self.db.commit()
                advanced = True

        return {
            "game_id": game_id,
            "hands_played": runtime.hands_played,
            "blind_level_advanced": advanced,
            "current_blind_level": runtime.blind_clock.current_level,
        }
