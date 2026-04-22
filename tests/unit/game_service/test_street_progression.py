"""
Comprehensive unit tests for the street progression engine.

Tests cover:
- next_street() transitions
- find_first_to_act() seat selection
- evaluate_street_end() for all outcome types
- Heads-up (2-player) specific scenarios
- Multi-player (3–6 player) scenarios
- Edge cases: all-in cascades, fold-to-win, showdown from river
"""

from __future__ import annotations

import os

import pytest

from tests.service_loader import load_service_app_module

os.environ.setdefault("GAME_DB", "sqlite+aiosqlite:///:memory:")
os.environ.setdefault("RABBIT_URL", "amqp://guest:guest@localhost:5672/")
os.environ.setdefault("EXCHANGE_NAME", "test_exchange")

@pytest.fixture(scope="module")
def sp_module():
    return load_service_app_module(
        "game-service",
        "domain/engine/street_progression",
        package_name="game_street_test_app",
        reload_modules=True,
    )

@pytest.fixture(scope="module")
def constants_module():
    return load_service_app_module(
        "game-service",
        "domain/constants",
        package_name="game_street_test_app",
    )

@pytest.fixture(scope="module")
def Street(constants_module):
    return constants_module.Street

@pytest.fixture(scope="module")
def StreetAdvanceAction(constants_module):
    return constants_module.StreetAdvanceAction

@pytest.fixture(scope="module")
def PlayerSeat(sp_module):
    return sp_module.PlayerSeat

@pytest.fixture(scope="module")
def next_street(sp_module):
    return sp_module.next_street

@pytest.fixture(scope="module")
def find_first_to_act(sp_module):
    return sp_module.find_first_to_act

@pytest.fixture(scope="module")
def evaluate_street_end(sp_module):
    return sp_module.evaluate_street_end

def _seat(PS, pid, seat, *, folded=False, all_in=False, active=True):
    return PS(
        player_id=pid,
        seat_number=seat,
        has_folded=folded,
        is_all_in=all_in,
        is_active_in_hand=active,
    )

@pytest.mark.unit
class TestNextStreet:
    def test_pre_flop_to_flop(self, next_street, Street):
        assert next_street(Street.PRE_FLOP) == Street.FLOP

    def test_flop_to_turn(self, next_street, Street):
        assert next_street(Street.FLOP) == Street.TURN

    def test_turn_to_river(self, next_street, Street):
        assert next_street(Street.TURN) == Street.RIVER

    def test_river_to_showdown(self, next_street, Street):
        assert next_street(Street.RIVER) == Street.SHOWDOWN

    def test_showdown_is_terminal(self, next_street, Street):
        assert next_street(Street.SHOWDOWN) is None

    def test_unknown_street_returns_none(self, next_street):
        assert next_street("NONSENSE") is None

@pytest.mark.unit
class TestFindFirstToAct:
    def test_single_player(self, find_first_to_act, PlayerSeat):
        players = [_seat(PlayerSeat, "A", 3)]
        assert find_first_to_act(players, reference_seat=1) == "A"

    def test_next_after_reference(self, find_first_to_act, PlayerSeat):
        players = [
            _seat(PlayerSeat, "A", 1),
            _seat(PlayerSeat, "B", 3),
            _seat(PlayerSeat, "C", 5),
        ]
        assert find_first_to_act(players, reference_seat=1) == "B"

    def test_wraps_around(self, find_first_to_act, PlayerSeat):
        players = [
            _seat(PlayerSeat, "A", 1),
            _seat(PlayerSeat, "B", 3),
            _seat(PlayerSeat, "C", 5),
        ]
        assert find_first_to_act(players, reference_seat=5) == "A"

    def test_reference_between_gaps(self, find_first_to_act, PlayerSeat):
        players = [
            _seat(PlayerSeat, "A", 2),
            _seat(PlayerSeat, "B", 6),
        ]
        assert find_first_to_act(players, reference_seat=3) == "B"

    def test_reference_equals_seat_picks_next(self, find_first_to_act, PlayerSeat):
        players = [
            _seat(PlayerSeat, "A", 1),
            _seat(PlayerSeat, "B", 2),
            _seat(PlayerSeat, "C", 3),
        ]
        assert find_first_to_act(players, reference_seat=2) == "C"

    def test_empty_list_returns_none(self, find_first_to_act):
        assert find_first_to_act([], reference_seat=1) is None

    def test_reference_beyond_all_seats_wraps(self, find_first_to_act, PlayerSeat):
        players = [
            _seat(PlayerSeat, "A", 1),
            _seat(PlayerSeat, "B", 2),
        ]
        assert find_first_to_act(players, reference_seat=99) == "A"

@pytest.mark.unit
class TestSettleHand:
    def test_one_player_remaining(self, evaluate_street_end, PlayerSeat, Street, StreetAdvanceAction):
        players = [
            _seat(PlayerSeat, "A", 1),
            _seat(PlayerSeat, "B", 2, folded=True),
            _seat(PlayerSeat, "C", 3, folded=True),
        ]
        result = evaluate_street_end(Street.PRE_FLOP, dealer_seat=1, big_blind_seat=3, players=players)
        assert result.action == StreetAdvanceAction.SETTLE_HAND
        assert result.winning_player_id == "A"

    def test_single_remaining_after_multiple_folds(self, evaluate_street_end, PlayerSeat, Street, StreetAdvanceAction):
        players = [
            _seat(PlayerSeat, "A", 1, folded=True),
            _seat(PlayerSeat, "B", 2, folded=True),
            _seat(PlayerSeat, "C", 3, folded=True),
            _seat(PlayerSeat, "D", 4),
        ]
        result = evaluate_street_end(Street.FLOP, dealer_seat=1, big_blind_seat=3, players=players)
        assert result.action == StreetAdvanceAction.SETTLE_HAND
        assert result.winning_player_id == "D"

    def test_inactive_players_dont_count(self, evaluate_street_end, PlayerSeat, Street, StreetAdvanceAction):
        players = [
            _seat(PlayerSeat, "A", 1),
            _seat(PlayerSeat, "B", 2, active=False),
        ]
        result = evaluate_street_end(Street.PRE_FLOP, dealer_seat=1, big_blind_seat=2, players=players)
        assert result.action == StreetAdvanceAction.SETTLE_HAND
        assert result.winning_player_id == "A"

@pytest.mark.unit
class TestShowdown:
    def test_river_complete_triggers_showdown(self, evaluate_street_end, PlayerSeat, Street, StreetAdvanceAction):
        players = [
            _seat(PlayerSeat, "A", 1),
            _seat(PlayerSeat, "B", 2),
        ]
        result = evaluate_street_end(Street.RIVER, dealer_seat=1, big_blind_seat=2, players=players)
        assert result.action == StreetAdvanceAction.SHOWDOWN
        assert result.next_street == Street.SHOWDOWN

    def test_already_at_showdown(self, evaluate_street_end, PlayerSeat, Street, StreetAdvanceAction):
        players = [
            _seat(PlayerSeat, "A", 1),
            _seat(PlayerSeat, "B", 2),
        ]
        result = evaluate_street_end(Street.SHOWDOWN, dealer_seat=1, big_blind_seat=2, players=players)
        assert result.action == StreetAdvanceAction.SHOWDOWN

    def test_all_remaining_all_in(self, evaluate_street_end, PlayerSeat, Street, StreetAdvanceAction):
        players = [
            _seat(PlayerSeat, "A", 1, all_in=True),
            _seat(PlayerSeat, "B", 2, all_in=True),
            _seat(PlayerSeat, "C", 3, folded=True),
        ]
        result = evaluate_street_end(Street.PRE_FLOP, dealer_seat=1, big_blind_seat=3, players=players)
        assert result.action == StreetAdvanceAction.SHOWDOWN
        assert result.next_street == Street.SHOWDOWN

    def test_one_active_rest_all_in(self, evaluate_street_end, PlayerSeat, Street, StreetAdvanceAction):
        players = [
            _seat(PlayerSeat, "A", 1, all_in=True),
            _seat(PlayerSeat, "B", 2, all_in=True),
            _seat(PlayerSeat, "C", 3),
        ]
        result = evaluate_street_end(Street.FLOP, dealer_seat=1, big_blind_seat=3, players=players)
        assert result.action == StreetAdvanceAction.SHOWDOWN

    def test_river_with_mixed_allin_and_active(self, evaluate_street_end, PlayerSeat, Street, StreetAdvanceAction):
        players = [
            _seat(PlayerSeat, "A", 1, all_in=True),
            _seat(PlayerSeat, "B", 2),
            _seat(PlayerSeat, "C", 3),
        ]
        result = evaluate_street_end(Street.RIVER, dealer_seat=1, big_blind_seat=3, players=players)
        assert result.action == StreetAdvanceAction.SHOWDOWN

@pytest.mark.unit
class TestNextStreetAdvance:
    def test_preflop_to_flop(self, evaluate_street_end, PlayerSeat, Street, StreetAdvanceAction):
        players = [
            _seat(PlayerSeat, "A", 1),
            _seat(PlayerSeat, "B", 3),
            _seat(PlayerSeat, "C", 5),
        ]
        result = evaluate_street_end(Street.PRE_FLOP, dealer_seat=1, big_blind_seat=5, players=players)
        assert result.action == StreetAdvanceAction.NEXT_STREET
        assert result.next_street == Street.FLOP

    def test_flop_to_turn(self, evaluate_street_end, PlayerSeat, Street, StreetAdvanceAction):
        players = [
            _seat(PlayerSeat, "A", 1),
            _seat(PlayerSeat, "B", 2),
        ]
        result = evaluate_street_end(Street.FLOP, dealer_seat=1, big_blind_seat=2, players=players)
        assert result.action == StreetAdvanceAction.NEXT_STREET
        assert result.next_street == Street.TURN

    def test_turn_to_river(self, evaluate_street_end, PlayerSeat, Street, StreetAdvanceAction):
        players = [
            _seat(PlayerSeat, "A", 1),
            _seat(PlayerSeat, "B", 2),
        ]
        result = evaluate_street_end(Street.TURN, dealer_seat=1, big_blind_seat=2, players=players)
        assert result.action == StreetAdvanceAction.NEXT_STREET
        assert result.next_street == Street.RIVER

    def test_first_to_act_is_left_of_dealer(self, evaluate_street_end, PlayerSeat, Street):
        players = [
            _seat(PlayerSeat, "A", 1),
            _seat(PlayerSeat, "B", 3),
            _seat(PlayerSeat, "C", 5),
        ]
        result = evaluate_street_end(Street.PRE_FLOP, dealer_seat=1, big_blind_seat=5, players=players)
        assert result.acting_player_id == "B"

    def test_first_to_act_wraps_around(self, evaluate_street_end, PlayerSeat, Street):
        players = [
            _seat(PlayerSeat, "A", 1),
            _seat(PlayerSeat, "B", 3),
            _seat(PlayerSeat, "C", 5),
        ]
        result = evaluate_street_end(Street.PRE_FLOP, dealer_seat=5, big_blind_seat=3, players=players)
        assert result.acting_player_id == "A"

    def test_folded_players_skipped_for_first_to_act(self, evaluate_street_end, PlayerSeat, Street):
        players = [
            _seat(PlayerSeat, "A", 1),
            _seat(PlayerSeat, "B", 3, folded=True),
            _seat(PlayerSeat, "C", 5),
            _seat(PlayerSeat, "D", 7),
        ]
        result = evaluate_street_end(Street.PRE_FLOP, dealer_seat=1, big_blind_seat=3, players=players)
        assert result.acting_player_id == "C"

    def test_allin_players_skipped_for_first_to_act(self, evaluate_street_end, PlayerSeat, Street):
        players = [
            _seat(PlayerSeat, "A", 1),
            _seat(PlayerSeat, "B", 3, all_in=True),
            _seat(PlayerSeat, "C", 5),
            _seat(PlayerSeat, "D", 7),
        ]
        result = evaluate_street_end(Street.PRE_FLOP, dealer_seat=1, big_blind_seat=7, players=players)
        assert result.acting_player_id == "C"

@pytest.mark.unit
class TestHeadsUp:
    def test_heads_up_normal_advance(self, evaluate_street_end, PlayerSeat, Street, StreetAdvanceAction):
        players = [
            _seat(PlayerSeat, "A", 1),
            _seat(PlayerSeat, "B", 2),
        ]
        result = evaluate_street_end(Street.PRE_FLOP, dealer_seat=1, big_blind_seat=2, players=players)
        assert result.action == StreetAdvanceAction.NEXT_STREET
        assert result.next_street == Street.FLOP

    def test_heads_up_postflop_bb_acts_first(self, evaluate_street_end, PlayerSeat, Street):
        players = [
            _seat(PlayerSeat, "A", 1),
            _seat(PlayerSeat, "B", 2),
        ]
        result = evaluate_street_end(Street.PRE_FLOP, dealer_seat=1, big_blind_seat=2, players=players)
        assert result.acting_player_id == "B"

    def test_heads_up_postflop_reversed_seats(self, evaluate_street_end, PlayerSeat, Street):
        players = [
            _seat(PlayerSeat, "A", 1),
            _seat(PlayerSeat, "B", 2),
        ]
        result = evaluate_street_end(Street.FLOP, dealer_seat=2, big_blind_seat=1, players=players)
        assert result.acting_player_id == "A"

    def test_heads_up_one_folds(self, evaluate_street_end, PlayerSeat, Street, StreetAdvanceAction):
        players = [
            _seat(PlayerSeat, "A", 1),
            _seat(PlayerSeat, "B", 2, folded=True),
        ]
        result = evaluate_street_end(Street.PRE_FLOP, dealer_seat=1, big_blind_seat=2, players=players)
        assert result.action == StreetAdvanceAction.SETTLE_HAND
        assert result.winning_player_id == "A"

    def test_heads_up_both_all_in(self, evaluate_street_end, PlayerSeat, Street, StreetAdvanceAction):
        players = [
            _seat(PlayerSeat, "A", 1, all_in=True),
            _seat(PlayerSeat, "B", 2, all_in=True),
        ]
        result = evaluate_street_end(Street.PRE_FLOP, dealer_seat=1, big_blind_seat=2, players=players)
        assert result.action == StreetAdvanceAction.SHOWDOWN

    def test_heads_up_one_all_in(self, evaluate_street_end, PlayerSeat, Street, StreetAdvanceAction):
        players = [
            _seat(PlayerSeat, "A", 1, all_in=True),
            _seat(PlayerSeat, "B", 2),
        ]
        result = evaluate_street_end(Street.FLOP, dealer_seat=1, big_blind_seat=2, players=players)
        assert result.action == StreetAdvanceAction.SHOWDOWN

    def test_heads_up_through_all_streets(self, evaluate_street_end, PlayerSeat, Street, StreetAdvanceAction):
        players = [
            _seat(PlayerSeat, "A", 1),
            _seat(PlayerSeat, "B", 2),
        ]

        r1 = evaluate_street_end(Street.PRE_FLOP, dealer_seat=1, big_blind_seat=2, players=players)
        assert r1.action == StreetAdvanceAction.NEXT_STREET
        assert r1.next_street == Street.FLOP

        r2 = evaluate_street_end(Street.FLOP, dealer_seat=1, big_blind_seat=2, players=players)
        assert r2.action == StreetAdvanceAction.NEXT_STREET
        assert r2.next_street == Street.TURN

        r3 = evaluate_street_end(Street.TURN, dealer_seat=1, big_blind_seat=2, players=players)
        assert r3.action == StreetAdvanceAction.NEXT_STREET
        assert r3.next_street == Street.RIVER

        r4 = evaluate_street_end(Street.RIVER, dealer_seat=1, big_blind_seat=2, players=players)
        assert r4.action == StreetAdvanceAction.SHOWDOWN
        assert r4.next_street == Street.SHOWDOWN

@pytest.mark.unit
class TestMultiPlayer:
    def test_three_player_normal_advance(self, evaluate_street_end, PlayerSeat, Street, StreetAdvanceAction):
        players = [
            _seat(PlayerSeat, "A", 1),
            _seat(PlayerSeat, "B", 3),
            _seat(PlayerSeat, "C", 5),
        ]
        result = evaluate_street_end(Street.PRE_FLOP, dealer_seat=1, big_blind_seat=5, players=players)
        assert result.action == StreetAdvanceAction.NEXT_STREET
        assert result.next_street == Street.FLOP
        assert result.acting_player_id == "B"

    def test_four_player_two_folded_two_active(self, evaluate_street_end, PlayerSeat, Street, StreetAdvanceAction):
        players = [
            _seat(PlayerSeat, "A", 1, folded=True),
            _seat(PlayerSeat, "B", 2),
            _seat(PlayerSeat, "C", 3, folded=True),
            _seat(PlayerSeat, "D", 4),
        ]
        result = evaluate_street_end(Street.FLOP, dealer_seat=1, big_blind_seat=3, players=players)
        assert result.action == StreetAdvanceAction.NEXT_STREET
        assert result.acting_player_id == "B"

    def test_four_player_two_folded_one_allin_one_active(self, evaluate_street_end, PlayerSeat, Street, StreetAdvanceAction):
        players = [
            _seat(PlayerSeat, "A", 1, folded=True),
            _seat(PlayerSeat, "B", 2, all_in=True),
            _seat(PlayerSeat, "C", 3, folded=True),
            _seat(PlayerSeat, "D", 4),
        ]
        result = evaluate_street_end(Street.TURN, dealer_seat=1, big_blind_seat=3, players=players)
        assert result.action == StreetAdvanceAction.SHOWDOWN

    def test_four_player_three_all_in_one_active(self, evaluate_street_end, PlayerSeat, Street, StreetAdvanceAction):
        players = [
            _seat(PlayerSeat, "A", 1, all_in=True),
            _seat(PlayerSeat, "B", 2, all_in=True),
            _seat(PlayerSeat, "C", 3, all_in=True),
            _seat(PlayerSeat, "D", 4),
        ]
        result = evaluate_street_end(Street.PRE_FLOP, dealer_seat=1, big_blind_seat=2, players=players)
        assert result.action == StreetAdvanceAction.SHOWDOWN

    def test_six_player_complex_mix(self, evaluate_street_end, PlayerSeat, Street, StreetAdvanceAction):
        players = [
            _seat(PlayerSeat, "P1", 1, folded=True),
            _seat(PlayerSeat, "P2", 2, all_in=True),
            _seat(PlayerSeat, "P3", 3),
            _seat(PlayerSeat, "P4", 4, folded=True),
            _seat(PlayerSeat, "P5", 5),
            _seat(PlayerSeat, "P6", 6, all_in=True),
        ]
        result = evaluate_street_end(Street.FLOP, dealer_seat=2, big_blind_seat=4, players=players)
        assert result.action == StreetAdvanceAction.NEXT_STREET
        assert result.acting_player_id == "P3"

    def test_six_player_everyone_folds_to_one(self, evaluate_street_end, PlayerSeat, Street, StreetAdvanceAction):
        players = [
            _seat(PlayerSeat, "P1", 1, folded=True),
            _seat(PlayerSeat, "P2", 2, folded=True),
            _seat(PlayerSeat, "P3", 3, folded=True),
            _seat(PlayerSeat, "P4", 4, folded=True),
            _seat(PlayerSeat, "P5", 5, folded=True),
            _seat(PlayerSeat, "P6", 6),
        ]
        result = evaluate_street_end(Street.PRE_FLOP, dealer_seat=1, big_blind_seat=3, players=players)
        assert result.action == StreetAdvanceAction.SETTLE_HAND
        assert result.winning_player_id == "P6"

    def test_three_player_two_allin_on_flop(self, evaluate_street_end, PlayerSeat, Street, StreetAdvanceAction):
        players = [
            _seat(PlayerSeat, "A", 1, all_in=True),
            _seat(PlayerSeat, "B", 2, all_in=True),
            _seat(PlayerSeat, "C", 3),
        ]
        result = evaluate_street_end(Street.FLOP, dealer_seat=1, big_blind_seat=3, players=players)
        assert result.action == StreetAdvanceAction.SHOWDOWN

    def test_five_player_two_active(self, evaluate_street_end, PlayerSeat, Street, StreetAdvanceAction):
        players = [
            _seat(PlayerSeat, "A", 1),
            _seat(PlayerSeat, "B", 2, folded=True),
            _seat(PlayerSeat, "C", 3, all_in=True),
            _seat(PlayerSeat, "D", 4, folded=True),
            _seat(PlayerSeat, "E", 5),
        ]
        result = evaluate_street_end(Street.TURN, dealer_seat=4, big_blind_seat=2, players=players)
        assert result.action == StreetAdvanceAction.NEXT_STREET
        assert result.next_street == Street.RIVER
        assert result.acting_player_id == "E"

@pytest.mark.unit
class TestActingPlayerConsistency:
    def test_acting_player_is_never_folded(self, evaluate_street_end, PlayerSeat, Street, StreetAdvanceAction):
        players = [
            _seat(PlayerSeat, "A", 1, folded=True),
            _seat(PlayerSeat, "B", 2),
            _seat(PlayerSeat, "C", 3),
        ]
        result = evaluate_street_end(Street.PRE_FLOP, dealer_seat=1, big_blind_seat=3, players=players)
        if result.action == StreetAdvanceAction.NEXT_STREET:
            assert result.acting_player_id != "A"

    def test_acting_player_is_never_all_in(self, evaluate_street_end, PlayerSeat, Street, StreetAdvanceAction):
        players = [
            _seat(PlayerSeat, "A", 1, all_in=True),
            _seat(PlayerSeat, "B", 2),
            _seat(PlayerSeat, "C", 3),
        ]
        result = evaluate_street_end(Street.PRE_FLOP, dealer_seat=1, big_blind_seat=3, players=players)
        if result.action == StreetAdvanceAction.NEXT_STREET:
            assert result.acting_player_id != "A"

    def test_settle_has_no_acting_player(self, evaluate_street_end, PlayerSeat, Street, StreetAdvanceAction):
        players = [
            _seat(PlayerSeat, "A", 1),
            _seat(PlayerSeat, "B", 2, folded=True),
        ]
        result = evaluate_street_end(Street.PRE_FLOP, dealer_seat=1, big_blind_seat=2, players=players)
        assert result.action == StreetAdvanceAction.SETTLE_HAND
        assert result.acting_player_id is None

    def test_showdown_has_no_acting_player(self, evaluate_street_end, PlayerSeat, Street, StreetAdvanceAction):
        players = [
            _seat(PlayerSeat, "A", 1, all_in=True),
            _seat(PlayerSeat, "B", 2, all_in=True),
        ]
        result = evaluate_street_end(Street.PRE_FLOP, dealer_seat=1, big_blind_seat=2, players=players)
        assert result.action == StreetAdvanceAction.SHOWDOWN
        assert result.acting_player_id is None