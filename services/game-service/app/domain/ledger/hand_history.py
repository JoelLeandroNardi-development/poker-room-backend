
from __future__ import annotations

from dataclasses import dataclass, field

from .hand_ledger import LedgerRow

_BLIND_TYPES = frozenset({"BLIND_POSTED", "ANTE_POSTED"})
_BET_TYPES = frozenset({"BET_PLACED"})
_STREET_TYPES = frozenset({"STREET_DEALT"})
_PAYOUT_TYPES = frozenset({"PAYOUT_AWARDED"})
_COMPLETION_TYPES = frozenset({"ROUND_COMPLETED"})
_CORRECTION_TYPES = frozenset({
    "ACTION_REVERSED", "STACK_ADJUSTED", "HAND_REOPENED", "PAYOUT_CORRECTED",
})

@dataclass(frozen=True, slots=True)
class ActionEntry:

    entry_id: str
    player_id: str | None
    action_type: str
    amount: int
    pot_running_total: int

@dataclass(slots=True)
class StreetSummary:

    street: str
    actions: list[ActionEntry] = field(default_factory=list)
    pot_at_start: int = 0
    pot_at_end: int = 0

@dataclass(frozen=True, slots=True)
class PayoutEntry:

    entry_id: str
    player_id: str
    amount: int

@dataclass(frozen=True, slots=True)
class CorrectionEntry:

    entry_id: str
    correction_type: str
    player_id: str | None
    amount: int | None
    original_entry_id: str | None
    detail: dict | None

@dataclass(slots=True)
class HandTimeline:

    round_id: str = ""
    streets: list[StreetSummary] = field(default_factory=list)
    payouts: list[PayoutEntry] = field(default_factory=list)
    corrections: list[CorrectionEntry] = field(default_factory=list)
    is_completed: bool = False
    is_reopened: bool = False
    total_entries: int = 0

def build_hand_timeline(
    round_id: str,
    entries: list[LedgerRow],
) -> HandTimeline:
    timeline = HandTimeline(round_id=round_id, total_entries=len(entries))

    current_street = StreetSummary(street="PRE_FLOP")
    pot = 0

    for entry in entries:
        etype = entry.entry_type

        if etype in _STREET_TYPES:
            current_street.pot_at_end = pot
            timeline.streets.append(current_street)
            new_street_name = (
                entry.detail.get("street", "UNKNOWN")
                if entry.detail else "UNKNOWN"
            )
            current_street = StreetSummary(street=new_street_name, pot_at_start=pot)
            continue

        if etype in _BLIND_TYPES or etype in _BET_TYPES:
            amt = entry.amount or 0
            pot += amt
            current_street.actions.append(ActionEntry(
                entry_id=entry.entry_id,
                player_id=entry.player_id,
                action_type=etype,
                amount=amt,
                pot_running_total=pot,
            ))
            continue

        if etype in _PAYOUT_TYPES:
            if entry.player_id:
                timeline.payouts.append(PayoutEntry(
                    entry_id=entry.entry_id,
                    player_id=entry.player_id,
                    amount=entry.amount or 0,
                ))
            continue

        if etype in _COMPLETION_TYPES:
            timeline.is_completed = True
            continue

        if etype in _CORRECTION_TYPES:
            if etype == "HAND_REOPENED":
                timeline.is_reopened = True
                timeline.is_completed = False
            if etype == "ACTION_REVERSED":
                pot -= entry.amount or 0
            timeline.corrections.append(CorrectionEntry(
                entry_id=entry.entry_id,
                correction_type=etype,
                player_id=entry.player_id,
                amount=entry.amount,
                original_entry_id=entry.original_entry_id,
                detail=entry.detail,
            ))
            continue

    current_street.pot_at_end = pot
    timeline.streets.append(current_street)

    return timeline