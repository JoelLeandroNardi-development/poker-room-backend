"""Deterministic hand replay engine.

Replays a hand step-by-step from immutable ledger entries, producing a
``ReplayResult`` that contains the hand state at every point in its
lifecycle.  By design this is a **pure** function — no IO, no ORM, no
side effects.

Use cases
---------
1. **Determinism proof** — replay a hand's ledger and compare the final
   ``HandState`` against the live projection; any mismatch is a bug.
2. **Hand history** — reconstruct every intermediate state for display
   or audit purposes.
3. **Debugging** — step through a hand to understand how state evolved.

The ``replay_hand()`` function delegates the aggregate accounting to
``hand_ledger.rebuild_hand_state`` after *each* entry, so the replay is
always consistent with the authoritative ledger engine.
"""

from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass, field

from .hand_ledger import HandState, LedgerRow, rebuild_hand_state


# ── Output types ─────────────────────────────────────────────────────

@dataclass(frozen=True, slots=True)
class HandStep:
    """Snapshot of the hand after a single ledger entry was applied."""

    step_number: int
    entry_id: str
    entry_type: str
    player_id: str | None
    amount: int | None
    state_after: HandState


@dataclass(slots=True)
class ReplayResult:
    """Complete step-by-step replay of a hand."""

    steps: list[HandStep] = field(default_factory=list)
    final_state: HandState = field(default_factory=HandState)
    entry_count: int = 0
    is_consistent: bool = True


# ── Public API ───────────────────────────────────────────────────────

def replay_hand(entries: list[LedgerRow]) -> ReplayResult:
    """Replay a hand from its ledger entries, producing every intermediate state.

    Parameters
    ----------
    entries:
        Chronologically sorted ledger entries for a single hand.

    Returns
    -------
    ReplayResult
        Contains one ``HandStep`` per entry plus the final ``HandState``.
    """
    result = ReplayResult(entry_count=len(entries))

    for i, entry in enumerate(entries, start=1):
        # Rebuild from the first *i* entries — guaranteed consistent
        # because we use the same engine every time.
        partial = rebuild_hand_state(entries[:i])
        step = HandStep(
            step_number=i,
            entry_id=entry.entry_id,
            entry_type=entry.entry_type,
            player_id=entry.player_id,
            amount=entry.amount,
            state_after=deepcopy(partial),
        )
        result.steps.append(step)

    if entries:
        result.final_state = rebuild_hand_state(entries)

    return result


def verify_consistency(
    entries: list[LedgerRow],
    live_pot_total: int,
    live_player_committed: dict[str, int],
) -> list[str]:
    """Compare a replayed hand against the live projection.

    Parameters
    ----------
    entries:
        Chronologically sorted ledger entries for the hand.
    live_pot_total:
        The pot amount from the live ``Round`` projection.
    live_player_committed:
        Mapping of ``player_id → committed_this_hand`` from live
        ``RoundPlayer`` rows.

    Returns
    -------
    list[str]
        Empty list if consistent; otherwise a list of human-readable
        discrepancy descriptions.
    """
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
