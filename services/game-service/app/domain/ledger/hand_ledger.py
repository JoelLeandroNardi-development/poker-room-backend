
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

@dataclass(frozen=True)
class LedgerRow:
    entry_id: str
    entry_type: str
    player_id: str | None
    amount: int | None
    detail: dict[str, Any] | None
    original_entry_id: str | None

@dataclass
class PlayerSnapshot:
    player_id: str
    stack_adjustment: int = 0
    total_committed: int = 0
    total_won: int = 0
    is_action_reversed: bool = False

@dataclass
class HandState:
    players: dict[str, PlayerSnapshot] = field(default_factory=dict)
    pot_total: int = 0
    is_completed: bool = False
    is_reopened: bool = False
    reversed_entry_ids: set[str] = field(default_factory=set)
    payout_corrections: list[dict[str, Any]] = field(default_factory=list)
    entry_count: int = 0

    def net_pot(self) -> int:
        return self.pot_total

_BLIND_POSTED = "BLIND_POSTED"
_ANTE_POSTED = "ANTE_POSTED"
_BET_PLACED = "BET_PLACED"
_PAYOUT_AWARDED = "PAYOUT_AWARDED"
_ROUND_COMPLETED = "ROUND_COMPLETED"
_ACTION_REVERSED = "ACTION_REVERSED"
_STACK_ADJUSTED = "STACK_ADJUSTED"
_HAND_REOPENED = "HAND_REOPENED"
_PAYOUT_CORRECTED = "PAYOUT_CORRECTED"

def _ensure_player(state: HandState, player_id: str) -> PlayerSnapshot:
    if player_id not in state.players:
        state.players[player_id] = PlayerSnapshot(player_id=player_id)
    return state.players[player_id]

def apply_entry(state: HandState, e: LedgerRow) -> None:
    state.entry_count += 1

    if e.entry_type in (_BLIND_POSTED, _ANTE_POSTED, _BET_PLACED):
        amt = e.amount or 0
        if e.player_id:
            ps = _ensure_player(state, e.player_id)
            ps.total_committed += amt
            ps.is_action_reversed = False
        state.pot_total += amt

    elif e.entry_type == _PAYOUT_AWARDED:
        amt = e.amount or 0
        if e.player_id:
            ps = _ensure_player(state, e.player_id)
            ps.total_won += amt

    elif e.entry_type == _ROUND_COMPLETED:
        state.is_completed = True

    elif e.entry_type == _ACTION_REVERSED:
        orig_id = e.original_entry_id
        if orig_id:
            state.reversed_entry_ids.add(orig_id)
        amt = e.amount or 0
        if e.player_id:
            ps = _ensure_player(state, e.player_id)
            ps.total_committed -= amt
            ps.is_action_reversed = True
        state.pot_total -= amt

    elif e.entry_type == _STACK_ADJUSTED:
        amt = e.amount or 0
        if e.player_id:
            ps = _ensure_player(state, e.player_id)
            ps.stack_adjustment += amt

    elif e.entry_type == _HAND_REOPENED:
        state.is_completed = False
        state.is_reopened = True

    elif e.entry_type == _PAYOUT_CORRECTED:
        detail = e.detail or {}
        old_player = detail.get("old_player_id")
        new_player = e.player_id
        old_amount = detail.get("old_amount", 0)
        new_amount = e.amount or 0

        if old_player:
            ps_old = _ensure_player(state, old_player)
            ps_old.total_won -= old_amount

        if new_player:
            ps_new = _ensure_player(state, new_player)
            ps_new.total_won += new_amount

        state.payout_corrections.append({
            "entry_id": e.entry_id,
            "old_player_id": old_player,
            "old_amount": old_amount,
            "new_player_id": new_player,
            "new_amount": new_amount,
        })

def rebuild_hand_state(entries: list[LedgerRow]) -> HandState:
    state = HandState()
    for e in entries:
        apply_entry(state, e)
    return state