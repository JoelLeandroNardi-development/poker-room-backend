
from __future__ import annotations

from dataclasses import dataclass

@dataclass(frozen=True)
class SeatPlayer:
    player_id: str
    seat_number: int
    stack: int

@dataclass(frozen=True)
class PostedPlayer:
    player_id: str
    seat_number: int
    stack_remaining: int
    committed_this_street: int
    committed_this_hand: int
    is_all_in: bool

@dataclass(frozen=True)
class BlindPostingResult:
    players: list[PostedPlayer]
    pot_total: int
    current_highest_bet: int

def post_blinds_and_antes(
    players: list[SeatPlayer],
    small_blind_seat: int,
    big_blind_seat: int,
    small_blind_amount: int,
    big_blind_amount: int,
    ante_amount: int = 0,
) -> BlindPostingResult:
    posted: list[PostedPlayer] = []

    for p in players:
        remaining = p.stack
        committed = 0

        if ante_amount > 0:
            ante = min(ante_amount, remaining)
            committed += ante
            remaining -= ante

        if p.seat_number == small_blind_seat:
            blind = min(small_blind_amount, remaining)
            committed += blind
            remaining -= blind
        elif p.seat_number == big_blind_seat:
            blind = min(big_blind_amount, remaining)
            committed += blind
            remaining -= blind

        is_all_in = remaining == 0 and committed > 0

        posted.append(PostedPlayer(
            player_id=p.player_id,
            seat_number=p.seat_number,
            stack_remaining=remaining,
            committed_this_street=committed,
            committed_this_hand=committed,
            is_all_in=is_all_in,
        ))

    pot_total = sum(p.committed_this_street for p in posted)
    current_highest_bet = max(
        (p.committed_this_street for p in posted), default=0,
    )

    return BlindPostingResult(
        players=posted,
        pot_total=pot_total,
        current_highest_bet=current_highest_bet,
    )