"""Validate dealer-submitted payouts against the computed side-pot structure.

This module bridges ``side_pots.calculate_side_pots`` and the
``ResolveHandRequest`` data to ensure the dealer cannot award more
chips from any pot than actually exist, and that only eligible players
receive payouts.
"""

from __future__ import annotations

from .exceptions import PayoutExceedsPot, PayoutMismatch
from .models import RoundPlayer
from .side_pots import PlayerContribution, Pot, calculate_side_pots


def validate_payouts_against_side_pots(
    round_players: list[RoundPlayer],
    submitted_payouts: list[dict],
    total_pot: int,
) -> list[Pot]:
    """Validate submitted payouts against the computed pot structure.

    Parameters
    ----------
    round_players :
        All players in the round (ORM instances).
    submitted_payouts :
        List of dicts with ``pot_index``, ``amount``, and ``winners``
        (each winner has ``player_id`` and ``amount``).
    total_pot :
        The round's total pot amount.

    Returns
    -------
    list[Pot]
        The computed pots (for informational / logging purposes).

    Raises
    ------
    PayoutExceedsPot
        If a submitted pot's total exceeds the computed pot's amount.
    PayoutMismatch
        If a winner is not eligible for the pot they're winning from.
    """
    contributions = [
        PlayerContribution(
            player_id=rp.player_id,
            committed_this_hand=rp.committed_this_hand,
            has_folded=rp.has_folded,
            reached_showdown=not rp.has_folded and rp.is_active_in_hand,
        )
        for rp in round_players
    ]

    computed_pots = calculate_side_pots(contributions)

    if not computed_pots:
        return computed_pots

    # Build a lookup: pot_index → computed Pot
    computed_map: dict[int, Pot] = {p.pot_index: p for p in computed_pots}

    for submitted in submitted_payouts:
        idx = submitted["pot_index"]
        computed = computed_map.get(idx)

        if computed is None:
            raise PayoutMismatch(
                f"Submitted pot_index {idx} does not exist in the computed pot structure"
            )

        submitted_total = sum(w["amount"] for w in submitted["winners"])
        if submitted_total > computed.amount:
            raise PayoutExceedsPot(
                f"Pot {idx} payout ({submitted_total}) exceeds computed pot ({computed.amount})"
            )

        eligible_set = set(computed.eligible_winner_player_ids)
        for w in submitted["winners"]:
            if w["player_id"] not in eligible_set:
                raise PayoutMismatch(
                    f"Player {w['player_id']} is not eligible to win pot {idx}"
                )

    return computed_pots
