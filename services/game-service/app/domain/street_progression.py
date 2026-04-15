"""
Pure street-progression engine for Texas Hold'em.

Algorithm
---------
After all players have acted on a street the caller invokes
``evaluate_street_end`` which inspects the hand state and returns one of
three outcomes:

NEXT_STREET
    Normal case — advance to the next betting round.  The result
    includes the *next_street* and the *acting_player_id* (first to
    act on that street).

SETTLE_HAND
    Only one player remains (everyone else has folded).  The hand is
    over and the remaining player wins by default.  ``winning_player_id``
    is set.

SHOWDOWN
    No more betting is possible — either the river action is
    complete or all remaining players are all-in.  The hand must
    proceed to showdown / hand evaluation.

First-to-act rules
~~~~~~~~~~~~~~~~~~~
- **Post-flop** (FLOP / TURN / RIVER): first active non-all-in
  player **left of the dealer** (clockwise).
- **Pre-flop** first-to-act is computed in ``start_round()`` (UTG,
  left of big blind) and is *not* part of this module.
"""

from __future__ import annotations

from dataclasses import dataclass

from .constants import Street, StreetAdvanceAction

STREET_ORDER: tuple[str, ...] = (
    Street.PRE_FLOP,
    Street.FLOP,
    Street.TURN,
    Street.RIVER,
    Street.SHOWDOWN,
)


# ------------------------------------------------------------------
# Data types
# ------------------------------------------------------------------

@dataclass(frozen=True, slots=True)
class PlayerSeat:
    """Lightweight projection of a RoundPlayer for pure logic."""

    player_id: str
    seat_number: int
    has_folded: bool
    is_all_in: bool
    is_active_in_hand: bool


@dataclass(frozen=True, slots=True)
class StreetAdvanceResult:
    """What should happen after the current street's action ends."""

    action: str  # StreetAdvanceAction value
    next_street: str | None = None
    acting_player_id: str | None = None
    winning_player_id: str | None = None


# ------------------------------------------------------------------
# Public helpers
# ------------------------------------------------------------------

def next_street(current: str) -> str | None:
    """Return the street that follows *current*, or ``None`` if terminal."""
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
    """
    Return the player_id of the first eligible player **clockwise**
    from *reference_seat*.

    Eligible players are assumed to be non-folded, non-all-in, active.
    """
    if not eligible:
        return None
    sorted_players = sorted(eligible, key=lambda p: p.seat_number)
    for p in sorted_players:
        if p.seat_number > reference_seat:
            return p.player_id
    # Wrap around
    return sorted_players[0].player_id


# ------------------------------------------------------------------
# Core evaluator
# ------------------------------------------------------------------

def evaluate_street_end(
    current_street: str,
    dealer_seat: int,
    big_blind_seat: int,  # noqa: ARG001 — reserved for pre-flop awareness
    players: list[PlayerSeat],
) -> StreetAdvanceResult:
    """
    Determine what happens after the current street's action is complete.

    Parameters
    ----------
    current_street:
        The street that just finished (e.g. ``Street.PRE_FLOP``).
    dealer_seat:
        Seat number of the dealer button.
    big_blind_seat:
        Seat number of the big blind (unused today, reserved).
    players:
        All players dealt into the hand.

    Returns
    -------
    StreetAdvanceResult
    """
    not_folded = [
        p for p in players
        if not p.has_folded and p.is_active_in_hand
    ]

    # --- Only one player left → immediate settlement ---
    if len(not_folded) <= 1:
        return StreetAdvanceResult(
            action=StreetAdvanceAction.SETTLE_HAND,
            winning_player_id=not_folded[0].player_id if not_folded else None,
        )

    # --- River (or already showdown) → showdown ---
    if current_street in (Street.RIVER, Street.SHOWDOWN):
        return StreetAdvanceResult(
            action=StreetAdvanceAction.SHOWDOWN,
            next_street=Street.SHOWDOWN,
        )

    # --- Check how many players can still act ---
    can_act = [p for p in not_folded if not p.is_all_in]

    if len(can_act) <= 1:
        # All remaining players are all-in (or only 1 has chips) →
        # no further betting is possible → showdown.
        return StreetAdvanceResult(
            action=StreetAdvanceAction.SHOWDOWN,
            next_street=Street.SHOWDOWN,
        )

    # --- Normal advance to next street ---
    ns = next_street(current_street)

    # Post-flop: first to act is left of dealer among eligible
    acting = find_first_to_act(can_act, dealer_seat)

    return StreetAdvanceResult(
        action=StreetAdvanceAction.NEXT_STREET,
        next_street=ns,
        acting_player_id=acting,
    )
