"""Settlement explanation engine.

Produces a structured, human-readable explanation of how the pot was
split among players.  Given the same inputs that
``payout_validation.validate_payouts_against_side_pots`` consumes, this
module builds a narrative showing:

- How each pot was formed (who contributed, how much).
- Who was eligible to win each pot and why.
- Which players were *ineligible* (folded, etc.) and why.
- The actual winner(s) and amounts awarded.

This is a **pure** module — no IO, no ORM types in public signatures.

Usage::

    explanation = explain_settlement(contributions, submitted_payouts)
"""

from __future__ import annotations

from dataclasses import dataclass, field

from .side_pots import PlayerContribution, Pot, calculate_side_pots


# ── Output types ─────────────────────────────────────────────────────

@dataclass(frozen=True, slots=True)
class WinnerDetail:
    """One winner's share from a single pot."""

    player_id: str
    amount: int


@dataclass(frozen=True, slots=True)
class PotExplanation:
    """Full explanation of a single (main / side) pot."""

    pot_index: int
    pot_label: str  # "Main Pot", "Side Pot 1", etc.
    amount: int
    contributor_player_ids: tuple[str, ...]
    eligible_player_ids: tuple[str, ...]
    ineligible_reasons: dict[str, str]  # player_id → reason
    winners: list[WinnerDetail]
    awarded_total: int
    unclaimed: int  # amount - awarded_total


@dataclass(slots=True)
class SettlementExplanation:
    """Complete settlement narrative for a hand."""

    total_pot: int = 0
    total_awarded: int = 0
    total_unclaimed: int = 0
    pots: list[PotExplanation] = field(default_factory=list)
    narrative: list[str] = field(default_factory=list)


# ── Public API ───────────────────────────────────────────────────────

def explain_settlement(
    contributions: list[PlayerContribution],
    submitted_payouts: list[dict] | None = None,
) -> SettlementExplanation:
    """Build a human-readable explanation of the settlement.

    Parameters
    ----------
    contributions:
        Per-player end-of-hand contributions (same input as
        ``calculate_side_pots``).
    submitted_payouts:
        Optional list of pot payouts (``pot_index``, ``winners``).
        If ``None``, the explanation covers pot structure only.

    Returns
    -------
    SettlementExplanation
    """
    computed_pots = calculate_side_pots(contributions)

    # Index submitted payouts by pot_index for quick lookup
    payout_map: dict[int, list[dict]] = {}
    if submitted_payouts:
        for sp in submitted_payouts:
            payout_map[sp["pot_index"]] = sp.get("winners", [])

    # Build a lookup of player fold / showdown status
    player_status: dict[str, PlayerContribution] = {
        c.player_id: c for c in contributions
    }

    result = SettlementExplanation()
    total_pot = 0
    total_awarded = 0

    for pot in computed_pots:
        pot_label = "Main Pot" if pot.pot_index == 0 else f"Side Pot {pot.pot_index}"
        total_pot += pot.amount

        # Determine ineligible reasons
        ineligible: dict[str, str] = {}
        eligible_set = set(pot.eligible_winner_player_ids)
        for cid in pot.contributor_player_ids:
            if cid not in eligible_set:
                pc = player_status.get(cid)
                if pc and pc.has_folded:
                    ineligible[cid] = "folded"
                elif pc and not pc.reached_showdown:
                    ineligible[cid] = "did not reach showdown"
                else:
                    ineligible[cid] = "ineligible"

        # Map winners
        winners: list[WinnerDetail] = []
        pot_winners = payout_map.get(pot.pot_index, [])
        for w in pot_winners:
            winners.append(WinnerDetail(
                player_id=w["player_id"],
                amount=w["amount"],
            ))
        awarded = sum(w.amount for w in winners)
        total_awarded += awarded

        pot_exp = PotExplanation(
            pot_index=pot.pot_index,
            pot_label=pot_label,
            amount=pot.amount,
            contributor_player_ids=pot.contributor_player_ids,
            eligible_player_ids=pot.eligible_winner_player_ids,
            ineligible_reasons=ineligible,
            winners=winners,
            awarded_total=awarded,
            unclaimed=pot.amount - awarded,
        )
        result.pots.append(pot_exp)

    result.total_pot = total_pot
    result.total_awarded = total_awarded
    result.total_unclaimed = total_pot - total_awarded

    # Build narrative sentences
    result.narrative = _build_narrative(result, player_status)
    return result


# ── Narrative builder ────────────────────────────────────────────────

def _build_narrative(
    explanation: SettlementExplanation,
    player_status: dict[str, PlayerContribution],
) -> list[str]:
    """Generate human-readable sentences describing the settlement."""
    lines: list[str] = []

    lines.append(f"Total pot: {explanation.total_pot} chips.")

    if len(explanation.pots) == 1:
        lines.append("Single pot (no side pots).")
    else:
        lines.append(f"{len(explanation.pots)} pots (1 main + {len(explanation.pots) - 1} side).")

    for pot_exp in explanation.pots:
        lines.append(
            f"{pot_exp.pot_label}: {pot_exp.amount} chips "
            f"from {len(pot_exp.contributor_player_ids)} contributors."
        )
        if pot_exp.eligible_player_ids:
            lines.append(
                f"  Eligible: {', '.join(pot_exp.eligible_player_ids)}."
            )
        if pot_exp.ineligible_reasons:
            for pid, reason in pot_exp.ineligible_reasons.items():
                lines.append(f"  {pid} ineligible ({reason}).")

        if pot_exp.winners:
            for w in pot_exp.winners:
                lines.append(f"  → {w.player_id} wins {w.amount} chips.")
        elif pot_exp.eligible_player_ids:
            lines.append("  No winners submitted yet.")
        else:
            lines.append("  No eligible winners — dead pot.")

        if pot_exp.unclaimed > 0 and pot_exp.winners:
            lines.append(f"  Unclaimed remainder: {pot_exp.unclaimed} chips.")

    if explanation.total_unclaimed > 0 and explanation.total_awarded > 0:
        lines.append(
            f"Total unclaimed: {explanation.total_unclaimed} chips."
        )

    return lines
