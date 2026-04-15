"""Pure-function forced-bet posting for Texas Hold'em round start.

Posts small blind, big blind, and optional antes as real chip commitments
before any player action begins.  Short-stacked players go all-in for
whatever they can cover.

Order of deductions (matches live-poker convention):
  1. Ante from every active player  (if ante_amount > 0)
  2. Small blind from the SB seat
  3. Big blind from the BB seat

Each deduction is capped at the player's remaining stack at that step.
"""

from __future__ import annotations

from dataclasses import dataclass


# ── Input ────────────────────────────────────────────────────────────

@dataclass(frozen=True)
class SeatPlayer:
    """Minimal per-player input: identity, position, and available chips."""

    player_id: str
    seat_number: int
    stack: int


# ── Output ───────────────────────────────────────────────────────────

@dataclass(frozen=True)
class PostedPlayer:
    """Per-player state after forced bets are posted."""

    player_id: str
    seat_number: int
    stack_remaining: int
    committed_this_street: int
    committed_this_hand: int
    is_all_in: bool


@dataclass(frozen=True)
class BlindPostingResult:
    """Aggregate result of blind & ante posting."""

    players: list[PostedPlayer]
    pot_total: int
    current_highest_bet: int


# ── Core function ────────────────────────────────────────────────────

def post_blinds_and_antes(
    players: list[SeatPlayer],
    small_blind_seat: int,
    big_blind_seat: int,
    small_blind_amount: int,
    big_blind_amount: int,
    ante_amount: int = 0,
) -> BlindPostingResult:
    """Post forced bets and return the resulting player states + pot.

    Parameters
    ----------
    players:
        Active players at the table, in any order.
    small_blind_seat / big_blind_seat:
        Seat numbers that owe the small / big blind.
    small_blind_amount / big_blind_amount:
        Nominal blind sizes for the current level.
    ante_amount:
        Per-player ante.  0 means no ante.

    Returns
    -------
    BlindPostingResult with updated player list, pot total, and
    current_highest_bet (= max committed_this_street).
    """
    posted: list[PostedPlayer] = []

    for p in players:
        remaining = p.stack
        committed = 0

        # 1. Ante
        if ante_amount > 0:
            ante = min(ante_amount, remaining)
            committed += ante
            remaining -= ante

        # 2. Blind (only one of SB / BB, never both)
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
