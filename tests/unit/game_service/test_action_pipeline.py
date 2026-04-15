"""Unit tests for the unified apply_action pipeline.

Tests the domain-level state machine that validates a betting action
and mutates Round + RoundPlayer state in a single call.
"""

from __future__ import annotations

import os

import pytest

from tests.service_loader import load_service_app_module

os.environ.setdefault("GAME_DB", "sqlite+aiosqlite:///:memory:")
os.environ.setdefault("RABBIT_URL", "amqp://guest:guest@localhost:5672/")
os.environ.setdefault("EXCHANGE_NAME", "test_exchange")


@pytest.fixture(scope="module")
def pipeline_module():
    return load_service_app_module(
        "game-service",
        "domain/action_pipeline",
        package_name="game_pipeline_test_app",
        reload_modules=True,
    )


@pytest.fixture(scope="module")
def models_module():
    return load_service_app_module(
        "game-service",
        "domain/models",
        package_name="game_pipeline_test_app",
    )


@pytest.fixture(scope="module")
def constants_module():
    return load_service_app_module(
        "game-service",
        "domain/constants",
        package_name="game_pipeline_test_app",
    )


@pytest.fixture(scope="module")
def exceptions_module():
    return load_service_app_module(
        "game-service",
        "domain/exceptions",
        package_name="game_pipeline_test_app",
    )


@pytest.fixture
def Round(models_module):
    return models_module.Round


@pytest.fixture
def RoundPlayer(models_module):
    return models_module.RoundPlayer


@pytest.fixture
def apply_action(pipeline_module):
    return pipeline_module.apply_action


@pytest.fixture
def BetAction(constants_module):
    return constants_module.BetAction


@pytest.fixture
def RoundStatus(constants_module):
    return constants_module.RoundStatus


@pytest.fixture
def Street(constants_module):
    return constants_module.Street


def _make_round(Round, Street, RoundStatus, **overrides):
    defaults = dict(
        round_id="r1",
        game_id="g1",
        round_number=1,
        dealer_seat=1,
        small_blind_seat=2,
        big_blind_seat=3,
        small_blind_amount=50,
        big_blind_amount=100,
        ante_amount=0,
        status=RoundStatus.ACTIVE,
        pot_amount=150,
        street=Street.PRE_FLOP,
        acting_player_id="p4",
        current_highest_bet=100,
        minimum_raise_amount=100,
        is_action_closed=False,
    )
    defaults.update(overrides)
    return Round(**defaults)


def _make_player(RoundPlayer, pid, seat, stack, committed_street=0, committed_hand=0, **overrides):
    defaults = dict(
        round_id="r1",
        player_id=pid,
        seat_number=seat,
        stack_remaining=stack,
        committed_this_street=committed_street,
        committed_this_hand=committed_hand,
        has_folded=False,
        is_all_in=False,
        is_active_in_hand=True,
    )
    defaults.update(overrides)
    return RoundPlayer(**defaults)


# ── Basic action tests ───────────────────────────────────────────────

class TestApplyActionFold:
    def test_fold_marks_player_folded(self, apply_action, Round, RoundPlayer, BetAction, RoundStatus, Street):
        game_round = _make_round(Round, Street, RoundStatus, acting_player_id="p4")
        players = [
            _make_player(RoundPlayer, "p2", 2, 950, 50, 50),   # SB
            _make_player(RoundPlayer, "p3", 3, 900, 100, 100), # BB
            _make_player(RoundPlayer, "p4", 4, 1000, 0, 0),    # UTG (acting)
        ]

        result = apply_action(game_round, players, "p4", "FOLD", 0)

        assert result.action == BetAction.FOLD
        assert result.amount == 0
        p4 = players[2]
        assert p4.has_folded is True
        assert p4.is_active_in_hand is False
        assert p4.stack_remaining == 1000  # unchanged

    def test_fold_does_not_change_pot(self, apply_action, Round, RoundPlayer, BetAction, RoundStatus, Street):
        game_round = _make_round(Round, Street, RoundStatus, pot_amount=200)
        players = [
            _make_player(RoundPlayer, "p1", 1, 900, 100, 100),
            _make_player(RoundPlayer, "p2", 2, 1000, 0, 0),
            _make_player(RoundPlayer, "p3", 3, 1000, 0, 0),
        ]
        game_round.acting_player_id = "p2"

        apply_action(game_round, players, "p2", "FOLD", 0)

        assert game_round.pot_amount == 200


class TestApplyActionCall:
    def test_call_deducts_chips_and_adds_to_pot(self, apply_action, Round, RoundPlayer, BetAction, RoundStatus, Street):
        game_round = _make_round(Round, Street, RoundStatus, acting_player_id="p4", pot_amount=150)
        players = [
            _make_player(RoundPlayer, "p2", 2, 950, 50, 50),
            _make_player(RoundPlayer, "p3", 3, 900, 100, 100),
            _make_player(RoundPlayer, "p4", 4, 1000, 0, 0),
        ]

        result = apply_action(game_round, players, "p4", "CALL", 0)

        assert result.action == BetAction.CALL
        assert result.amount == 100
        p4 = players[2]
        assert p4.stack_remaining == 900
        assert p4.committed_this_street == 100
        assert p4.committed_this_hand == 100
        assert game_round.pot_amount == 250


class TestApplyActionRaise:
    def test_raise_updates_highest_bet_and_min_raise(self, apply_action, Round, RoundPlayer, BetAction, RoundStatus, Street):
        game_round = _make_round(Round, Street, RoundStatus, acting_player_id="p4", pot_amount=150, current_highest_bet=100, minimum_raise_amount=100)
        players = [
            _make_player(RoundPlayer, "p2", 2, 950, 50, 50),
            _make_player(RoundPlayer, "p3", 3, 900, 100, 100),
            _make_player(RoundPlayer, "p4", 4, 1000, 0, 0),
        ]

        result = apply_action(game_round, players, "p4", "RAISE", 200)

        assert result.action == BetAction.RAISE
        assert result.amount == 200  # additional chips
        p4 = players[2]
        assert p4.stack_remaining == 800
        assert p4.committed_this_street == 200
        assert game_round.current_highest_bet == 200
        assert game_round.minimum_raise_amount == 100  # raise increment = 200 - 100 = 100


class TestApplyActionBet:
    def test_opening_bet_on_clean_street(self, apply_action, Round, RoundPlayer, BetAction, RoundStatus, Street):
        game_round = _make_round(
            Round, Street, RoundStatus,
            acting_player_id="p1",
            pot_amount=200,
            current_highest_bet=0,
            minimum_raise_amount=100,
            street=Street.FLOP,
        )
        players = [
            _make_player(RoundPlayer, "p1", 1, 900, 0, 100),
            _make_player(RoundPlayer, "p2", 2, 900, 0, 100),
            _make_player(RoundPlayer, "p3", 3, 900, 0, 100),
        ]

        result = apply_action(game_round, players, "p1", "BET", 200)

        assert result.action == BetAction.BET
        assert result.amount == 200
        assert players[0].stack_remaining == 700
        assert game_round.current_highest_bet == 200
        assert game_round.pot_amount == 400


class TestApplyActionAllIn:
    def test_explicit_all_in(self, apply_action, Round, RoundPlayer, BetAction, RoundStatus, Street):
        game_round = _make_round(
            Round, Street, RoundStatus,
            acting_player_id="p1",
            pot_amount=200,
            current_highest_bet=0,
            minimum_raise_amount=100,
            street=Street.FLOP,
        )
        players = [
            _make_player(RoundPlayer, "p1", 1, 50, 0, 100),
            _make_player(RoundPlayer, "p2", 2, 900, 0, 100),
            _make_player(RoundPlayer, "p3", 3, 900, 0, 100),
        ]

        result = apply_action(game_round, players, "p1", "ALL_IN", 50)

        assert result.action == BetAction.ALL_IN
        assert result.amount == 50
        assert players[0].stack_remaining == 0
        assert players[0].is_all_in is True
        assert game_round.pot_amount == 250


class TestApplyActionCheck:
    def test_check_no_state_change(self, apply_action, Round, RoundPlayer, BetAction, RoundStatus, Street):
        game_round = _make_round(
            Round, Street, RoundStatus,
            acting_player_id="p1",
            pot_amount=200,
            current_highest_bet=0,
            minimum_raise_amount=100,
            street=Street.FLOP,
        )
        players = [
            _make_player(RoundPlayer, "p1", 1, 900, 0, 100),
            _make_player(RoundPlayer, "p2", 2, 900, 0, 100),
        ]

        result = apply_action(game_round, players, "p1", "CHECK", 0)

        assert result.action == BetAction.CHECK
        assert result.amount == 0
        assert players[0].stack_remaining == 900
        assert game_round.pot_amount == 200


# ── Turn progression / round closure tests ───────────────────────────

class TestApplyActionTurnProgression:
    def test_next_player_after_action(self, apply_action, Round, RoundPlayer, BetAction, RoundStatus, Street):
        """After p4 calls, the next player should be p2 (SB who hasn't matched BB yet)."""
        game_round = _make_round(Round, Street, RoundStatus, acting_player_id="p4", pot_amount=150)
        players = [
            _make_player(RoundPlayer, "p2", 2, 950, 50, 50),
            _make_player(RoundPlayer, "p3", 3, 900, 100, 100),
            _make_player(RoundPlayer, "p4", 4, 1000, 0, 0),
        ]

        result = apply_action(game_round, players, "p4", "CALL", 0)

        assert result.next_player_id == "p2"
        assert result.is_round_closed is False
        assert game_round.acting_player_id == "p2"

    def test_round_closes_when_all_matched(self, apply_action, Round, RoundPlayer, BetAction, RoundStatus, Street):
        """When the last player to act matches the bet, the round should close."""
        game_round = _make_round(
            Round, Street, RoundStatus,
            acting_player_id="p2",
            pot_amount=200,
            current_highest_bet=100,
        )
        players = [
            _make_player(RoundPlayer, "p2", 2, 950, 50, 50),
            _make_player(RoundPlayer, "p3", 3, 900, 100, 100),
            _make_player(RoundPlayer, "p4", 4, 900, 100, 100),
        ]

        result = apply_action(game_round, players, "p2", "CALL", 0)

        assert result.is_round_closed is True
        assert game_round.is_action_closed is True
        assert game_round.acting_player_id is None

    def test_everyone_folds_closes_round(self, apply_action, Round, RoundPlayer, BetAction, RoundStatus, Street):
        """When only one player remains, the round should close."""
        game_round = _make_round(
            Round, Street, RoundStatus,
            acting_player_id="p3",
            pot_amount=200,
            current_highest_bet=100,
        )
        players = [
            _make_player(RoundPlayer, "p2", 2, 950, 50, 50, has_folded=True, is_active_in_hand=False),
            _make_player(RoundPlayer, "p3", 3, 1000, 0, 0),
            _make_player(RoundPlayer, "p4", 4, 900, 100, 100),
        ]

        result = apply_action(game_round, players, "p3", "FOLD", 0)

        assert result.is_round_closed is True


# ── Validation errors ────────────────────────────────────────────────

class TestApplyActionValidationErrors:
    def test_not_your_turn(self, apply_action, Round, RoundPlayer, BetAction, RoundStatus, Street, exceptions_module):
        NotYourTurn = exceptions_module.NotYourTurn
        game_round = _make_round(Round, Street, RoundStatus, acting_player_id="p4")
        players = [
            _make_player(RoundPlayer, "p2", 2, 950, 50, 50),
            _make_player(RoundPlayer, "p3", 3, 900, 100, 100),
            _make_player(RoundPlayer, "p4", 4, 1000, 0, 0),
        ]

        with pytest.raises(NotYourTurn):
            apply_action(game_round, players, "p2", "CALL", 0)

    def test_round_not_active(self, apply_action, Round, RoundPlayer, BetAction, RoundStatus, Street, exceptions_module):
        RoundNotActive = exceptions_module.RoundNotActive
        game_round = _make_round(Round, Street, RoundStatus, status=RoundStatus.COMPLETED)
        players = [_make_player(RoundPlayer, "p1", 1, 1000, 0, 0)]

        with pytest.raises(RoundNotActive):
            apply_action(game_round, players, "p1", "CHECK", 0)

    def test_action_closed(self, apply_action, Round, RoundPlayer, BetAction, RoundStatus, Street, exceptions_module):
        ActionClosed = exceptions_module.ActionClosed
        game_round = _make_round(Round, Street, RoundStatus, is_action_closed=True)
        players = [_make_player(RoundPlayer, "p1", 1, 1000, 0, 0)]

        with pytest.raises(ActionClosed):
            apply_action(game_round, players, "p1", "CHECK", 0)
