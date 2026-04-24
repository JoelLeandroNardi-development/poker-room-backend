from __future__ import annotations

from dataclasses import dataclass

from ..domain.engine.table_runtime import BlindClock
from ..domain.integration.room_adapter import RoomConfig
from ..domain.models import Game
from shared.core.time import ensure_utc

@dataclass(frozen=True, slots=True)
class HandCompletionResult:
    hands_played: int
    hands_at_current_level: int
    current_blind_level: int
    level_started_at: object
    blind_level_advanced: bool

def apply_hand_completion(
    game: Game,
    room_config: RoomConfig,
    *,
    should_count_hand: bool,
) -> HandCompletionResult:
    blind_clock = BlindClock(
        current_level=game.current_blind_level,
        level_started_at=ensure_utc(game.level_started_at),
        hands_at_level=game.hands_at_current_level,
    )

    hands_played = game.hands_played
    advanced = False

    if should_count_hand:
        hands_played += 1
        blind_clock.record_hand()

        max_level = max((bl.level for bl in room_config.blind_levels), default=1)
        current_bl = room_config.blind_level(game.current_blind_level)
        seconds_per_level = (
            current_bl.duration_minutes * 60
            if current_bl and current_bl.duration_minutes
            else None
        )

        if blind_clock.should_advance(seconds_per_level=seconds_per_level):
            if game.current_blind_level < max_level:
                blind_clock.advance()
                advanced = True

    return HandCompletionResult(
        hands_played=hands_played,
        hands_at_current_level=blind_clock.hands_at_level,
        current_blind_level=blind_clock.current_level,
        level_started_at=blind_clock.level_started_at,
        blind_level_advanced=advanced,
    )