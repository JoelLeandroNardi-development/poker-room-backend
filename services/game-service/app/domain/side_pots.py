"""
Pure side-pot calculator for Texas Hold'em.

Algorithm
---------
1. Accept a list of player contributions (final, end-of-hand).
2. Sort players by ``committed_this_hand`` ascending.
3. Walk through each *distinct* commitment level.  At each level the
   "slice" is ``(current_level - previous_level) * players_still_contributing``.
   That slice forms a pot.
4. Players who folded still *contribute* chips they already put in, but
   they are **not** eligible to win any pot.
5. Players who neither reached showdown nor folded (e.g. disconnected)
   are also ineligible.
6. Pots with zero eligible winners are merged into the next higher pot
   (the chips are "dead" and awarded to the smallest pot that has at
   least one eligible winner).

The output is a deterministic, ordered list of ``Pot`` dataclasses.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class PlayerContribution:
    """Input: one player's end-of-hand state."""

    player_id: str
    committed_this_hand: int
    has_folded: bool
    reached_showdown: bool


@dataclass(frozen=True, slots=True)
class Pot:
    """Output: a single (main / side) pot."""

    pot_index: int
    amount: int
    contributor_player_ids: tuple[str, ...]
    eligible_winner_player_ids: tuple[str, ...]


def calculate_side_pots(players: list[PlayerContribution]) -> list[Pot]:
    """
    Calculate all main and side pots for a completed hand.

    Parameters
    ----------
    players:
        Every player who was dealt into the hand, with their total
        commitment and fold / showdown status.

    Returns
    -------
    list[Pot]
        Ordered pots (index 0 = main pot, 1+ = side pots).
        Empty list if no chips were committed.
    """
    if not players:
        return []

    # Sort by commitment (ascending) so we can peel off pots layer by layer.
    sorted_players = sorted(players, key=lambda p: p.committed_this_hand)

    raw_pots: list[dict] = []
    previous_level = 0

    for i, player in enumerate(sorted_players):
        current_level = player.committed_this_hand
        if current_level <= previous_level:
            continue  # same tier as a previous player — already accounted for

        # How many players committed at least this much?
        contributors: list[str] = []
        eligible: list[str] = []

        for p in sorted_players:
            if p.committed_this_hand > previous_level:
                # This player contributes to this pot slice
                contributors.append(p.player_id)
                if not p.has_folded and p.reached_showdown:
                    eligible.append(p.player_id)

        slice_per_player = current_level - previous_level
        pot_amount = slice_per_player * len(contributors)

        raw_pots.append(
            {
                "amount": pot_amount,
                "contributors": tuple(contributors),
                "eligible": tuple(eligible),
            }
        )
        previous_level = current_level

    # Merge pots that have zero eligible winners into the *next* pot that does.
    # If the very last pot(s) have no eligible winner we merge backward instead.
    merged: list[dict] = _merge_dead_pots(raw_pots)

    return [
        Pot(
            pot_index=idx,
            amount=p["amount"],
            contributor_player_ids=p["contributors"],
            eligible_winner_player_ids=p["eligible"],
        )
        for idx, p in enumerate(merged)
    ]


def _merge_dead_pots(raw_pots: list[dict]) -> list[dict]:
    """Merge pots with no eligible winners into adjacent pots."""
    if not raw_pots:
        return []

    # Forward pass: if a pot has no eligible winners, push its amount
    # forward into the next pot that *does* have eligible winners.
    result: list[dict] = []
    carry_amount = 0
    carry_contributors: list[str] = []

    for pot in raw_pots:
        combined_amount = pot["amount"] + carry_amount
        combined_contributors = _unique_ordered(
            list(carry_contributors) + list(pot["contributors"])
        )

        if pot["eligible"]:
            result.append(
                {
                    "amount": combined_amount,
                    "contributors": tuple(combined_contributors),
                    "eligible": pot["eligible"],
                }
            )
            carry_amount = 0
            carry_contributors = []
        else:
            carry_amount = combined_amount
            carry_contributors = combined_contributors

    # If there is leftover carry (last pot(s) had no eligible winners),
    # merge backward into the last pot that has eligible winners.
    if carry_amount > 0 and result:
        last = result[-1]
        result[-1] = {
            "amount": last["amount"] + carry_amount,
            "contributors": tuple(
                _unique_ordered(list(last["contributors"]) + list(carry_contributors))
            ),
            "eligible": last["eligible"],
        }
    elif carry_amount > 0:
        # Every pot is dead (all players folded) — return a single pot
        # with the full amount and no eligible winners.
        result.append(
            {
                "amount": carry_amount,
                "contributors": tuple(carry_contributors),
                "eligible": (),
            }
        )

    return result


def _unique_ordered(items: list[str]) -> list[str]:
    """De-duplicate while preserving order."""
    seen: set[str] = set()
    out: list[str] = []
    for item in items:
        if item not in seen:
            seen.add(item)
            out.append(item)
    return out
