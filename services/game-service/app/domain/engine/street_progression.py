
from __future__ import annotations

from dataclasses import dataclass

from ..constants import Street, StreetAdvanceAction

STREET_ORDER: tuple[str, ...] = (
    Street.PRE_FLOP,
    Street.FLOP,
    Street.TURN,
    Street.RIVER,
    Street.SHOWDOWN,
)

@dataclass(frozen=True, slots=True)
class PlayerSeat:
    player_id: str
    seat_number: int
    has_folded: bool
    is_all_in: bool
    is_active_in_hand: bool

@dataclass(frozen=True, slots=True)
class StreetAdvanceResult:
    action: str
    next_street: str | None = None
    acting_player_id: str | None = None
    winning_player_id: str | None = None

def next_street(current: str) -> str | None:
    try:
        idx = STREET_ORDER.index(current)
    except ValueError:
        return None
    next_idx = idx + 1
    if next_idx >= len(STREET_ORDER):
        return None
    return STREET_ORDER[next_idx]

def find_first_to_act(
    eligible: list[PlayerSeat],
    reference_seat: int,
) -> str | None:
    if not eligible:
        return None
    sorted_players = sorted(eligible, key=lambda p: p.seat_number)
    for p in sorted_players:
        if p.seat_number > reference_seat:
            return p.player_id
    return sorted_players[0].player_id

def evaluate_street_end(
    current_street: str,
    dealer_seat: int,
    big_blind_seat: int,
    players: list[PlayerSeat],
) -> StreetAdvanceResult:
    not_folded = [
        p for p in players
        if not p.has_folded and p.is_active_in_hand
    ]

    if len(not_folded) <= 1:
        return StreetAdvanceResult(
            action=StreetAdvanceAction.SETTLE_HAND,
            winning_player_id=not_folded[0].player_id if not_folded else None,
        )

    if current_street in (Street.RIVER, Street.SHOWDOWN):
        return StreetAdvanceResult(
            action=StreetAdvanceAction.SHOWDOWN,
            next_street=Street.SHOWDOWN,
        )

    can_act = [p for p in not_folded if not p.is_all_in]

    if len(can_act) <= 1:
        return StreetAdvanceResult(
            action=StreetAdvanceAction.SHOWDOWN,
            next_street=Street.SHOWDOWN,
        )

    ns = next_street(current_street)

    acting = find_first_to_act(can_act, dealer_seat)

    return StreetAdvanceResult(
        action=StreetAdvanceAction.NEXT_STREET,
        next_street=ns,
        acting_player_id=acting,
    )