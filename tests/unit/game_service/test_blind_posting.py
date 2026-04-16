"""
Unit tests for forced blind and ante posting.

Covers:
- Normal SB + BB posting (3+ players)
- Heads-up blind posting (SB = dealer)
- Antes for all players
- Combined antes + blinds
- Short-stack SB: all-in for partial blind
- Short-stack BB: all-in for partial blind
- Short-stack ante: all-in during ante, nothing left for blind
- Exact-amount stacks (goes all-in at exactly zero remaining)
- Six-player table with antes and mixed short stacks
- Zero-chip player (committed=0, is_all_in=False)
- Pot and current_highest_bet correctness
"""

from __future__ import annotations

import os

import pytest

from tests.service_loader import load_service_app_module

os.environ.setdefault("GAME_DB", "sqlite+aiosqlite:///:memory:")
os.environ.setdefault("RABBIT_URL", "amqp://guest:guest@localhost:5672/")
os.environ.setdefault("EXCHANGE_NAME", "test_exchange")

@pytest.fixture(scope="module")
def blind_module():
    mod = load_service_app_module("game-service", "domain/engine/blind_posting")
    return mod

@pytest.fixture(scope="module")
def post_blinds_and_antes(blind_module):
    return blind_module.post_blinds_and_antes

@pytest.fixture(scope="module")
def SeatPlayer(blind_module):
    return blind_module.SeatPlayer

def _sp(cls, pid: str, seat: int, stack: int):
    return cls(player_id=pid, seat_number=seat, stack=stack)


def _find(result, pid: str):
    return next(p for p in result.players if p.player_id == pid)

class TestNormalBlinds:
    def test_three_players_sb_bb_posted(self, post_blinds_and_antes, SeatPlayer):
        players = [
            _sp(SeatPlayer, "A", 1, 1000),
            _sp(SeatPlayer, "B", 2, 1000),
            _sp(SeatPlayer, "C", 3, 1000),
        ]
        result = post_blinds_and_antes(
            players, small_blind_seat=2, big_blind_seat=3,
            small_blind_amount=50, big_blind_amount=100,
        )

        a = _find(result, "A")
        assert a.committed_this_street == 0
        assert a.committed_this_hand == 0
        assert a.stack_remaining == 1000
        assert a.is_all_in is False

        b = _find(result, "B")
        assert b.committed_this_street == 50
        assert b.committed_this_hand == 50
        assert b.stack_remaining == 950
        assert b.is_all_in is False

        c = _find(result, "C")
        assert c.committed_this_street == 100
        assert c.committed_this_hand == 100
        assert c.stack_remaining == 900
        assert c.is_all_in is False

    def test_pot_total(self, post_blinds_and_antes, SeatPlayer):
        players = [
            _sp(SeatPlayer, "A", 1, 1000),
            _sp(SeatPlayer, "B", 2, 1000),
            _sp(SeatPlayer, "C", 3, 1000),
        ]
        result = post_blinds_and_antes(
            players, small_blind_seat=2, big_blind_seat=3,
            small_blind_amount=50, big_blind_amount=100,
        )
        assert result.pot_total == 150

    def test_current_highest_bet(self, post_blinds_and_antes, SeatPlayer):
        players = [
            _sp(SeatPlayer, "A", 1, 1000),
            _sp(SeatPlayer, "B", 2, 1000),
            _sp(SeatPlayer, "C", 3, 1000),
        ]
        result = post_blinds_and_antes(
            players, small_blind_seat=2, big_blind_seat=3,
            small_blind_amount=50, big_blind_amount=100,
        )
        assert result.current_highest_bet == 100

    def test_player_order_preserved(self, post_blinds_and_antes, SeatPlayer):
        players = [
            _sp(SeatPlayer, "C", 5, 500),
            _sp(SeatPlayer, "A", 1, 500),
            _sp(SeatPlayer, "B", 3, 500),
        ]
        result = post_blinds_and_antes(
            players, small_blind_seat=3, big_blind_seat=5,
            small_blind_amount=10, big_blind_amount=20,
        )
        assert [p.player_id for p in result.players] == ["C", "A", "B"]

class TestHeadsUpBlinds:
    def test_heads_up_normal(self, post_blinds_and_antes, SeatPlayer):
        players = [
            _sp(SeatPlayer, "A", 1, 1000),
            _sp(SeatPlayer, "B", 2, 1000),
        ]
        result = post_blinds_and_antes(
            players, small_blind_seat=1, big_blind_seat=2,
            small_blind_amount=50, big_blind_amount=100,
        )

        a = _find(result, "A")
        assert a.committed_this_street == 50
        assert a.stack_remaining == 950
        assert a.is_all_in is False

        b = _find(result, "B")
        assert b.committed_this_street == 100
        assert b.stack_remaining == 900
        assert b.is_all_in is False

        assert result.pot_total == 150
        assert result.current_highest_bet == 100

    def test_heads_up_both_short(self, post_blinds_and_antes, SeatPlayer):
        players = [
            _sp(SeatPlayer, "A", 1, 30),
            _sp(SeatPlayer, "B", 2, 60),
        ]
        result = post_blinds_and_antes(
            players, small_blind_seat=1, big_blind_seat=2,
            small_blind_amount=50, big_blind_amount=100,
        )

        a = _find(result, "A")
        assert a.committed_this_street == 30
        assert a.stack_remaining == 0
        assert a.is_all_in is True

        b = _find(result, "B")
        assert b.committed_this_street == 60
        assert b.stack_remaining == 0
        assert b.is_all_in is True

        assert result.pot_total == 90
        assert result.current_highest_bet == 60

class TestAntes:
    def test_ante_all_players(self, post_blinds_and_antes, SeatPlayer):
        players = [
            _sp(SeatPlayer, "A", 1, 1000),
            _sp(SeatPlayer, "B", 2, 1000),
            _sp(SeatPlayer, "C", 3, 1000),
        ]
        result = post_blinds_and_antes(
            players, small_blind_seat=2, big_blind_seat=3,
            small_blind_amount=50, big_blind_amount=100,
            ante_amount=10,
        )

        a = _find(result, "A")
        assert a.committed_this_street == 10
        assert a.stack_remaining == 990

        b = _find(result, "B")
        assert b.committed_this_street == 60
        assert b.stack_remaining == 940

        c = _find(result, "C")
        assert c.committed_this_street == 110
        assert c.stack_remaining == 890

        assert result.pot_total == 180
        assert result.current_highest_bet == 110

    def test_zero_ante_ignored(self, post_blinds_and_antes, SeatPlayer):
        players = [
            _sp(SeatPlayer, "A", 1, 500),
            _sp(SeatPlayer, "B", 2, 500),
        ]
        result = post_blinds_and_antes(
            players, small_blind_seat=1, big_blind_seat=2,
            small_blind_amount=25, big_blind_amount=50,
            ante_amount=0,
        )
        assert _find(result, "A").committed_this_street == 25
        assert _find(result, "B").committed_this_street == 50
        assert result.pot_total == 75

class TestShortStacks:
    def test_sb_short_stack(self, post_blinds_and_antes, SeatPlayer):
        players = [
            _sp(SeatPlayer, "A", 1, 1000),
            _sp(SeatPlayer, "B", 2, 30),
            _sp(SeatPlayer, "C", 3, 1000),
        ]
        result = post_blinds_and_antes(
            players, small_blind_seat=2, big_blind_seat=3,
            small_blind_amount=50, big_blind_amount=100,
        )

        b = _find(result, "B")
        assert b.committed_this_street == 30
        assert b.stack_remaining == 0
        assert b.is_all_in is True

    def test_bb_short_stack(self, post_blinds_and_antes, SeatPlayer):
        players = [
            _sp(SeatPlayer, "A", 1, 1000),
            _sp(SeatPlayer, "B", 2, 1000),
            _sp(SeatPlayer, "C", 3, 75),
        ]
        result = post_blinds_and_antes(
            players, small_blind_seat=2, big_blind_seat=3,
            small_blind_amount=50, big_blind_amount=100,
        )

        c = _find(result, "C")
        assert c.committed_this_street == 75
        assert c.stack_remaining == 0
        assert c.is_all_in is True
        assert result.current_highest_bet == 75

    def test_sb_exactly_blind(self, post_blinds_and_antes, SeatPlayer):
        players = [
            _sp(SeatPlayer, "A", 1, 1000),
            _sp(SeatPlayer, "B", 2, 50),
            _sp(SeatPlayer, "C", 3, 1000),
        ]
        result = post_blinds_and_antes(
            players, small_blind_seat=2, big_blind_seat=3,
            small_blind_amount=50, big_blind_amount=100,
        )

        b = _find(result, "B")
        assert b.committed_this_street == 50
        assert b.stack_remaining == 0
        assert b.is_all_in is True

    def test_bb_exactly_blind(self, post_blinds_and_antes, SeatPlayer):
        players = [
            _sp(SeatPlayer, "A", 1, 1000),
            _sp(SeatPlayer, "B", 2, 1000),
            _sp(SeatPlayer, "C", 3, 100),
        ]
        result = post_blinds_and_antes(
            players, small_blind_seat=2, big_blind_seat=3,
            small_blind_amount=50, big_blind_amount=100,
        )

        c = _find(result, "C")
        assert c.committed_this_street == 100
        assert c.stack_remaining == 0
        assert c.is_all_in is True

    def test_ante_exhausts_stack_before_blind(self, post_blinds_and_antes, SeatPlayer):
        players = [
            _sp(SeatPlayer, "A", 1, 1000),
            _sp(SeatPlayer, "B", 2, 10),
            _sp(SeatPlayer, "C", 3, 1000),
        ]
        result = post_blinds_and_antes(
            players, small_blind_seat=2, big_blind_seat=3,
            small_blind_amount=50, big_blind_amount=100,
            ante_amount=10,
        )

        b = _find(result, "B")
        assert b.committed_this_street == 10
        assert b.stack_remaining == 0
        assert b.is_all_in is True

    def test_ante_partial_then_no_blind(self, post_blinds_and_antes, SeatPlayer):
        players = [
            _sp(SeatPlayer, "A", 1, 1000),
            _sp(SeatPlayer, "B", 2, 1000),
            _sp(SeatPlayer, "C", 3, 5),
        ]
        result = post_blinds_and_antes(
            players, small_blind_seat=2, big_blind_seat=3,
            small_blind_amount=50, big_blind_amount=100,
            ante_amount=10,
        )

        c = _find(result, "C")
        assert c.committed_this_street == 5
        assert c.stack_remaining == 0
        assert c.is_all_in is True

    def test_ante_partial_then_partial_blind(self, post_blinds_and_antes, SeatPlayer):
        players = [
            _sp(SeatPlayer, "A", 1, 1000),
            _sp(SeatPlayer, "B", 2, 40),
            _sp(SeatPlayer, "C", 3, 1000),
        ]
        result = post_blinds_and_antes(
            players, small_blind_seat=2, big_blind_seat=3,
            small_blind_amount=50, big_blind_amount=100,
            ante_amount=10,
        )

        b = _find(result, "B")
        assert b.committed_this_street == 40
        assert b.stack_remaining == 0
        assert b.is_all_in is True

    def test_zero_stack_player(self, post_blinds_and_antes, SeatPlayer):
        players = [
            _sp(SeatPlayer, "A", 1, 0),
            _sp(SeatPlayer, "B", 2, 1000),
            _sp(SeatPlayer, "C", 3, 1000),
        ]
        result = post_blinds_and_antes(
            players, small_blind_seat=2, big_blind_seat=3,
            small_blind_amount=50, big_blind_amount=100,
        )

        a = _find(result, "A")
        assert a.committed_this_street == 0
        assert a.stack_remaining == 0
        assert a.is_all_in is False

class TestSixPlayerTable:
    def test_six_player_normal(self, post_blinds_and_antes, SeatPlayer):
        players = [
            _sp(SeatPlayer, "P1", 1, 1000),
            _sp(SeatPlayer, "P2", 2, 1000),
            _sp(SeatPlayer, "P3", 3, 1000),
            _sp(SeatPlayer, "P4", 4, 1000),
            _sp(SeatPlayer, "P5", 5, 1000),
            _sp(SeatPlayer, "P6", 6, 1000),
        ]
        result = post_blinds_and_antes(
            players, small_blind_seat=2, big_blind_seat=3,
            small_blind_amount=50, big_blind_amount=100,
        )

        assert result.pot_total == 150
        assert result.current_highest_bet == 100
        for pid in ("P1", "P4", "P5", "P6"):
            assert _find(result, pid).committed_this_street == 0

    def test_six_player_with_antes(self, post_blinds_and_antes, SeatPlayer):
        players = [
            _sp(SeatPlayer, "P1", 1, 1000),
            _sp(SeatPlayer, "P2", 2, 1000),
            _sp(SeatPlayer, "P3", 3, 1000),
            _sp(SeatPlayer, "P4", 4, 1000),
            _sp(SeatPlayer, "P5", 5, 1000),
            _sp(SeatPlayer, "P6", 6, 1000),
        ]
        result = post_blinds_and_antes(
            players, small_blind_seat=2, big_blind_seat=3,
            small_blind_amount=50, big_blind_amount=100,
            ante_amount=10,
        )

        for pid in ("P1", "P4", "P5", "P6"):
            p = _find(result, pid)
            assert p.committed_this_street == 10
            assert p.stack_remaining == 990

        assert _find(result, "P2").committed_this_street == 60
        assert _find(result, "P3").committed_this_street == 110

        assert result.pot_total == 210
        assert result.current_highest_bet == 110

    def test_six_player_mixed_short_stacks(self, post_blinds_and_antes, SeatPlayer):
        players = [
            _sp(SeatPlayer, "P1", 1, 1000),
            _sp(SeatPlayer, "P2", 2, 25),
            _sp(SeatPlayer, "P3", 3, 50),
            _sp(SeatPlayer, "P4", 4, 5),
            _sp(SeatPlayer, "P5", 5, 1000),
            _sp(SeatPlayer, "P6", 6, 1000),
        ]
        result = post_blinds_and_antes(
            players, small_blind_seat=2, big_blind_seat=3,
            small_blind_amount=50, big_blind_amount=100,
            ante_amount=10,
        )

        p2 = _find(result, "P2")
        assert p2.committed_this_street == 25
        assert p2.stack_remaining == 0
        assert p2.is_all_in is True

        p3 = _find(result, "P3")
        assert p3.committed_this_street == 50
        assert p3.stack_remaining == 0
        assert p3.is_all_in is True

        p4 = _find(result, "P4")
        assert p4.committed_this_street == 5
        assert p4.stack_remaining == 0
        assert p4.is_all_in is True

        assert _find(result, "P1").committed_this_street == 10
        assert _find(result, "P5").committed_this_street == 10
        assert _find(result, "P6").committed_this_street == 10

        assert result.pot_total == 110

class TestEdgeCases:
    def test_single_player(self, post_blinds_and_antes, SeatPlayer):
        players = [_sp(SeatPlayer, "A", 1, 500)]
        result = post_blinds_and_antes(
            players, small_blind_seat=1, big_blind_seat=2,
            small_blind_amount=25, big_blind_amount=50,
        )
        assert _find(result, "A").committed_this_street == 25
        assert result.pot_total == 25

    def test_empty_players(self, post_blinds_and_antes, SeatPlayer):
        result = post_blinds_and_antes(
            [], small_blind_seat=1, big_blind_seat=2,
            small_blind_amount=25, big_blind_amount=50,
        )
        assert result.players == []
        assert result.pot_total == 0
        assert result.current_highest_bet == 0

    def test_large_antes_small_blinds(self, post_blinds_and_antes, SeatPlayer):
        players = [
            _sp(SeatPlayer, "A", 1, 500),
            _sp(SeatPlayer, "B", 2, 500),
            _sp(SeatPlayer, "C", 3, 500),
        ]
        result = post_blinds_and_antes(
            players, small_blind_seat=2, big_blind_seat=3,
            small_blind_amount=25, big_blind_amount=50,
            ante_amount=100,
        )
        a = _find(result, "A")
        assert a.committed_this_street == 100
        assert a.stack_remaining == 400

        b = _find(result, "B")
        assert b.committed_this_street == 125
        assert b.stack_remaining == 375

        c = _find(result, "C")
        assert c.committed_this_street == 150
        assert c.stack_remaining == 350

        assert result.pot_total == 375
        assert result.current_highest_bet == 150

    def test_non_contiguous_seats(self, post_blinds_and_antes, SeatPlayer):
        players = [
            _sp(SeatPlayer, "A", 3, 800),
            _sp(SeatPlayer, "B", 7, 800),
            _sp(SeatPlayer, "C", 9, 800),
        ]
        result = post_blinds_and_antes(
            players, small_blind_seat=7, big_blind_seat=9,
            small_blind_amount=25, big_blind_amount=50,
        )
        assert _find(result, "A").committed_this_street == 0
        assert _find(result, "B").committed_this_street == 25
        assert _find(result, "C").committed_this_street == 50
        assert result.pot_total == 75