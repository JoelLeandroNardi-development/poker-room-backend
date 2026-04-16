
from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

@dataclass(frozen=True, slots=True)
class BlindLevelConfig:
    level: int
    small_blind: int
    big_blind: int
    ante: int = 0
    duration_minutes: int | None = None

@dataclass(frozen=True, slots=True)
class PlayerConfig:
    player_id: str
    seat_number: int
    chip_count: int
    is_active: bool
    is_eliminated: bool

@dataclass(frozen=True, slots=True)
class RoomConfig:
    room_id: str
    starting_dealer_seat: int
    players: list[PlayerConfig]
    blind_levels: list[BlindLevelConfig]

    @property
    def active_players(self) -> list[PlayerConfig]:
        return sorted(
            [p for p in self.players if p.is_active and not p.is_eliminated],
            key=lambda p: p.seat_number,
        )

    @property
    def active_seats(self) -> list[int]:
        return [p.seat_number for p in self.active_players]

    def blind_level(self, level_num: int) -> BlindLevelConfig | None:
        return next((bl for bl in self.blind_levels if bl.level == level_num), None)

class RoomConfigProvider(Protocol):
    async def fetch_live(self, room_id: str) -> RoomConfig:
        ...

    async def save_snapshot(self, game_id: str, config: RoomConfig) -> None:
        ...

    async def load_snapshot(self, game_id: str) -> RoomConfig:
        ...