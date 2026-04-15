from __future__ import annotations

from dataclasses import dataclass
from fastapi import HTTPException

from .constants import BetAction, ErrorMessage


@dataclass(frozen=True, slots=True)
class PlayerState:
    player_id: str
    seat_number: int
    stack_remaining: int
    committed_this_street: int
    committed_this_hand: int
    has_folded: bool
    is_all_in: bool
    is_active_in_hand: bool


@dataclass(frozen=True, slots=True)
class HandContext:
    round_id: str
    status: str
    street: str
    acting_player_id: str | None
    current_highest_bet: int
    minimum_raise_amount: int
    is_action_closed: bool
    players: list[PlayerState]

    def get_player(self, player_id: str) -> PlayerState | None:
        for p in self.players:
            if p.player_id == player_id:
                return p
        return None


@dataclass(frozen=True, slots=True)
class ValidatedAction:
    """The result of validation — the canonical action and chip amount to record."""
    action: str
    amount: int


def _fail(detail: str, status_code: int = 400) -> None:
    raise HTTPException(status_code=status_code, detail=detail)


def validate_bet(ctx: HandContext, player_id: str, action: str, amount: int) -> ValidatedAction:
    """
    Validate a betting action against the current hand state.

    Returns a ValidatedAction with the canonical action name and chip amount,
    or raises an HTTPException if the action is illegal.
    """

    # --- Round-level guards ---
    if ctx.status != "ACTIVE":
        _fail(ErrorMessage.ROUND_NOT_ACTIVE)

    if ctx.is_action_closed:
        _fail(ErrorMessage.ACTION_CLOSED)

    # --- Player-level guards ---
    player = ctx.get_player(player_id)
    if player is None:
        _fail(ErrorMessage.PLAYER_NOT_IN_HAND, status_code=404)

    if not player.is_active_in_hand:
        _fail(ErrorMessage.PLAYER_NOT_IN_HAND)

    if player.has_folded:
        _fail(ErrorMessage.PLAYER_ALREADY_FOLDED)

    if player.is_all_in:
        _fail(ErrorMessage.PLAYER_ALL_IN)

    # --- Turn order ---
    if ctx.acting_player_id is not None and ctx.acting_player_id != player_id:
        _fail(ErrorMessage.NOT_YOUR_TURN)

    # --- Derived values ---
    call_amount = max(0, ctx.current_highest_bet - player.committed_this_street)
    stack = player.stack_remaining

    action_upper = action.upper()

    # ======== FOLD ========
    if action_upper == BetAction.FOLD:
        return ValidatedAction(action=BetAction.FOLD, amount=0)

    # ======== CHECK ========
    if action_upper == BetAction.CHECK:
        if call_amount > 0:
            _fail(ErrorMessage.CHECK_NOT_ALLOWED)
        return ValidatedAction(action=BetAction.CHECK, amount=0)

    # ======== CALL ========
    if action_upper == BetAction.CALL:
        if call_amount == 0:
            _fail(ErrorMessage.CALL_NOT_ALLOWED)
        effective = min(call_amount, stack)
        if effective == stack:
            # Calling puts player all-in
            return ValidatedAction(action=BetAction.ALL_IN, amount=effective)
        return ValidatedAction(action=BetAction.CALL, amount=effective)

    # ======== BET (opening bet — no previous bet on street) ========
    if action_upper == BetAction.BET:
        if ctx.current_highest_bet > 0:
            _fail(ErrorMessage.BET_NOT_ALLOWED)
        if amount <= 0:
            _fail(ErrorMessage.RAISE_AMOUNT_TOO_LOW)
        if amount > stack:
            _fail(ErrorMessage.AMOUNT_EXCEEDS_STACK)
        if amount < ctx.minimum_raise_amount and amount != stack:
            # Must meet minimum unless going all-in
            _fail(ErrorMessage.RAISE_BELOW_MINIMUM)
        if amount == stack:
            return ValidatedAction(action=BetAction.ALL_IN, amount=amount)
        return ValidatedAction(action=BetAction.BET, amount=amount)

    # ======== RAISE ========
    if action_upper == BetAction.RAISE:
        if ctx.current_highest_bet == 0:
            _fail(ErrorMessage.RAISE_NOT_ALLOWED)
        if amount <= 0:
            _fail(ErrorMessage.RAISE_AMOUNT_TOO_LOW)

        # "amount" is the total chips the player wants to have committed this street.
        # The raise *increment* over the current highest bet must meet the minimum.
        total_to_commit = amount
        additional_chips = total_to_commit - player.committed_this_street

        if additional_chips <= 0:
            _fail(ErrorMessage.RAISE_AMOUNT_TOO_LOW)

        if additional_chips > stack:
            _fail(ErrorMessage.AMOUNT_EXCEEDS_STACK)

        raise_increment = total_to_commit - ctx.current_highest_bet
        if raise_increment < ctx.minimum_raise_amount and additional_chips != stack:
            # Under-raise only allowed if it is an all-in
            _fail(ErrorMessage.RAISE_BELOW_MINIMUM)

        if additional_chips == stack:
            return ValidatedAction(action=BetAction.ALL_IN, amount=additional_chips)
        return ValidatedAction(action=BetAction.RAISE, amount=additional_chips)

    # ======== ALL_IN (explicit) ========
    if action_upper == BetAction.ALL_IN:
        if stack <= 0:
            _fail(ErrorMessage.PLAYER_ALL_IN)
        return ValidatedAction(action=BetAction.ALL_IN, amount=stack)

    _fail(ErrorMessage.INVALID_ACTION, status_code=422)
