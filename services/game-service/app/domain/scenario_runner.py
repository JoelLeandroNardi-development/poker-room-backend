"""Scenario runner framework for poker hand testing.

Provides a declarative DSL for scripting full hand scenarios — from
blind posting through betting rounds, street transitions, settlement,
and corrections — then replaying them through the pure engine and
verifying expectations.

Usage::

    scenario = HandScenario(
        name="3-player squeeze play",
        players=[
            PlayerSetup(player_id="p1", seat=1, stack=1000),
            PlayerSetup(player_id="p2", seat=2, stack=1000),
            PlayerSetup(player_id="p3", seat=3, stack=1000),
        ],
        blinds=BlindSetup(small=10, big=20),
        dealer_seat=1,
    )
    scenario.add_action("p2", "CALL", 20)
    scenario.add_action("p3", "RAISE", 60)
    scenario.add_action("p1", "FOLD", 0)
    scenario.add_action("p2", "FOLD", 0)
    scenario.expect_pot(50)  # 10 + 20 + 20 = 50 from P2, then P3 raise
    scenario.expect_action_closed()

    result = run_scenario(scenario, transition_hand_state)
    assert result.passed
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable

from .blind_posting import SeatPlayer, post_blinds_and_antes


# ── Setup types ──────────────────────────────────────────────────────

@dataclass(frozen=True, slots=True)
class PlayerSetup:
    """Initial player configuration for a scenario."""

    player_id: str
    seat: int
    stack: int


@dataclass(frozen=True, slots=True)
class BlindSetup:
    """Blind structure for a scenario."""

    small: int
    big: int
    ante: int = 0


# ── Action / expectation types ───────────────────────────────────────

@dataclass(frozen=True, slots=True)
class ScriptedAction:
    """A single player action in the scenario script."""

    player_id: str
    action: str
    amount: int


@dataclass(frozen=True, slots=True)
class Expectation:
    """A condition to verify at a point in the scenario."""

    check_type: str  # "pot", "action_closed", "player_stack", "player_folded", "error"
    args: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class ExpectationResult:
    """Result of evaluating a single expectation."""

    passed: bool
    expectation: Expectation
    message: str = ""


# ── Scenario definition ─────────────────────────────────────────────

@dataclass
class HandScenario:
    """Declarative hand scenario definition."""

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
        """Expect the last action to raise a specific domain error."""
        self.expectations.append(
            Expectation("error", {"error_type": error_type})
        )


# ── Scenario result ──────────────────────────────────────────────────

@dataclass
class ScenarioResult:
    """Aggregated result of running a scenario."""

    scenario_name: str = ""
    passed: bool = True
    actions_applied: int = 0
    expectation_results: list[ExpectationResult] = field(default_factory=list)
    error: str | None = None

    @property
    def failures(self) -> list[ExpectationResult]:
        return [r for r in self.expectation_results if not r.passed]


# ── Runner ───────────────────────────────────────────────────────────

def run_scenario(
    scenario: HandScenario,
    apply_action_fn: Callable,
    Round: type,
    RoundPlayer: type,
) -> ScenarioResult:
    """Execute a scenario through the ORM-level ``apply_action``.

    Parameters
    ----------
    scenario:
        The hand scenario to run.
    apply_action_fn:
        The ``apply_action`` function from ``action_pipeline``.
    Round:
        The ``Round`` ORM model class.
    RoundPlayer:
        The ``RoundPlayer`` ORM model class.

    Returns
    -------
    ScenarioResult
    """
    result = ScenarioResult(scenario_name=scenario.name)

    # ── Build initial state ──────────────────────────────────────
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

    # ── Apply blinds first ───────────────────────────────────────
    _post_blinds(game_round, round_players, scenario)

    # ── Execute scripted actions ─────────────────────────────────
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

    # ── Evaluate expectations ────────────────────────────────────
    for exp in scenario.expectations:
        er = _evaluate(exp, game_round, round_players, last_error)
        result.expectation_results.append(er)
        if not er.passed:
            result.passed = False

    return result


# ── Helpers ──────────────────────────────────────────────────────────

def _seat_left_of(seat: int, players: list[PlayerSetup]) -> int:
    """Find the next occupied seat clockwise."""
    seats = sorted(p.seat for p in players)
    idx = seats.index(seat) if seat in seats else 0
    return seats[(idx + 1) % len(seats)]


def _post_blinds(
    game_round,
    round_players: list,
    scenario: HandScenario,
) -> None:
    """Post blinds using the real ``post_blinds_and_antes()`` engine."""
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

    # Write posting results back onto ORM-like objects
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

    # Set first to act: left of big blind
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
    """Evaluate one expectation against current state."""
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
