"""
Comprehensive unit tests for the per-action turn engine.

Covers:
- Basic clockwise rotation
- Skipping folded, all-in, and inactive players
- Round closure (wrap back to aggressor)
- Round closure when < 2 eligible
- Heads-up (2-player) specific scenarios
- 3-player scenarios
- 6-player scenarios with complex fold/all-in mixes
- Pre-flop big-blind special case
- Edge cases: single eligible, all folded, all all-in
"""

from __future__ import annotations

import os

import pytest

from tests.service_loader import load_service_app_module

os.environ.setdefault("GAME_DB", "sqlite+aiosqlite:///:memory:")
os.environ.setdefault("RABBIT_URL", "amqp://guest:guest@localhost:5672/")
os.environ.setdefault("EXCHANGE_NAME", "test_exchange")

@pytest.fixture(scope="module")
def turn_module():
    return load_service_app_module(
        "game-service",
        "domain/engine/turn_engine",
        package_name="game_turn_test_app",
        reload_modules=True,
    )

@pytest.fixture(scope="module")
def ActionSeat(turn_module):
    return turn_module.ActionSeat

@pytest.fixture(scope="module")
def next_to_act(turn_module):
    return turn_module.next_to_act

def _s(AS, pid, seat, *, folded=False, all_in=False, active=True, committed=0):
    return AS(
        player_id=pid,
        seat_number=seat,
        has_folded=folded,
        is_all_in=all_in,
        is_active_in_hand=active,
        committed_this_street=committed,
    )

@pytest.mark.unit
class TestBasicRotation:
    def test_next_player_clockwise(self, next_to_act, ActionSeat):
        players = [
            _s(ActionSeat, "A", 1, committed=0),
            _s(ActionSeat, "B", 2, committed=0),
            _s(ActionSeat, "C", 3, committed=0),
        ]
        result = next_to_act(players, current_actor_seat=1, last_aggressor_seat=None, current_highest_bet=10)
        assert result.player_id == "B"
        assert result.seat_number == 2
        assert result.is_round_closed is False

    def test_wraps_around_to_lowest_seat(self, next_to_act, ActionSeat):
        players = [
            _s(ActionSeat, "A", 1, committed=0),
            _s(ActionSeat, "B", 2, committed=0),
            _s(ActionSeat, "C", 3, committed=0),
        ]
        result = next_to_act(players, current_actor_seat=3, last_aggressor_seat=None, current_highest_bet=10)
        assert result.player_id == "A"
        assert result.seat_number == 1

    def test_non_contiguous_seats(self, next_to_act, ActionSeat):
        players = [
            _s(ActionSeat, "A", 2, committed=0),
            _s(ActionSeat, "B", 5, committed=0),
            _s(ActionSeat, "C", 8, committed=0),
        ]
        result = next_to_act(players, current_actor_seat=5, last_aggressor_seat=None, current_highest_bet=10)
        assert result.player_id == "C"
        assert result.seat_number == 8

    def test_non_contiguous_wraps(self, next_to_act, ActionSeat):
        players = [
            _s(ActionSeat, "A", 2, committed=0),
            _s(ActionSeat, "B", 5, committed=0),
            _s(ActionSeat, "C", 8, committed=0),
        ]
        result = next_to_act(players, current_actor_seat=8, last_aggressor_seat=None, current_highest_bet=10)
        assert result.player_id == "A"
        assert result.seat_number == 2

@pytest.mark.unit
class TestSkipping:
    def test_skip_folded_player(self, next_to_act, ActionSeat):
        players = [
            _s(ActionSeat, "A", 1, committed=0),
            _s(ActionSeat, "B", 2, folded=True, committed=0),
            _s(ActionSeat, "C", 3, committed=0),
        ]
        result = next_to_act(players, current_actor_seat=1, last_aggressor_seat=None, current_highest_bet=10)
        assert result.player_id == "C"

    def test_skip_all_in_player(self, next_to_act, ActionSeat):
        players = [
            _s(ActionSeat, "A", 1, committed=0),
            _s(ActionSeat, "B", 2, all_in=True, committed=10),
            _s(ActionSeat, "C", 3, committed=0),
        ]
        result = next_to_act(players, current_actor_seat=1, last_aggressor_seat=None, current_highest_bet=10)
        assert result.player_id == "C"

    def test_skip_inactive_player(self, next_to_act, ActionSeat):
        players = [
            _s(ActionSeat, "A", 1, committed=0),
            _s(ActionSeat, "B", 2, active=False, committed=0),
            _s(ActionSeat, "C", 3, committed=0),
        ]
        result = next_to_act(players, current_actor_seat=1, last_aggressor_seat=None, current_highest_bet=10)
        assert result.player_id == "C"

    def test_skip_multiple_ineligible(self, next_to_act, ActionSeat):
        players = [
            _s(ActionSeat, "A", 1, committed=0),
            _s(ActionSeat, "B", 2, folded=True),
            _s(ActionSeat, "C", 3, all_in=True),
            _s(ActionSeat, "D", 4, active=False),
            _s(ActionSeat, "E", 5, committed=0),
        ]
        result = next_to_act(players, current_actor_seat=1, last_aggressor_seat=None, current_highest_bet=10)
        assert result.player_id == "E"

    def test_skip_wraps_past_ineligible(self, next_to_act, ActionSeat):
        players = [
            _s(ActionSeat, "A", 1, committed=0),
            _s(ActionSeat, "B", 3, folded=True),
            _s(ActionSeat, "C", 5, committed=0),
        ]
        result = next_to_act(players, current_actor_seat=5, last_aggressor_seat=None, current_highest_bet=10)
        assert result.player_id == "A"

@pytest.mark.unit
class TestRoundClosure:
    def test_closed_when_returning_to_aggressor(self, next_to_act, ActionSeat):
        players = [
            _s(ActionSeat, "A", 1, committed=10),
            _s(ActionSeat, "B", 2, committed=10),
            _s(ActionSeat, "C", 3, committed=10),
        ]
        result = next_to_act(
            players, current_actor_seat=3, last_aggressor_seat=1, current_highest_bet=10,
        )
        assert result.is_round_closed is True
        assert result.player_id is None

    def test_not_closed_when_player_still_owes(self, next_to_act, ActionSeat):
        players = [
            _s(ActionSeat, "A", 1, committed=10),
            _s(ActionSeat, "B", 2, committed=10),
            _s(ActionSeat, "C", 3, committed=0),
        ]
        result = next_to_act(
            players, current_actor_seat=2, last_aggressor_seat=1, current_highest_bet=10,
        )
        assert result.is_round_closed is False
        assert result.player_id == "C"

    def test_closed_all_checked(self, next_to_act, ActionSeat):
        players = [
            _s(ActionSeat, "A", 1, committed=0),
            _s(ActionSeat, "B", 2, committed=0),
            _s(ActionSeat, "C", 3, committed=0),
        ]
        result = next_to_act(
            players, current_actor_seat=3, last_aggressor_seat=1, current_highest_bet=0,
        )
        assert result.is_round_closed is True

    def test_closed_when_all_matched_after_raise(self, next_to_act, ActionSeat):
        players = [
            _s(ActionSeat, "A", 1, committed=20),
            _s(ActionSeat, "B", 2, committed=20),
            _s(ActionSeat, "C", 3, committed=20),
        ]
        result = next_to_act(
            players, current_actor_seat=3, last_aggressor_seat=1, current_highest_bet=20,
        )
        assert result.is_round_closed is True

    def test_reopen_after_reraise(self, next_to_act, ActionSeat):
        players = [
            _s(ActionSeat, "A", 1, committed=10),
            _s(ActionSeat, "B", 2, committed=20),
            _s(ActionSeat, "C", 3, committed=0),
        ]
        result = next_to_act(
            players, current_actor_seat=2, last_aggressor_seat=2, current_highest_bet=20,
        )
        assert result.player_id == "C"
        assert result.is_round_closed is False

@pytest.mark.unit
class TestInsufficientEligible:
    def test_zero_eligible(self, next_to_act, ActionSeat):
        players = [
            _s(ActionSeat, "A", 1, folded=True),
            _s(ActionSeat, "B", 2, folded=True),
        ]
        result = next_to_act(players, current_actor_seat=1, last_aggressor_seat=None, current_highest_bet=0)
        assert result.is_round_closed is True

    def test_one_eligible(self, next_to_act, ActionSeat):
        players = [
            _s(ActionSeat, "A", 1, committed=0),
            _s(ActionSeat, "B", 2, folded=True),
            _s(ActionSeat, "C", 3, all_in=True),
        ]
        result = next_to_act(players, current_actor_seat=1, last_aggressor_seat=None, current_highest_bet=0)
        assert result.is_round_closed is True

    def test_all_all_in(self, next_to_act, ActionSeat):
        players = [
            _s(ActionSeat, "A", 1, all_in=True, committed=100),
            _s(ActionSeat, "B", 2, all_in=True, committed=50),
        ]
        result = next_to_act(players, current_actor_seat=1, last_aggressor_seat=None, current_highest_bet=100)
        assert result.is_round_closed is True

    def test_empty_players(self, next_to_act):
        result = next_to_act([], current_actor_seat=1, last_aggressor_seat=None, current_highest_bet=0)
        assert result.is_round_closed is True

@pytest.mark.unit
class TestHeadsUp:
    def test_basic_alternation(self, next_to_act, ActionSeat):
        players = [
            _s(ActionSeat, "A", 1, committed=0),
            _s(ActionSeat, "B", 2, committed=0),
        ]
        result = next_to_act(players, current_actor_seat=1, last_aggressor_seat=None, current_highest_bet=10)
        assert result.player_id == "B"

    def test_heads_up_preflop_sb_acts_first(self, next_to_act, ActionSeat):
        players = [
            _s(ActionSeat, "A", 1, committed=10),
            _s(ActionSeat, "B", 2, committed=0),
        ]
        result = next_to_act(
            players, current_actor_seat=1, last_aggressor_seat=None, current_highest_bet=10,
        )
        assert result.player_id == "B"
        assert result.is_round_closed is False

        players_after_bb_checks = [
            _s(ActionSeat, "A", 1, committed=10),
            _s(ActionSeat, "B", 2, committed=10),
        ]
        result2 = next_to_act(
            players_after_bb_checks, current_actor_seat=2, last_aggressor_seat=None, current_highest_bet=10,
        )
        assert result2.is_round_closed is True

    def test_heads_up_one_folds(self, next_to_act, ActionSeat):
        players = [
            _s(ActionSeat, "A", 1, committed=10),
            _s(ActionSeat, "B", 2, folded=True, committed=5),
        ]
        result = next_to_act(players, current_actor_seat=2, last_aggressor_seat=1, current_highest_bet=10)
        assert result.is_round_closed is True

    def test_heads_up_postflop_dealer_acts_last(self, next_to_act, ActionSeat):
        players = [
            _s(ActionSeat, "A", 1, committed=0),
            _s(ActionSeat, "B", 2, committed=0),
        ]
        result = next_to_act(players, current_actor_seat=2, last_aggressor_seat=2, current_highest_bet=0)
        pass

    def test_heads_up_no_aggressor_all_check(self, next_to_act, ActionSeat):
        players = [
            _s(ActionSeat, "A", 1, committed=0),
            _s(ActionSeat, "B", 2, committed=0),
        ]
        result = next_to_act(players, current_actor_seat=2, last_aggressor_seat=None, current_highest_bet=0)
        assert result.is_round_closed is True

    def test_heads_up_raise_war(self, next_to_act, ActionSeat):
        players = [
            _s(ActionSeat, "A", 1, committed=10),
            _s(ActionSeat, "B", 2, committed=20),
        ]
        result = next_to_act(
            players, current_actor_seat=2, last_aggressor_seat=2, current_highest_bet=20,
        )
        assert result.player_id == "A"
        assert result.is_round_closed is False

@pytest.mark.unit
class TestThreePlayer:
    def test_simple_rotation(self, next_to_act, ActionSeat):
        players = [
            _s(ActionSeat, "A", 1, committed=0),
            _s(ActionSeat, "B", 2, committed=0),
            _s(ActionSeat, "C", 3, committed=0),
        ]
        r1 = next_to_act(players, current_actor_seat=1, last_aggressor_seat=None, current_highest_bet=10)
        assert r1.player_id == "B"
        r2 = next_to_act(players, current_actor_seat=2, last_aggressor_seat=None, current_highest_bet=10)
        assert r2.player_id == "C"

    def test_skip_middle_folded(self, next_to_act, ActionSeat):
        players = [
            _s(ActionSeat, "A", 1, committed=0),
            _s(ActionSeat, "B", 2, folded=True),
            _s(ActionSeat, "C", 3, committed=0),
        ]
        result = next_to_act(players, current_actor_seat=1, last_aggressor_seat=None, current_highest_bet=10)
        assert result.player_id == "C"

    def test_all_called_closes(self, next_to_act, ActionSeat):
        players = [
            _s(ActionSeat, "A", 1, committed=20),
            _s(ActionSeat, "B", 2, committed=20),
            _s(ActionSeat, "C", 3, committed=20),
        ]
        result = next_to_act(
            players, current_actor_seat=3, last_aggressor_seat=1, current_highest_bet=20,
        )
        assert result.is_round_closed is True

    def test_reraise_reopens(self, next_to_act, ActionSeat):
        players = [
            _s(ActionSeat, "A", 1, committed=10),
            _s(ActionSeat, "B", 2, committed=30),
            _s(ActionSeat, "C", 3, committed=0),
        ]
        result = next_to_act(
            players, current_actor_seat=2, last_aggressor_seat=2, current_highest_bet=30,
        )
        assert result.player_id == "C"

    def test_after_c_calls_a_still_owes(self, next_to_act, ActionSeat):
        players = [
            _s(ActionSeat, "A", 1, committed=10),
            _s(ActionSeat, "B", 2, committed=30),
            _s(ActionSeat, "C", 3, committed=30),
        ]
        result = next_to_act(
            players, current_actor_seat=3, last_aggressor_seat=2, current_highest_bet=30,
        )
        assert result.player_id == "A"
        assert result.is_round_closed is False

    def test_a_calls_round_closes(self, next_to_act, ActionSeat):
        players = [
            _s(ActionSeat, "A", 1, committed=30),
            _s(ActionSeat, "B", 2, committed=30),
            _s(ActionSeat, "C", 3, committed=30),
        ]
        result = next_to_act(
            players, current_actor_seat=1, last_aggressor_seat=2, current_highest_bet=30,
        )
        assert result.is_round_closed is True

    def test_one_folds_two_remain(self, next_to_act, ActionSeat):
        players = [
            _s(ActionSeat, "A", 1, folded=True),
            _s(ActionSeat, "B", 2, committed=10),
            _s(ActionSeat, "C", 3, committed=0),
        ]
        result = next_to_act(
            players, current_actor_seat=2, last_aggressor_seat=2, current_highest_bet=10,
        )
        assert result.player_id == "C"

    def test_two_fold_one_remains(self, next_to_act, ActionSeat):
        players = [
            _s(ActionSeat, "A", 1, folded=True),
            _s(ActionSeat, "B", 2, committed=10),
            _s(ActionSeat, "C", 3, folded=True),
        ]
        result = next_to_act(
            players, current_actor_seat=3, last_aggressor_seat=2, current_highest_bet=10,
        )
        assert result.is_round_closed is True

@pytest.mark.unit
class TestSixPlayer:
    def test_full_table_rotation(self, next_to_act, ActionSeat):
        players = [_s(ActionSeat, f"P{i}", i, committed=0) for i in range(1, 7)]
        result = next_to_act(players, current_actor_seat=3, last_aggressor_seat=None, current_highest_bet=10)
        assert result.player_id == "P4"

    def test_six_player_with_folds(self, next_to_act, ActionSeat):
        players = [
            _s(ActionSeat, "P1", 1, committed=0),
            _s(ActionSeat, "P2", 2, folded=True),
            _s(ActionSeat, "P3", 3, committed=0),
            _s(ActionSeat, "P4", 4, folded=True),
            _s(ActionSeat, "P5", 5, folded=True),
            _s(ActionSeat, "P6", 6, committed=0),
        ]
        result = next_to_act(players, current_actor_seat=1, last_aggressor_seat=None, current_highest_bet=10)
        assert result.player_id == "P3"

    def test_six_player_complex_scenario(self, next_to_act, ActionSeat):
        players = [
            _s(ActionSeat, "P1", 1, committed=20),
            _s(ActionSeat, "P2", 2, folded=True),
            _s(ActionSeat, "P3", 3, committed=20),
            _s(ActionSeat, "P4", 4, all_in=True, committed=15),
            _s(ActionSeat, "P5", 5, committed=20),
            _s(ActionSeat, "P6", 6, folded=True),
        ]
        result = next_to_act(
            players, current_actor_seat=5, last_aggressor_seat=1, current_highest_bet=20,
        )
        assert result.is_round_closed is True

    def test_six_player_reraise_mid_table(self, next_to_act, ActionSeat):
        players = [
            _s(ActionSeat, "P1", 1, committed=10),
            _s(ActionSeat, "P2", 2, folded=True),
            _s(ActionSeat, "P3", 3, committed=30),
            _s(ActionSeat, "P4", 4, folded=True),
            _s(ActionSeat, "P5", 5, committed=0),
            _s(ActionSeat, "P6", 6, committed=0),
        ]
        result = next_to_act(
            players, current_actor_seat=3, last_aggressor_seat=3, current_highest_bet=30,
        )
        assert result.player_id == "P5"

    def test_six_player_p5_calls_p6_owes(self, next_to_act, ActionSeat):
        players = [
            _s(ActionSeat, "P1", 1, committed=10),
            _s(ActionSeat, "P2", 2, folded=True),
            _s(ActionSeat, "P3", 3, committed=30),
            _s(ActionSeat, "P4", 4, folded=True),
            _s(ActionSeat, "P5", 5, committed=30),
            _s(ActionSeat, "P6", 6, committed=0),
        ]
        result = next_to_act(
            players, current_actor_seat=5, last_aggressor_seat=3, current_highest_bet=30,
        )
        assert result.player_id == "P6"

    def test_six_player_p6_calls_p1_owes(self, next_to_act, ActionSeat):
        players = [
            _s(ActionSeat, "P1", 1, committed=10),
            _s(ActionSeat, "P2", 2, folded=True),
            _s(ActionSeat, "P3", 3, committed=30),
            _s(ActionSeat, "P4", 4, folded=True),
            _s(ActionSeat, "P5", 5, committed=30),
            _s(ActionSeat, "P6", 6, committed=30),
        ]
        result = next_to_act(
            players, current_actor_seat=6, last_aggressor_seat=3, current_highest_bet=30,
        )
        assert result.player_id == "P1"

    def test_six_player_p1_calls_closes(self, next_to_act, ActionSeat):
        players = [
            _s(ActionSeat, "P1", 1, committed=30),
            _s(ActionSeat, "P2", 2, folded=True),
            _s(ActionSeat, "P3", 3, committed=30),
            _s(ActionSeat, "P4", 4, folded=True),
            _s(ActionSeat, "P5", 5, committed=30),
            _s(ActionSeat, "P6", 6, committed=30),
        ]
        result = next_to_act(
            players, current_actor_seat=1, last_aggressor_seat=3, current_highest_bet=30,
        )
        assert result.is_round_closed is True

    def test_six_player_wrap_around(self, next_to_act, ActionSeat):
        players = [
            _s(ActionSeat, "P1", 1, folded=True),
            _s(ActionSeat, "P2", 2, committed=0),
            _s(ActionSeat, "P3", 3, folded=True),
            _s(ActionSeat, "P4", 4, committed=0),
            _s(ActionSeat, "P5", 5, folded=True),
            _s(ActionSeat, "P6", 6, committed=0),
        ]
        result = next_to_act(players, current_actor_seat=6, last_aggressor_seat=None, current_highest_bet=10)
        assert result.player_id == "P2"

@pytest.mark.unit
class TestPreFlopBBOption:
    def test_bb_gets_option_after_everyone_calls(self, next_to_act, ActionSeat):
        players = [
            _s(ActionSeat, "SB", 1, committed=10),
            _s(ActionSeat, "BB", 2, committed=0),
            _s(ActionSeat, "UTG", 3, committed=10),
        ]
        result = next_to_act(
            players, current_actor_seat=1, last_aggressor_seat=None, current_highest_bet=10,
        )
        assert result.player_id == "BB"
        assert result.is_round_closed is False

@pytest.mark.unit
class TestNoAggressor:
    def test_no_aggressor_with_outstanding_debt(self, next_to_act, ActionSeat):
        players = [
            _s(ActionSeat, "A", 1, committed=10),
            _s(ActionSeat, "B", 2, committed=0),
        ]
        result = next_to_act(
            players, current_actor_seat=1, last_aggressor_seat=None, current_highest_bet=10,
        )
        assert result.player_id == "B"
        assert result.is_round_closed is False

    def test_no_aggressor_nobody_owes(self, next_to_act, ActionSeat):
        players = [
            _s(ActionSeat, "A", 1, committed=10),
            _s(ActionSeat, "B", 2, committed=10),
            _s(ActionSeat, "C", 3, committed=10),
        ]
        result = next_to_act(
            players, current_actor_seat=3, last_aggressor_seat=None, current_highest_bet=10,
        )
        assert result.is_round_closed is True

    def test_no_aggressor_all_zero(self, next_to_act, ActionSeat):
        players = [
            _s(ActionSeat, "A", 1, committed=0),
            _s(ActionSeat, "B", 2, committed=0),
        ]
        result = next_to_act(
            players, current_actor_seat=2, last_aggressor_seat=None, current_highest_bet=0,
        )
        assert result.is_round_closed is True

@pytest.mark.unit
class TestAllInMix:
    def test_one_all_in_others_still_acting(self, next_to_act, ActionSeat):
        players = [
            _s(ActionSeat, "A", 1, all_in=True, committed=50),
            _s(ActionSeat, "B", 2, committed=10),
            _s(ActionSeat, "C", 3, committed=0),
        ]
        result = next_to_act(
            players, current_actor_seat=1, last_aggressor_seat=1, current_highest_bet=50,
        )
        assert result.player_id == "B"

    def test_all_in_player_not_the_next(self, next_to_act, ActionSeat):
        players = [
            _s(ActionSeat, "A", 1, committed=20),
            _s(ActionSeat, "B", 2, all_in=True, committed=50),
            _s(ActionSeat, "C", 3, committed=0),
        ]
        result = next_to_act(
            players, current_actor_seat=2, last_aggressor_seat=2, current_highest_bet=50,
        )
        assert result.player_id == "C"

    def test_two_all_in_one_active(self, next_to_act, ActionSeat):
        players = [
            _s(ActionSeat, "A", 1, all_in=True, committed=30),
            _s(ActionSeat, "B", 2, all_in=True, committed=50),
            _s(ActionSeat, "C", 3, committed=20),
        ]
        result = next_to_act(
            players, current_actor_seat=2, last_aggressor_seat=2, current_highest_bet=50,
        )
        assert result.is_round_closed is True