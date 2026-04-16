
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable

from .engine.blind_posting import SeatPlayer, post_blinds_and_antes

@dataclass(frozen=True, slots=True)
class PlayerSetup:

    player_id: str
    seat: int
    stack: int

@dataclass(frozen=True, slots=True)
class BlindSetup:

    small: int
    big: int
    ante: int = 0

@dataclass(frozen=True, slots=True)
class ScriptedAction:

    player_id: str
    action: str
    amount: int

@dataclass(frozen=True, slots=True)
class Expectation:

    check_type: str
    args: dict[str, Any] = field(default_factory=dict)

@dataclass(frozen=True, slots=True)
class ExpectationResult:

    passed: bool
    expectation: Expectation
    message: str = ""

@dataclass
class HandScenario:
    name: str
    players: list[PlayerSetup]
    blinds: BlindSetup
    dealer_seat: int
    actions: list[ScriptedAction] = field(default_factory=list)
    expectations: list[Expectation] = field(default_factory=list)

    def add_action(self, player_id: str, action: str, amount: int = 0) -> None:
        self.actions.append(ScriptedAction(player_id, action, amount))

    def expect_pot(self, amount: int) -> None:
        self.expectations.append(Expectation("pot", {"amount": amount}))

    def expect_action_closed(self) -> None:
        self.expectations.append(Expectation("action_closed", {}))

    def expect_player_stack(self, player_id: str, stack: int) -> None:
        self.expectations.append(
            Expectation("player_stack", {"player_id": player_id, "stack": stack})
        )

    def expect_player_folded(self, player_id: str) -> None:
        self.expectations.append(
            Expectation("player_folded", {"player_id": player_id})
        )

    def expect_error(self, error_type: str) -> None:
        self.expectations.append(
            Expectation("error", {"error_type": error_type})
        )

@dataclass
class ScenarioResult:

    scenario_name: str = ""
    passed: bool = True
    actions_applied: int = 0
    expectation_results: list[ExpectationResult] = field(default_factory=list)
    error: str | None = None

    @property
    def failures(self) -> list[ExpectationResult]:
        return [r for r in self.expectation_results if not r.passed]

def run_scenario(
    scenario: HandScenario,
    apply_action_fn: Callable,
    Round: type,
    RoundPlayer: type,
) -> ScenarioResult:
    result = ScenarioResult(scenario_name=scenario.name)

    game_round = Round(
        round_id="scenario-round",
        game_id="scenario-game",
        round_number=1,
        dealer_seat=scenario.dealer_seat,
        small_blind_seat=_seat_left_of(scenario.dealer_seat, scenario.players),
        big_blind_seat=_seat_left_of(
            _seat_left_of(scenario.dealer_seat, scenario.players),
            scenario.players,
        ),
        small_blind_amount=scenario.blinds.small,
        big_blind_amount=scenario.blinds.big,
        ante_amount=scenario.blinds.ante,
        status="ACTIVE",
        street="PRE_FLOP",
        pot_amount=0,
        current_highest_bet=0,
        minimum_raise_amount=scenario.blinds.big,
        is_action_closed=False,
        last_aggressor_seat=None,
    )

    round_players = []
    for ps in scenario.players:
        rp = RoundPlayer(
            round_id="scenario-round",
            player_id=ps.player_id,
            seat_number=ps.seat,
            stack_remaining=ps.stack,
            committed_this_street=0,
            committed_this_hand=0,
            has_folded=False,
            is_all_in=False,
            is_active_in_hand=True,
        )
        round_players.append(rp)

    _post_blinds(game_round, round_players, scenario)

    last_error = None
    for sa in scenario.actions:
        try:
            apply_action_fn(
                game_round, round_players, sa.player_id, sa.action, sa.amount,
            )
            result.actions_applied += 1
            last_error = None
        except Exception as exc:
            last_error = exc
            result.actions_applied += 1

    for exp in scenario.expectations:
        er = _evaluate(exp, game_round, round_players, last_error)
        result.expectation_results.append(er)
        if not er.passed:
            result.passed = False

    return result

def _seat_left_of(seat: int, players: list[PlayerSetup]) -> int:
    seats = sorted(p.seat for p in players)
    idx = seats.index(seat) if seat in seats else 0
    return seats[(idx + 1) % len(seats)]

def _post_blinds(
    game_round,
    round_players: list,
    scenario: HandScenario,
) -> None:
    seat_players = [
        SeatPlayer(
            player_id=rp.player_id,
            seat_number=rp.seat_number,
            stack=rp.stack_remaining,
        )
        for rp in round_players
    ]

    posting = post_blinds_and_antes(
        players=seat_players,
        small_blind_seat=game_round.small_blind_seat,
        big_blind_seat=game_round.big_blind_seat,
        small_blind_amount=scenario.blinds.small,
        big_blind_amount=scenario.blinds.big,
        ante_amount=scenario.blinds.ante,
    )

    for pp in posting.players:
        for rp in round_players:
            if rp.player_id == pp.player_id:
                rp.stack_remaining = pp.stack_remaining
                rp.committed_this_street = pp.committed_this_street
                rp.committed_this_hand = pp.committed_this_hand
                rp.is_all_in = pp.is_all_in
                break

    game_round.pot_amount = posting.pot_total
    game_round.current_highest_bet = posting.current_highest_bet
    game_round.minimum_raise_amount = scenario.blinds.big

    bb_seat = game_round.big_blind_seat
    first_seat = _seat_left_of(bb_seat, scenario.players)
    for rp in round_players:
        if rp.seat_number == first_seat:
            game_round.acting_player_id = rp.player_id
            break

def _evaluate(
    exp: Expectation,
    game_round,
    round_players: list,
    last_error: Exception | None,
) -> ExpectationResult:
    if exp.check_type == "pot":
        expected = exp.args["amount"]
        actual = game_round.pot_amount
        ok = actual == expected
        return ExpectationResult(
            passed=ok,
            expectation=exp,
            message="" if ok else f"Expected pot={expected}, got {actual}",
        )

    if exp.check_type == "action_closed":
        ok = game_round.is_action_closed
        return ExpectationResult(
            passed=ok,
            expectation=exp,
            message="" if ok else "Expected action_closed=True",
        )

    if exp.check_type == "player_stack":
        pid = exp.args["player_id"]
        expected = exp.args["stack"]
        rp = next((r for r in round_players if r.player_id == pid), None)
        if rp is None:
            return ExpectationResult(
                passed=False, expectation=exp,
                message=f"Player {pid} not found",
            )
        ok = rp.stack_remaining == expected
        return ExpectationResult(
            passed=ok,
            expectation=exp,
            message="" if ok else f"Expected {pid} stack={expected}, got {rp.stack_remaining}",
        )

    if exp.check_type == "player_folded":
        pid = exp.args["player_id"]
        rp = next((r for r in round_players if r.player_id == pid), None)
        if rp is None:
            return ExpectationResult(
                passed=False, expectation=exp,
                message=f"Player {pid} not found",
            )
        ok = rp.has_folded
        return ExpectationResult(
            passed=ok,
            expectation=exp,
            message="" if ok else f"Expected {pid} to be folded",
        )

    if exp.check_type == "error":
        expected_type = exp.args["error_type"]
        if last_error is None:
            return ExpectationResult(
                passed=False, expectation=exp,
                message=f"Expected error {expected_type} but no error occurred",
            )
        actual_type = type(last_error).__name__
        ok = actual_type == expected_type
        return ExpectationResult(
            passed=ok,
            expectation=exp,
            message="" if ok else f"Expected {expected_type}, got {actual_type}",
        )

    return ExpectationResult(
        passed=False, expectation=exp,
        message=f"Unknown expectation type: {exp.check_type}",
    )