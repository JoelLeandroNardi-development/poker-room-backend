
from __future__ import annotations

from dataclasses import dataclass

@dataclass(frozen=True, slots=True)
class PlayerContribution:
    player_id: str
    committed_this_hand: int
    has_folded: bool
    reached_showdown: bool

@dataclass(frozen=True, slots=True)
class Pot:
    pot_index: int
    amount: int
    contributor_player_ids: tuple[str, ...]
    eligible_winner_player_ids: tuple[str, ...]

def calculate_side_pots(players: list[PlayerContribution]) -> list[Pot]:
    if not players:
        return []

    sorted_players = sorted(players, key=lambda p: p.committed_this_hand)

    raw_pots: list[dict] = []
    previous_level = 0

    for i, player in enumerate(sorted_players):
        current_level = player.committed_this_hand
        if current_level <= previous_level:
            continue

        contributors: list[str] = []
        eligible: list[str] = []

        for p in sorted_players:
            if p.committed_this_hand > previous_level:
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
    if not raw_pots:
        return []

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
        result.append(
            {
                "amount": carry_amount,
                "contributors": tuple(carry_contributors),
                "eligible": (),
            }
        )

    return result

def _unique_ordered(items: list[str]) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for item in items:
        if item not in seen:
            seen.add(item)
            out.append(item)
    return out