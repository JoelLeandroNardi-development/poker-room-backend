"""Unified apply-action pipeline for Texas Hold'em.

Encapsulates the full per-action state machine:

1. Validate the action via :func:`~.validator.validate_bet`.
2. Mutate the acting player's state (stack, commitments, flags).
3. Update the round state (pot, highest bet, minimum raise).
4. Determine the next player to act (or close the betting round).

This module is the **single point of mutation** for betting state within
a hand.  It operates directly on ORM model instances so that the caller
can commit once and all changes are persisted atomically.
"""

from __future__ import annotations

from dataclasses import dataclass

from .constants import BetAction
from .models import Round, RoundPlayer
from .turn_engine import ActionSeat, next_to_act
from .validator import HandContext, PlayerState, ValidatedAction, validate_bet


@dataclass(frozen=True, slots=True)
class ApplyActionResult:
    """Outcome of a single player action."""
    action: str
    amount: int
    is_round_closed: bool
    next_player_id: str | None


def _build_hand_context(game_round: Round, round_players: list[RoundPlayer]) -> HandContext:
    players = [
        PlayerState(
            player_id=rp.player_id,
            seat_number=rp.seat_number,
            stack_remaining=rp.stack_remaining,
            committed_this_street=rp.committed_this_street,
            committed_this_hand=rp.committed_this_hand,
            has_folded=rp.has_folded,
            is_all_in=rp.is_all_in,
            is_active_in_hand=rp.is_active_in_hand,
        )
        for rp in round_players
    ]
    return HandContext(
        round_id=game_round.round_id,
        status=game_round.status,
        street=game_round.street,
        acting_player_id=game_round.acting_player_id,
        current_highest_bet=game_round.current_highest_bet,
        minimum_raise_amount=game_round.minimum_raise_amount,
        is_action_closed=game_round.is_action_closed,
        players=players,
    )


def apply_action(
    game_round: Round,
    round_players: list[RoundPlayer],
    player_id: str,
    action: str,
    amount: int,
) -> ApplyActionResult:
    """Validate *and* mutate round + player state for a single action.

    The caller is responsible for wrapping this in a DB transaction and
    persisting the mutated ORM objects.

    Parameters
    ----------
    game_round : Round
        The active round (will be mutated).
    round_players : list[RoundPlayer]
        All players in the round (the acting player will be mutated).
    player_id : str
        The player attempting to act.
    action : str
        Raw action string (FOLD, CHECK, CALL, BET, RAISE, ALL_IN).
    amount : int
        Chip amount accompanying the action.

    Returns
    -------
    ApplyActionResult
        Contains the canonical action, effective chip amount, whether
        the betting round is now closed, and who acts next (if any).
    """

    # ── 1. Validate ──────────────────────────────────────────────────
    ctx = _build_hand_context(game_round, round_players)
    result: ValidatedAction = validate_bet(ctx, player_id, action, amount)

    # ── 2. Locate the acting player's ORM row ────────────────────────
    player_row: RoundPlayer | None = None
    for rp in round_players:
        if rp.player_id == player_id:
            player_row = rp
            break
    assert player_row is not None  # validate_bet already checked

    # ── 3. Mutate player state ───────────────────────────────────────
    effective_action = result.action
    effective_amount = result.amount

    if effective_action == BetAction.FOLD:
        player_row.has_folded = True
        player_row.is_active_in_hand = False

    elif effective_action in (BetAction.CALL, BetAction.BET, BetAction.RAISE, BetAction.ALL_IN):
        player_row.stack_remaining -= effective_amount
        player_row.committed_this_street += effective_amount
        player_row.committed_this_hand += effective_amount

        if effective_action == BetAction.ALL_IN:
            player_row.is_all_in = True

    # CHECK: no mutations needed

    # ── 4. Mutate round state ────────────────────────────────────────
    if effective_action in (BetAction.BET, BetAction.RAISE, BetAction.ALL_IN):
        new_total_committed = player_row.committed_this_street
        if new_total_committed > game_round.current_highest_bet:
            raise_increment = new_total_committed - game_round.current_highest_bet
            game_round.current_highest_bet = new_total_committed
            if raise_increment > game_round.minimum_raise_amount:
                game_round.minimum_raise_amount = raise_increment
    elif effective_action == BetAction.CALL:
        pass  # No change to highest bet or min raise

    game_round.pot_amount += effective_amount

    # ── 5. Determine next actor ──────────────────────────────────────
    action_seats = [
        ActionSeat(
            player_id=rp.player_id,
            seat_number=rp.seat_number,
            has_folded=rp.has_folded,
            is_all_in=rp.is_all_in,
            is_active_in_hand=rp.is_active_in_hand,
            committed_this_street=rp.committed_this_street,
        )
        for rp in round_players
    ]

    # The aggressor is the player who last bet/raised (or all-in as a raise).
    if effective_action in (BetAction.BET, BetAction.RAISE, BetAction.ALL_IN):
        last_aggressor_seat = player_row.seat_number
    else:
        # Keep existing aggressor — use acting_player as fallback
        last_aggressor_seat = game_round.acting_player_id
        # We need a seat number, not player_id. Look it up.
        for rp in round_players:
            if rp.player_id == game_round.acting_player_id:
                last_aggressor_seat = rp.seat_number
                break

    nta = next_to_act(
        players=action_seats,
        current_actor_seat=player_row.seat_number,
        last_aggressor_seat=last_aggressor_seat,
        current_highest_bet=game_round.current_highest_bet,
    )

    if nta.is_round_closed:
        game_round.acting_player_id = None
        game_round.is_action_closed = True
    else:
        game_round.acting_player_id = nta.player_id
        game_round.is_action_closed = False

    return ApplyActionResult(
        action=effective_action,
        amount=effective_amount,
        is_round_closed=nta.is_round_closed,
        next_player_id=nta.player_id,
    )
