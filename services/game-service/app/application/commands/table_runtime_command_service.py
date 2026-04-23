
from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from ...domain.constants import GameStatus, ErrorMessage
from ...domain.exceptions import GameNotActive
from ...domain.models import Game
from ...domain.engine.table_runtime import (
    BlindClock, SeatStatus, TableRuntime, TableSeat, TableStatus,
)
from ...domain.integration.room_adapter import RoomConfig
from ...infrastructure.logging import get_logger
from ...infrastructure.repositories.game_repository import fetch_or_raise
from ...infrastructure.room_config import load_room_snapshot
from shared.core.db.session import atomic
from shared.core.time import ensure_utc, utc_now

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
            level_started_at=ensure_utc(game.level_started_at),
            hands_at_level=game.hands_at_current_level,
        ),
        hands_played=game.hands_played,
        dealer_seat=game.current_dealer_seat,
    )

class TableRuntimeCommandService:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def _load_runtime(self, game_id: str) -> tuple[Game, TableRuntime, RoomConfig]:
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
        return game, runtime, room_config

    async def pause_table(self, game_id: str) -> dict:
        game, runtime, _room_config = await self._load_runtime(game_id)
        if game.status != GameStatus.ACTIVE:
            raise GameNotActive(ErrorMessage.GAME_NOT_ACTIVE)

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
        game, runtime, _room_config = await self._load_runtime(game_id)
        if game.status != GameStatus.PAUSED:
            raise GameNotActive(ErrorMessage.GAME_NOT_PAUSED)

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
        game, runtime, room_config = await self._load_runtime(game_id)
        runtime.record_hand_completed()

        advanced = False
        max_level = max((bl.level for bl in room_config.blind_levels), default=1)

        current_bl = room_config.blind_level(game.current_blind_level)
        seconds_per_level = (
            current_bl.duration_minutes * 60
            if current_bl and current_bl.duration_minutes
            else None
        )

        if runtime.blind_clock.should_advance(seconds_per_level=seconds_per_level):
            if game.current_blind_level < max_level:
                runtime.blind_clock.advance()
                advanced = True

        async with atomic(self.db):
            game.hands_played = runtime.hands_played
            game.hands_at_current_level = runtime.blind_clock.hands_at_level
            game.current_blind_level = runtime.blind_clock.current_level
            game.level_started_at = runtime.blind_clock.level_started_at

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

        seconds_until_blind_advance: int | None = None
        if (
            current_bl
            and current_bl.duration_minutes
            and game.level_started_at
            and game.current_blind_level < max_level
        ):
            elapsed = (utc_now() - ensure_utc(game.level_started_at)).total_seconds()
            remaining_seconds = int((current_bl.duration_minutes * 60) - elapsed)
            seconds_until_blind_advance = max(0, remaining_seconds)

        return {
            "game_id": game.game_id,
            "status": game.status,
            "hands_played": game.hands_played,
            "current_blind_level": game.current_blind_level,
            "hands_at_current_level": game.hands_at_current_level,
            "hands_until_blind_advance": None,
            "seconds_until_blind_advance": seconds_until_blind_advance,
            "max_blind_level": max_level,
            "small_blind": current_bl.small_blind if current_bl else None,
            "big_blind": current_bl.big_blind if current_bl else None,
            "ante": current_bl.ante if current_bl and room_config.antes_enabled else 0,
            "dealer_seat": game.current_dealer_seat,
        }