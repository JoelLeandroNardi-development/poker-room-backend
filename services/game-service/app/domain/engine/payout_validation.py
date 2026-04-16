
from __future__ import annotations

from .side_pots import PlayerContribution, Pot, calculate_side_pots
from ..exceptions import PayoutExceedsPot, PayoutMismatch
from ..models import RoundPlayer

def validate_payouts_against_side_pots(
    round_players: list[RoundPlayer],
    submitted_payouts: list[dict],
    total_pot: int,
) -> list[Pot]:
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