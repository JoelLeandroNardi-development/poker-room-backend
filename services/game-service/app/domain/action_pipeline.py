"""Unified apply-action pipeline for Texas Hold'em.

Architecture:

1. ``transition_hand_state()`` — **pure domain function**.  Accepts
   immutable dataclass snapshots, validates, and returns a structured
   ``HandTransition`` describing all mutations without performing them.

2. ``apply_action()`` — **thin ORM adapter**.  Reads ORM rows into the
   pure input, calls ``transition_hand_state()``, and writes the diff
   back onto the mutable ORM objects.

Callers interact with ``apply_action()`` at the application boundary.
The pure core is independently testable without any DB or ORM involvement.
"""

from __future__ import annotations

from dataclasses import dataclass

from .constants import BetAction
from .models import Round, RoundPlayer
from .turn_engine import ActionSeat, next_to_act
from .validator import HandContext, PlayerState, ValidatedAction, validate_bet


# ── Pure output types ────────────────────────────────────────────────

@dataclass(frozen=True, slots=True)
class PlayerMutation:
    """Describes changes to apply to one player after an action."""
    player_id: str
    stack_delta: int          # negative = chips removed from stack
    street_commit_delta: int
    hand_commit_delta: int
    should_fold: bool
    should_all_in: bool


@dataclass(frozen=True, slots=True)
class RoundMutation:
    """Describes changes to apply to the round after an action."""
    pot_delta: int
    new_highest_bet: int | None     # None = unchanged
    new_min_raise: int | None       # None = unchanged
    new_acting_player_id: str | None
    new_last_aggressor_seat: int | None  # None = unchanged
    is_action_closed: bool


@dataclass(frozen=True, slots=True)
class HandTransition:
    """Complete, pure result of a single player action.

    Contains the validated action outcome and all planned mutations,
    but performs no side effects.
    """
    action: str
    amount: int
    is_round_closed: bool
    next_player_id: str | None
    player_mutation: PlayerMutation
    round_mutation: RoundMutation


# ── Legacy result alias (public API) ────────────────────────────────

@dataclass(frozen=True, slots=True)
class ApplyActionResult:
    """Outcome of a single player action (kept for backward compat)."""
    action: str
    amount: int
    is_round_closed: bool
    next_player_id: str | None


# ── Pure state-transition core ───────────────────────────────────────

def transition_hand_state(
    ctx: HandContext,
    player_id: str,
    action: str,
    amount: int,
    last_aggressor_seat: int | None,
) -> HandTransition:
    """Validate an action and compute the full mutation plan.

    This function is **pure** — it reads only from its arguments and
    returns a deterministic ``HandTransition`` without mutating anything.

    Parameters
    ----------
    ctx : HandContext
        Immutable snapshot of the current hand state.
    player_id : str
        The player attempting to act.
    action : str
        Raw action string (FOLD, CHECK, CALL, BET, RAISE, ALL_IN).
    amount : int
        Chip amount accompanying the action.
    last_aggressor_seat : int | None
        The seat of the most recent bet/raise on this street, or
        ``None`` if there is no aggressor yet.

    Returns
    -------
    HandTransition
        Contains the validated action, chip movement, and next-actor
        determination.
    """
    # ── 1. Validate ──────────────────────────────────────────────────
    result: ValidatedAction = validate_bet(ctx, player_id, action, amount)
    effective_action = result.action
    effective_amount = result.amount

    # ── 2. Locate the acting player's snapshot ───────────────────────
    player = ctx.get_player(player_id)
    assert player is not None  # validate_bet already checked

    # ── 3. Compute player mutation ───────────────────────────────────
    should_fold = effective_action == BetAction.FOLD
    should_all_in = effective_action == BetAction.ALL_IN
    if effective_action in (BetAction.CALL, BetAction.BET, BetAction.RAISE, BetAction.ALL_IN):
        stack_delta = -effective_amount
        commit_delta = effective_amount
    else:
        stack_delta = 0
        commit_delta = 0

    player_mutation = PlayerMutation(
        player_id=player_id,
        stack_delta=stack_delta,
        street_commit_delta=commit_delta,
        hand_commit_delta=commit_delta,
        should_fold=should_fold,
        should_all_in=should_all_in,
    )

    # ── 4. Compute round mutation ────────────────────────────────────
    new_highest_bet: int | None = None
    new_min_raise: int | None = None
    new_aggressor_seat: int | None = None

    # Apply player-level delta to compute post-action committed total
    post_committed = player.committed_this_street + commit_delta

    if effective_action in (BetAction.BET, BetAction.RAISE, BetAction.ALL_IN):
        if post_committed > ctx.current_highest_bet:
            raise_increment = post_committed - ctx.current_highest_bet
            new_highest_bet = post_committed
            if raise_increment > ctx.minimum_raise_amount:
                new_min_raise = raise_increment
        new_aggressor_seat = player.seat_number

    # ── 5. Determine next actor ──────────────────────────────────────
    # Build post-mutation player snapshots for the turn engine
    action_seats: list[ActionSeat] = []
    for p in ctx.players:
        folded = p.has_folded
        all_in = p.is_all_in
        active = p.is_active_in_hand
        committed = p.committed_this_street

        if p.player_id == player_id:
            if should_fold:
                folded = True
                active = False
            committed += commit_delta
            if should_all_in:
                all_in = True

        action_seats.append(ActionSeat(
            player_id=p.player_id,
            seat_number=p.seat_number,
            has_folded=folded,
            is_all_in=all_in,
            is_active_in_hand=active,
            committed_this_street=committed,
        ))

    resolved_aggressor = new_aggressor_seat if new_aggressor_seat is not None else last_aggressor_seat

    nta = next_to_act(
        players=action_seats,
        current_actor_seat=player.seat_number,
        last_aggressor_seat=resolved_aggressor,
        current_highest_bet=new_highest_bet if new_highest_bet is not None else ctx.current_highest_bet,
    )

    round_mutation = RoundMutation(
        pot_delta=effective_amount,
        new_highest_bet=new_highest_bet,
        new_min_raise=new_min_raise,
        new_acting_player_id=nta.player_id if not nta.is_round_closed else None,
        new_last_aggressor_seat=new_aggressor_seat,
        is_action_closed=nta.is_round_closed,
    )

    return HandTransition(
        action=effective_action,
        amount=effective_amount,
        is_round_closed=nta.is_round_closed,
        next_player_id=nta.player_id,
        player_mutation=player_mutation,
        round_mutation=round_mutation,
    )


# ── ORM adapter ──────────────────────────────────────────────────────

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


def _apply_transition(
    game_round: Round,
    round_players: list[RoundPlayer],
    transition: HandTransition,
) -> None:
    """Write a ``HandTransition`` onto mutable ORM objects."""
    pm = transition.player_mutation
    rm = transition.round_mutation

    # Player mutations
    for rp in round_players:
        if rp.player_id == pm.player_id:
            rp.stack_remaining += pm.stack_delta
            rp.committed_this_street += pm.street_commit_delta
            rp.committed_this_hand += pm.hand_commit_delta
            if pm.should_fold:
                rp.has_folded = True
                rp.is_active_in_hand = False
            if pm.should_all_in:
                rp.is_all_in = True
            break

    # Round mutations
    game_round.pot_amount += rm.pot_delta
    if rm.new_highest_bet is not None:
        game_round.current_highest_bet = rm.new_highest_bet
    if rm.new_min_raise is not None:
        game_round.minimum_raise_amount = rm.new_min_raise
    if rm.new_last_aggressor_seat is not None:
        game_round.last_aggressor_seat = rm.new_last_aggressor_seat

    if rm.is_action_closed:
        game_round.acting_player_id = None
        game_round.is_action_closed = True
    else:
        game_round.acting_player_id = rm.new_acting_player_id
        game_round.is_action_closed = False


def apply_action(
    game_round: Round,
    round_players: list[RoundPlayer],
    player_id: str,
    action: str,
    amount: int,
) -> ApplyActionResult:
    """Validate *and* mutate round + player state for a single action.

    This is the application-layer entry point.  It delegates to the
    pure ``transition_hand_state()`` for all decision logic and then
    writes the resulting diff onto the ORM objects.

    The caller is responsible for wrapping this in a DB transaction and
    persisting the mutated ORM objects.
    """
    ctx = _build_hand_context(game_round, round_players)

    transition = transition_hand_state(
        ctx, player_id, action, amount,
        last_aggressor_seat=game_round.last_aggressor_seat,
    )

    _apply_transition(game_round, round_players, transition)

    return ApplyActionResult(
        action=transition.action,
        amount=transition.amount,
        is_round_closed=transition.is_round_closed,
        next_player_id=transition.next_player_id,
    )
