"""Table runtime — session lifecycle layer above the single-hand engine.

This module owns concerns that span *multiple hands* within one game
session:

- **Hand numbering** — sequential round numbering for the session.
- **Seat management** — sit-out / sit-in between hands.
- **Session pause / resume** — freeze state without losing context.
- **Blind clock** — track when to advance blind levels based on
  elapsed time or hands played.

The table runtime is a **pure state machine** — no IO, no ORM.
Application services translate between ORM objects and this layer.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum


class SeatStatus(str, Enum):
    ACTIVE = "ACTIVE"
    SITTING_OUT = "SITTING_OUT"
    EMPTY = "EMPTY"


class TableStatus(str, Enum):
    WAITING = "WAITING"
    RUNNING = "RUNNING"
    PAUSED = "PAUSED"
    FINISHED = "FINISHED"


@dataclass
class TableSeat:
    """One seat at the table."""

    seat_number: int
    player_id: str | None = None
    status: str = SeatStatus.EMPTY
    chip_count: int = 0
    hands_sat_out: int = 0


@dataclass
class BlindClock:
    """Tracks blind level progression."""

    current_level: int = 1
    level_started_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    hands_at_level: int = 0

    def should_advance(
        self,
        hands_per_level: int | None = None,
        seconds_per_level: int | None = None,
        now: datetime | None = None,
    ) -> bool:
        """Check if the blind level should advance based on policy."""
        if hands_per_level is not None and self.hands_at_level >= hands_per_level:
            return True
        if seconds_per_level is not None:
            now = now or datetime.now(timezone.utc)
            elapsed = (now - self.level_started_at).total_seconds()
            if elapsed >= seconds_per_level:
                return True
        return False

    def advance(self) -> int:
        """Advance to the next blind level. Returns the new level number."""
        self.current_level += 1
        self.level_started_at = datetime.now(timezone.utc)
        self.hands_at_level = 0
        return self.current_level

    def record_hand(self) -> None:
        """Record that a hand was completed at the current level."""
        self.hands_at_level += 1


@dataclass
class TableRuntime:
    """Pure state machine for the table session."""

    game_id: str
    status: str = TableStatus.WAITING
    seats: list[TableSeat] = field(default_factory=list)
    blind_clock: BlindClock = field(default_factory=BlindClock)
    hands_played: int = 0
    dealer_seat: int | None = None

    @property
    def active_seats(self) -> list[TableSeat]:
        return [s for s in self.seats if s.status == SeatStatus.ACTIVE and s.player_id]

    @property
    def seated_count(self) -> int:
        return sum(1 for s in self.seats if s.player_id is not None)

    def can_start_hand(self) -> bool:
        return self.status == TableStatus.RUNNING and len(self.active_seats) >= 2

    def start_session(self) -> None:
        if len(self.active_seats) < 2:
            raise ValueError("Need at least 2 active players")
        self.status = TableStatus.RUNNING

    def pause_session(self) -> None:
        self.status = TableStatus.PAUSED

    def resume_session(self) -> None:
        if self.status != TableStatus.PAUSED:
            raise ValueError("Can only resume a paused session")
        self.status = TableStatus.RUNNING

    def finish_session(self) -> None:
        self.status = TableStatus.FINISHED

    def sit_out(self, seat_number: int) -> None:
        seat = self._get_seat(seat_number)
        if seat.status != SeatStatus.ACTIVE:
            raise ValueError(f"Seat {seat_number} is not active")
        seat.status = SeatStatus.SITTING_OUT
        seat.hands_sat_out = 0

    def sit_in(self, seat_number: int) -> None:
        seat = self._get_seat(seat_number)
        if seat.status != SeatStatus.SITTING_OUT:
            raise ValueError(f"Seat {seat_number} is not sitting out")
        seat.status = SeatStatus.ACTIVE
        seat.hands_sat_out = 0

    def record_hand_completed(self) -> None:
        """Call after each hand finishes."""
        self.hands_played += 1
        self.blind_clock.record_hand()
        for s in self.seats:
            if s.status == SeatStatus.SITTING_OUT:
                s.hands_sat_out += 1

    def next_hand_number(self) -> int:
        return self.hands_played + 1

    def _get_seat(self, seat_number: int) -> TableSeat:
        for s in self.seats:
            if s.seat_number == seat_number:
                return s
        raise ValueError(f"Seat {seat_number} not found")
