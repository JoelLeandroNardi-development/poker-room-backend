from __future__ import annotations

from dataclasses import dataclass

from .constants import BetAction, RoundStatus
from .exceptions import (
    ActionClosed,
    AmountExceedsStack,
    BetNotAllowed,
    CallNotAllowed,
    CheckNotAllowed,
    IllegalAction,
    InvalidAmount,
    NotYourTurn,
    PlayerAlreadyAllIn,
    PlayerAlreadyFolded,
    PlayerNotInHand,
    RaiseBelowMinimum,
    RaiseNotAllowed,
    RoundNotActive,
)
from .rules import RulesProfile, NO_LIMIT_HOLDEM


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
    action: str
    amount: int


def validate_bet(
    ctx: HandContext,
    player_id: str,
    action: str,
    amount: int,
    rules: RulesProfile = NO_LIMIT_HOLDEM,
) -> ValidatedAction:

    if ctx.status != RoundStatus.ACTIVE:
        raise RoundNotActive("Round is not in ACTIVE status")

    if ctx.is_action_closed:
        raise ActionClosed("Betting action is closed for this street")

    player = ctx.get_player(player_id)
    if player is None:
        raise PlayerNotInHand("Player is not in this hand")

    if not player.is_active_in_hand:
        raise PlayerNotInHand("Player is not in this hand")

    if player.has_folded:
        raise PlayerAlreadyFolded("Player has already folded this round")

    if player.is_all_in:
        raise PlayerAlreadyAllIn("Player is already all-in")

    if ctx.acting_player_id is not None and ctx.acting_player_id != player_id:
        raise NotYourTurn("It is not your turn to act")

    call_amount = max(0, ctx.current_highest_bet - player.committed_this_street)
    stack = player.stack_remaining

    action_upper = action.upper()

    if action_upper == BetAction.FOLD:
        return ValidatedAction(action=BetAction.FOLD, amount=0)

    if action_upper == BetAction.CHECK:
        if call_amount > 0:
            raise CheckNotAllowed("Cannot check when there is a bet to call")
        return ValidatedAction(action=BetAction.CHECK, amount=0)

    if action_upper == BetAction.CALL:
        if call_amount == 0:
            raise CallNotAllowed("Nothing to call — use check instead")
        effective = min(call_amount, stack)
        if effective == stack:
            return ValidatedAction(action=BetAction.ALL_IN, amount=effective)
        return ValidatedAction(action=BetAction.CALL, amount=effective)

    if action_upper == BetAction.BET:
        if ctx.current_highest_bet > 0:
            raise BetNotAllowed("Cannot bet — there is already a bet on this street; use raise")
        if amount <= 0:
            raise InvalidAmount("Bet amount must be greater than 0")
        if amount > stack:
            raise AmountExceedsStack("Bet amount exceeds remaining stack")
        if amount < ctx.minimum_raise_amount and amount != stack:
            raise RaiseBelowMinimum("Bet amount is below the minimum")
        if amount == stack:
            return ValidatedAction(action=BetAction.ALL_IN, amount=amount)
        return ValidatedAction(action=BetAction.BET, amount=amount)

    if action_upper == BetAction.RAISE:
        if ctx.current_highest_bet == 0:
            raise RaiseNotAllowed("Cannot raise — no previous bet to raise; use bet")
        if amount <= 0:
            raise InvalidAmount("Raise amount must be greater than 0")

        total_to_commit = amount
        additional_chips = total_to_commit - player.committed_this_street

        if additional_chips <= 0:
            raise InvalidAmount("Raise amount must be greater than 0")

        if additional_chips > stack:
            raise AmountExceedsStack("Raise amount exceeds remaining stack")

        raise_increment = total_to_commit - ctx.current_highest_bet
        if raise_increment < ctx.minimum_raise_amount and additional_chips != stack:
            raise RaiseBelowMinimum("Raise amount is below the minimum raise")

        if additional_chips == stack:
            return ValidatedAction(action=BetAction.ALL_IN, amount=additional_chips)
        return ValidatedAction(action=BetAction.RAISE, amount=additional_chips)

    if action_upper == BetAction.ALL_IN:
        if stack <= 0:
            raise PlayerAlreadyAllIn("Player is already all-in")
        return ValidatedAction(action=BetAction.ALL_IN, amount=stack)

    raise IllegalAction(f"Invalid bet action: {action}")
