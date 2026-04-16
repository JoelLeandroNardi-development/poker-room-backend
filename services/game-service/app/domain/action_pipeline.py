
from __future__ import annotations

from dataclasses import dataclass

from .constants import BetAction
from .exceptions import StaleStateError
from .models import Round, RoundPlayer
from .rules import RulesProfile, NO_LIMIT_HOLDEM
from .turn_engine import ActionSeat, next_to_act
from .validator import HandContext, PlayerState, ValidatedAction, validate_bet


@dataclass(frozen=True, slots=True)
class PlayerMutation:
    player_id: str
    stack_delta: int
    street_commit_delta: int
    hand_commit_delta: int
    should_fold: bool
    should_all_in: bool


@dataclass(frozen=True, slots=True)
class RoundMutation:
    pot_delta: int
    new_highest_bet: int | None
    new_min_raise: int | None
    new_acting_player_id: str | None
    new_last_aggressor_seat: int | None
    is_action_closed: bool


@dataclass(frozen=True, slots=True)
class HandTransition:
    action: str
    amount: int
    is_round_closed: bool
    next_player_id: str | None
    player_mutation: PlayerMutation
    round_mutation: RoundMutation


@dataclass(frozen=True, slots=True)
class ApplyActionResult:
    action: str
    amount: int
    is_round_closed: bool
    next_player_id: str | None


def transition_hand_state(
    ctx: HandContext,
    player_id: str,
    action: str,
    amount: int,
    last_aggressor_seat: int | None,
    rules: RulesProfile = NO_LIMIT_HOLDEM,
) -> HandTransition:
    result: ValidatedAction = validate_bet(ctx, player_id, action, amount, rules=rules)
    effective_action = result.action
    effective_amount = result.amount

    player = ctx.get_player(player_id)
    assert player is not None

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

    new_highest_bet: int | None = None
    new_min_raise: int | None = None
    new_aggressor_seat: int | None = None

    post_committed = player.committed_this_street + commit_delta

    if effective_action in (BetAction.BET, BetAction.RAISE, BetAction.ALL_IN):
        if post_committed > ctx.current_highest_bet:
            raise_increment = post_committed - ctx.current_highest_bet
            new_highest_bet = post_committed
            if raise_increment > ctx.minimum_raise_amount:
                new_min_raise = raise_increment
        new_aggressor_seat = player.seat_number

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
    pm = transition.player_mutation
    rm = transition.round_mutation

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

    game_round.state_version = (game_round.state_version or 1) + 1


def apply_action(
    game_round: Round,
    round_players: list[RoundPlayer],
    player_id: str,
    action: str,
    amount: int,
    rules: RulesProfile = NO_LIMIT_HOLDEM,
    expected_version: int | None = None,
) -> ApplyActionResult:
    if expected_version is not None:
        current = game_round.state_version or 1
        if current != expected_version:
            raise StaleStateError(
                f"Expected state_version={expected_version}, "
                f"current={current}"
            )

    ctx = _build_hand_context(game_round, round_players)

    transition = transition_hand_state(
        ctx, player_id, action, amount,
        last_aggressor_seat=game_round.last_aggressor_seat,
        rules=rules,
    )

    _apply_transition(game_round, round_players, transition)

    return ApplyActionResult(
        action=transition.action,
        amount=transition.amount,
        is_round_closed=transition.is_round_closed,
        next_player_id=transition.next_player_id,
    )
