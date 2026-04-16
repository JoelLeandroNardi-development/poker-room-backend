
from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass, field

from .hand_ledger import HandState, LedgerRow, apply_entry, rebuild_hand_state

@dataclass(frozen=True, slots=True)
class HandStep:

    step_number: int
    entry_id: str
    entry_type: str
    player_id: str | None
    amount: int | None
    state_after: HandState

@dataclass(slots=True)
class ReplayResult:

    steps: list[HandStep] = field(default_factory=list)
    final_state: HandState = field(default_factory=HandState)
    entry_count: int = 0
    is_consistent: bool = True

def replay_hand(entries: list[LedgerRow]) -> ReplayResult:
    result = ReplayResult(entry_count=len(entries))
    state = HandState()

    for i, entry in enumerate(entries, start=1):
        apply_entry(state, entry)
        step = HandStep(
            step_number=i,
            entry_id=entry.entry_id,
            entry_type=entry.entry_type,
            player_id=entry.player_id,
            amount=entry.amount,
            state_after=deepcopy(state),
        )
        result.steps.append(step)

    result.final_state = deepcopy(state) if entries else HandState()
    return result

def verify_consistency(
    entries: list[LedgerRow],
    live_pot_total: int,
    live_player_committed: dict[str, int],
) -> list[str]:
    replayed = rebuild_hand_state(entries)
    discrepancies: list[str] = []

    if replayed.pot_total != live_pot_total:
        discrepancies.append(
            f"Pot mismatch: replayed={replayed.pot_total}, live={live_pot_total}"
        )

    for player_id, committed in live_player_committed.items():
        snap = replayed.players.get(player_id)
        if snap is None:
            discrepancies.append(
                f"Player {player_id} exists in live state but not in replay"
            )
        elif snap.total_committed != committed:
            discrepancies.append(
                f"Player {player_id} committed mismatch: "
                f"replayed={snap.total_committed}, live={committed}"
            )

    for player_id in replayed.players:
        if player_id not in live_player_committed:
            discrepancies.append(
                f"Player {player_id} exists in replay but not in live state"
            )

    return discrepancies