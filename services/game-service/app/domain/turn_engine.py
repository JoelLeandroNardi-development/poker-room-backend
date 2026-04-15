"""
Per-action turn engine for Texas Hold'em.

Given the current hand state and the player who just acted, determines
who must act next — or signals that the betting round is closed.

This module is **pure** (no DB, no IO).  It reuses `PlayerSeat` from
``street_progression`` for its input type.

Rules
-----
- Skip folded players.
- Skip all-in players (they cannot act).
- Skip inactive players.
- Walk clockwise (ascending seat order with wrap) from the player
  who just acted.
- The betting round is **closed** when we wrap all the way around back
  to the *last aggressor* (the opener / last raiser) without finding
  anyone who still needs to act, **or** when fewer than 2 players can
  act.

The caller tells us:
- ``players`` — all seats dealt into the hand
- ``current_actor_seat`` — the seat of the player who just finished acting
- ``last_aggressor_seat`` — the seat of the player who last bet/raised
  (or the first forced actor for a fresh street, i.e. the opener)
- ``current_highest_bet`` — the highest bet on this street
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class ActionSeat:
    """Lightweight projection of a RoundPlayer for turn calculation."""

    player_id: str
    seat_number: int
    has_folded: bool
    is_all_in: bool
    is_active_in_hand: bool
    committed_this_street: int


@dataclass(frozen=True, slots=True)
class NextActorResult:
    """Result of the next-to-act calculation."""

    player_id: str | None
    seat_number: int | None
    is_round_closed: bool


def _can_act(p: ActionSeat) -> bool:
    """Return True if the player is eligible to take a betting action."""
    return p.is_active_in_hand and not p.has_folded and not p.is_all_in


def _needs_action(p: ActionSeat, highest_bet: int) -> bool:
    """
    Return True if an eligible player still needs to act.

    A player needs to act if they haven't yet matched the current
    highest bet.  A player who *is* the last aggressor does **not**
    need to act again (handled by the caller via *last_aggressor_seat*).
    """
    return _can_act(p) and p.committed_this_street < highest_bet


def next_to_act(
    players: list[ActionSeat],
    current_actor_seat: int,
    last_aggressor_seat: int | None,
    current_highest_bet: int,
) -> NextActorResult:
    """
    Determine who acts next after *current_actor_seat*.

    Parameters
    ----------
    players:
        All players dealt into the hand (any order).
    current_actor_seat:
        The seat that just finished acting.
    last_aggressor_seat:
        The seat of the player who last bet or raised this street.
        On a fresh street with no voluntary action yet, this should be
        the first-to-act (opener) so the round closes when it wraps
        back to them.  ``None`` means there is no aggressor yet (rare).
    current_highest_bet:
        The current highest bet on this street.

    Returns
    -------
    NextActorResult
        ``player_id`` / ``seat_number`` of the next player, or
        ``is_round_closed=True`` with ``None`` fields if the betting
        round is over.
    """
    eligible = [p for p in players if _can_act(p)]

    # Fewer than 2 eligible → nobody to bet against → round closed
    if len(eligible) < 2:
        return NextActorResult(player_id=None, seat_number=None, is_round_closed=True)

    # Build a clockwise-ordered ring starting *after* current_actor_seat
    ordered = sorted(eligible, key=lambda p: p.seat_number)
    n = len(ordered)

    # Find the starting index: the first player whose seat is strictly
    # after current_actor_seat; if none, wrap to the beginning.
    start_idx = 0
    for i, p in enumerate(ordered):
        if p.seat_number > current_actor_seat:
            start_idx = i
            break
    else:
        start_idx = 0  # wrap around

    # Walk up to n steps clockwise
    for step in range(n):
        idx = (start_idx + step) % n
        candidate = ordered[idx]

        # Skip back to the aggressor — that means we've gone full circle
        if (
            last_aggressor_seat is not None
            and candidate.seat_number == last_aggressor_seat
        ):
            # The aggressor only needs to act again if someone raised
            # *after* them (which would make someone else the aggressor).
            # Since we track the *current* aggressor, arriving back at
            # them means the round is closed.
            return NextActorResult(
                player_id=None, seat_number=None, is_round_closed=True,
            )

        # Does this player still owe chips or haven't had a chance to act?
        if _needs_action(candidate, current_highest_bet):
            return NextActorResult(
                player_id=candidate.player_id,
                seat_number=candidate.seat_number,
                is_round_closed=False,
            )

    # Walked the whole ring without finding anyone → closed
    return NextActorResult(player_id=None, seat_number=None, is_round_closed=True)
