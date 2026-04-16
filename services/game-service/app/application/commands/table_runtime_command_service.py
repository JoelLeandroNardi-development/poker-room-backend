
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
from ...infrastructure.logging import get_logger
from ...infrastructure.repository import fetch_or_raise
from ...infrastructure.room_config import load_room_snapshot
from shared.core.db.session import atomic

logger = get_logger("game-service.table_runtime")


def _build_runtime_from_game(game: Game, seats: list[TableSeat]) -> TableRuntime:
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
        blind_clock=BlindClock(
            current_level=game.current_blind_level,
            hands_at_level=game.hands_at_current_level,
        ),
        hands_played=game.hands_played,
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

        logger.info(
            "table paused",
            game_id=game_id,
            hands_played=game.hands_played,
            blind_level=game.current_blind_level,
        )
        return {"game_id": game_id, "status": GameStatus.PAUSED}

    async def resume_table(self, game_id: str) -> dict:
        game, runtime = await self._load_runtime(game_id)
        if game.status != GameStatus.PAUSED:
            raise GameNotActive("Game is not paused")

        runtime.resume_session()

        async with atomic(self.db):
            game.status = GameStatus.ACTIVE

        await self.db.commit()

        logger.info(
            "table resumed",
            game_id=game_id,
            hands_played=game.hands_played,
            blind_level=game.current_blind_level,
        )
        return {"game_id": game_id, "status": GameStatus.ACTIVE}

    async def record_hand_completed(self, game_id: str) -> dict:
        game, runtime = await self._load_runtime(game_id)
        runtime.record_hand_completed()

        advanced = False
        room_config = await load_room_snapshot(self.db, game_id)
        max_level = max((bl.level for bl in room_config.blind_levels), default=1)

        if runtime.blind_clock.should_advance(hands_per_level=10):
            if game.current_blind_level < max_level:
                runtime.blind_clock.advance()
                advanced = True

        async with atomic(self.db):
            game.hands_played = runtime.hands_played
            game.hands_at_current_level = runtime.blind_clock.hands_at_level
            game.current_blind_level = runtime.blind_clock.current_level

        await self.db.commit()

        if advanced:
            logger.info(
                "blind level advanced",
                game_id=game_id,
                new_level=runtime.blind_clock.current_level,
                hands_played=runtime.hands_played,
            )
        else:
            logger.info(
                "hand completed",
                game_id=game_id,
                hands_played=runtime.hands_played,
                hands_at_current_level=runtime.blind_clock.hands_at_level,
                blind_level=runtime.blind_clock.current_level,
            )

        return {
            "game_id": game_id,
            "hands_played": runtime.hands_played,
            "hands_at_current_level": runtime.blind_clock.hands_at_level,
            "blind_level_advanced": advanced,
            "current_blind_level": runtime.blind_clock.current_level,
        }

    async def get_session_status(self, game_id: str) -> dict:
        game = await fetch_or_raise(
            self.db, Game,
            filter_column=Game.game_id,
            filter_value=game_id,
            detail=ErrorMessage.GAME_NOT_FOUND,
        )
        room_config = await load_room_snapshot(self.db, game_id)
        max_level = max((bl.level for bl in room_config.blind_levels), default=1)
        current_bl = next(
            (bl for bl in room_config.blind_levels if bl.level == game.current_blind_level),
            None,
        )

        hands_until_advance: int | None = None
        hands_per_level = 10
        remaining = hands_per_level - game.hands_at_current_level
        if remaining > 0 and game.current_blind_level < max_level:
            hands_until_advance = remaining

        return {
            "game_id": game.game_id,
            "status": game.status,
            "hands_played": game.hands_played,
            "current_blind_level": game.current_blind_level,
            "hands_at_current_level": game.hands_at_current_level,
            "hands_until_blind_advance": hands_until_advance,
            "max_blind_level": max_level,
            "small_blind": current_bl.small_blind if current_bl else None,
            "big_blind": current_bl.big_blind if current_bl else None,
            "ante": current_bl.ante if current_bl else 0,
            "dealer_seat": game.current_dealer_seat,
        }
