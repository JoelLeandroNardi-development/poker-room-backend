
from __future__ import annotations

from dataclasses import dataclass

@dataclass(frozen=True, slots=True)
class ActionSeat:

    player_id: str
    seat_number: int
    has_folded: bool
    is_all_in: bool
    is_active_in_hand: bool
    committed_this_street: int

@dataclass(frozen=True, slots=True)
class NextActorResult:

    player_id: str | None
    seat_number: int | None
    is_round_closed: bool

def _can_act(p: ActionSeat) -> bool:
    return p.is_active_in_hand and not p.has_folded and not p.is_all_in

def _needs_action(p: ActionSeat, highest_bet: int) -> bool:
    return _can_act(p) and p.committed_this_street < highest_bet

def next_to_act(
    players: list[ActionSeat],
    current_actor_seat: int,
    last_aggressor_seat: int | None,
    current_highest_bet: int,
) -> NextActorResult:
    eligible = [p for p in players if _can_act(p)]

    if len(eligible) < 2:
        return NextActorResult(player_id=None, seat_number=None, is_round_closed=True)

    ordered = sorted(eligible, key=lambda p: p.seat_number)
    n = len(ordered)

    start_idx = 0
    for i, p in enumerate(ordered):
        if p.seat_number > current_actor_seat:
            start_idx = i
            break
    else:
        start_idx = 0

    for step in range(n):
        idx = (start_idx + step) % n
        candidate = ordered[idx]

        if (
            last_aggressor_seat is not None
            and candidate.seat_number == last_aggressor_seat
        ):
            return NextActorResult(
                player_id=None, seat_number=None, is_round_closed=True,
            )

        if _needs_action(candidate, current_highest_bet):
            return NextActorResult(
                player_id=candidate.player_id,
                seat_number=candidate.seat_number,
                is_round_closed=False,
            )

    return NextActorResult(player_id=None, seat_number=None, is_round_closed=True)