"""
Comprehensive unit tests for the side-pot calculator.

Covers:
- Single-pot (no all-ins)
- Two-player heads-up all-in
- Three-player all-in at different levels
- Four-player with multiple side pots
- Folded players contribute but are ineligible
- Mixed fold + all-in scenarios
- All players fold (dead pot)
- Single player (everyone else folded pre-flop)
- Equal stacks, no side pots
- Zero commitment player
- Deterministic pot ordering
"""

from __future__ import annotations

import os

import pytest

from tests.service_loader import load_service_app_module

os.environ.setdefault("GAME_DB", "sqlite+aiosqlite:///:memory:")
os.environ.setdefault("RABBIT_URL", "amqp://guest:guest@localhost:5672/")
os.environ.setdefault("EXCHANGE_NAME", "test_exchange")

@pytest.fixture(scope="module")
def side_pots_module():
    return load_service_app_module(
        "game-service",
        "domain/engine/side_pots",
        package_name="game_sidepots_test_app",
        reload_modules=True,
    )

@pytest.fixture(scope="module")
def PlayerContribution(side_pots_module):
    return side_pots_module.PlayerContribution

@pytest.fixture(scope="module")
def calculate_side_pots(side_pots_module):
    return side_pots_module.calculate_side_pots

def _p(PlayerContribution, pid, committed, *, folded=False, showdown=True):
    return PlayerContribution(
        player_id=pid,
        committed_this_hand=committed,
        has_folded=folded,
        reached_showdown=showdown if not folded else False,
    )

@pytest.mark.unit
class TestBasicCases:
    def test_empty_input(self, calculate_side_pots):
        assert calculate_side_pots([]) == []

    def test_single_player_wins_everything(self, calculate_side_pots, PlayerContribution):
        players = [
            _p(PlayerContribution, "A", 100, showdown=True),
        ]
        pots = calculate_side_pots(players)
        assert len(pots) == 1
        assert pots[0].amount == 100
        assert pots[0].eligible_winner_player_ids == ("A",)

    def test_two_equal_stacks_no_side_pot(self, calculate_side_pots, PlayerContribution):
        players = [
            _p(PlayerContribution, "A", 200),
            _p(PlayerContribution, "B", 200),
        ]
        pots = calculate_side_pots(players)
        assert len(pots) == 1
        assert pots[0].pot_index == 0
        assert pots[0].amount == 400
        assert set(pots[0].contributor_player_ids) == {"A", "B"}
        assert set(pots[0].eligible_winner_player_ids) == {"A", "B"}

@pytest.mark.unit
class TestTwoPlayer:
    def test_heads_up_all_in_unequal(self, calculate_side_pots, PlayerContribution):
        players = [
            _p(PlayerContribution, "A", 100),
            _p(PlayerContribution, "B", 300),
        ]
        pots = calculate_side_pots(players)
        assert len(pots) == 2

        assert pots[0].amount == 200
        assert set(pots[0].eligible_winner_player_ids) == {"A", "B"}

        assert pots[1].amount == 200
        assert pots[1].eligible_winner_player_ids == ("B",)

    def test_heads_up_one_folds(self, calculate_side_pots, PlayerContribution):
        players = [
            _p(PlayerContribution, "A", 50, folded=True),
            _p(PlayerContribution, "B", 100, showdown=True),
        ]
        pots = calculate_side_pots(players)
        assert len(pots) == 2
        assert pots[0].amount == 100
        assert set(pots[0].contributor_player_ids) == {"A", "B"}
        assert pots[0].eligible_winner_player_ids == ("B",)

        assert pots[1].amount == 50
        assert pots[1].contributor_player_ids == ("B",)
        assert pots[1].eligible_winner_player_ids == ("B",)

        assert sum(p.amount for p in pots) == 150

@pytest.mark.unit
class TestThreePlayer:
    def test_three_players_all_equal(self, calculate_side_pots, PlayerContribution):
        players = [
            _p(PlayerContribution, "A", 100),
            _p(PlayerContribution, "B", 100),
            _p(PlayerContribution, "C", 100),
        ]
        pots = calculate_side_pots(players)
        assert len(pots) == 1
        assert pots[0].amount == 300
        assert set(pots[0].eligible_winner_player_ids) == {"A", "B", "C"}

    def test_three_players_one_short_all_in(self, calculate_side_pots, PlayerContribution):
        players = [
            _p(PlayerContribution, "A", 50),
            _p(PlayerContribution, "B", 200),
            _p(PlayerContribution, "C", 200),
        ]
        pots = calculate_side_pots(players)
        assert len(pots) == 2

        assert pots[0].amount == 150
        assert set(pots[0].eligible_winner_player_ids) == {"A", "B", "C"}

        assert pots[1].amount == 300
        assert set(pots[1].eligible_winner_player_ids) == {"B", "C"}

    def test_three_players_all_different_stacks(self, calculate_side_pots, PlayerContribution):
        players = [
            _p(PlayerContribution, "A", 30),
            _p(PlayerContribution, "B", 80),
            _p(PlayerContribution, "C", 200),
        ]
        pots = calculate_side_pots(players)
        assert len(pots) == 3

        assert pots[0].amount == 90
        assert set(pots[0].eligible_winner_player_ids) == {"A", "B", "C"}

        assert pots[1].amount == 100
        assert set(pots[1].eligible_winner_player_ids) == {"B", "C"}

        assert pots[2].amount == 120
        assert pots[2].eligible_winner_player_ids == ("C",)

    def test_three_players_one_folded(self, calculate_side_pots, PlayerContribution):
        players = [
            _p(PlayerContribution, "A", 40, folded=True),
            _p(PlayerContribution, "B", 100),
            _p(PlayerContribution, "C", 100),
        ]
        pots = calculate_side_pots(players)
        assert len(pots) == 2

        assert pots[0].amount == 120
        assert set(pots[0].contributor_player_ids) == {"A", "B", "C"}
        assert set(pots[0].eligible_winner_player_ids) == {"B", "C"}

        assert pots[1].amount == 120
        assert set(pots[1].contributor_player_ids) == {"B", "C"}
        assert set(pots[1].eligible_winner_player_ids) == {"B", "C"}

    def test_three_players_short_stack_folds(self, calculate_side_pots, PlayerContribution):
        players = [
            _p(PlayerContribution, "A", 20, folded=True),
            _p(PlayerContribution, "B", 50),
            _p(PlayerContribution, "C", 100),
        ]
        pots = calculate_side_pots(players)
        assert len(pots) == 3

        assert pots[0].amount == 60
        assert set(pots[0].eligible_winner_player_ids) == {"B", "C"}

        assert pots[1].amount == 60
        assert set(pots[1].eligible_winner_player_ids) == {"B", "C"}

        assert pots[2].amount == 50
        assert pots[2].eligible_winner_player_ids == ("C",)

        assert sum(p.amount for p in pots) == 170

@pytest.mark.unit
class TestFourPlayer:
    def test_four_players_cascading_all_ins(self, calculate_side_pots, PlayerContribution):
        players = [
            _p(PlayerContribution, "A", 25),
            _p(PlayerContribution, "B", 50),
            _p(PlayerContribution, "C", 100),
            _p(PlayerContribution, "D", 100),
        ]
        pots = calculate_side_pots(players)
        assert len(pots) == 3

        assert pots[0].amount == 100
        assert set(pots[0].eligible_winner_player_ids) == {"A", "B", "C", "D"}

        assert pots[1].amount == 75
        assert set(pots[1].eligible_winner_player_ids) == {"B", "C", "D"}

        assert pots[2].amount == 100
        assert set(pots[2].eligible_winner_player_ids) == {"C", "D"}

        assert sum(p.amount for p in pots) == 275

    def test_four_players_two_fold_two_showdown(self, calculate_side_pots, PlayerContribution):
        players = [
            _p(PlayerContribution, "A", 10, folded=True),
            _p(PlayerContribution, "B", 30, folded=True),
            _p(PlayerContribution, "C", 200),
            _p(PlayerContribution, "D", 200),
        ]
        pots = calculate_side_pots(players)

        total = sum(p.amount for p in pots)
        assert total == 440

        for pot in pots:
            assert set(pot.eligible_winner_player_ids) == {"C", "D"}

    def test_four_players_fold_then_allin(self, calculate_side_pots, PlayerContribution):
        players = [
            _p(PlayerContribution, "A", 20, folded=True),
            _p(PlayerContribution, "B", 60),
            _p(PlayerContribution, "C", 150),
            _p(PlayerContribution, "D", 150),
        ]
        pots = calculate_side_pots(players)
        assert len(pots) == 3

        assert pots[0].amount == 80
        assert set(pots[0].eligible_winner_player_ids) == {"B", "C", "D"}

        assert pots[1].amount == 120
        assert set(pots[1].eligible_winner_player_ids) == {"B", "C", "D"}

        assert pots[2].amount == 180
        assert set(pots[2].eligible_winner_player_ids) == {"C", "D"}

        assert sum(p.amount for p in pots) == 380

    def test_four_players_identical_commitments(self, calculate_side_pots, PlayerContribution):
        players = [
            _p(PlayerContribution, "A", 100),
            _p(PlayerContribution, "B", 100),
            _p(PlayerContribution, "C", 100),
            _p(PlayerContribution, "D", 100),
        ]
        pots = calculate_side_pots(players)
        assert len(pots) == 1
        assert pots[0].amount == 400
        assert set(pots[0].eligible_winner_player_ids) == {"A", "B", "C", "D"}

@pytest.mark.unit
class TestDeadPotMerging:
    def test_all_players_fold(self, calculate_side_pots, PlayerContribution):
        players = [
            _p(PlayerContribution, "A", 10, folded=True),
            _p(PlayerContribution, "B", 20, folded=True),
        ]
        pots = calculate_side_pots(players)
        assert len(pots) == 1
        assert pots[0].amount == 30
        assert pots[0].eligible_winner_player_ids == ()

    def test_folded_only_tier_merges_forward(self, calculate_side_pots, PlayerContribution):
        players = [
            _p(PlayerContribution, "A", 10, folded=True),
            _p(PlayerContribution, "B", 50),
            _p(PlayerContribution, "C", 50),
        ]
        pots = calculate_side_pots(players)
        total = sum(p.amount for p in pots)
        assert total == 110

    def test_middle_tier_all_fold(self, calculate_side_pots, PlayerContribution):
        players = [
            _p(PlayerContribution, "A", 10),
            _p(PlayerContribution, "B", 30, folded=True),
            _p(PlayerContribution, "C", 100),
        ]
        pots = calculate_side_pots(players)
        assert sum(p.amount for p in pots) == 140
        assert len(pots) == 3

@pytest.mark.unit
class TestChipConservation:
    def test_conservation_simple(self, calculate_side_pots, PlayerContribution):
        players = [
            _p(PlayerContribution, "A", 100),
            _p(PlayerContribution, "B", 200),
            _p(PlayerContribution, "C", 300),
        ]
        pots = calculate_side_pots(players)
        assert sum(p.amount for p in pots) == 600

    def test_conservation_with_folds(self, calculate_side_pots, PlayerContribution):
        players = [
            _p(PlayerContribution, "A", 10, folded=True),
            _p(PlayerContribution, "B", 25, folded=True),
            _p(PlayerContribution, "C", 50),
            _p(PlayerContribution, "D", 50),
        ]
        pots = calculate_side_pots(players)
        assert sum(p.amount for p in pots) == 135

    def test_conservation_complex(self, calculate_side_pots, PlayerContribution):
        players = [
            _p(PlayerContribution, "A", 5, folded=True),
            _p(PlayerContribution, "B", 15),
            _p(PlayerContribution, "C", 40),
            _p(PlayerContribution, "D", 100),
            _p(PlayerContribution, "E", 100),
        ]
        pots = calculate_side_pots(players)
        assert sum(p.amount for p in pots) == 260

@pytest.mark.unit
class TestPotOrdering:
    def test_pot_indices_are_sequential(self, calculate_side_pots, PlayerContribution):
        players = [
            _p(PlayerContribution, "A", 10),
            _p(PlayerContribution, "B", 50),
            _p(PlayerContribution, "C", 200),
            _p(PlayerContribution, "D", 200),
        ]
        pots = calculate_side_pots(players)
        for i, pot in enumerate(pots):
            assert pot.pot_index == i

    def test_main_pot_is_largest_contributor_group(self, calculate_side_pots, PlayerContribution):
        players = [
            _p(PlayerContribution, "A", 10),
            _p(PlayerContribution, "B", 50),
            _p(PlayerContribution, "C", 100),
        ]
        pots = calculate_side_pots(players)
        assert len(pots[0].contributor_player_ids) >= len(pots[-1].contributor_player_ids)

@pytest.mark.unit
class TestZeroCommitment:
    def test_zero_commitment_player_excluded_from_pots(self, calculate_side_pots, PlayerContribution):
        players = [
            _p(PlayerContribution, "A", 0, folded=True),
            _p(PlayerContribution, "B", 100),
            _p(PlayerContribution, "C", 100),
        ]
        pots = calculate_side_pots(players)
        assert len(pots) == 1
        assert pots[0].amount == 200
        assert "A" not in pots[0].contributor_player_ids

    def test_all_zero(self, calculate_side_pots, PlayerContribution):
        players = [
            _p(PlayerContribution, "A", 0, folded=True),
            _p(PlayerContribution, "B", 0, folded=True),
        ]
        pots = calculate_side_pots(players)
        assert pots == []

@pytest.mark.unit
class TestRealisticHand:
    def test_full_hand_scenario(self, calculate_side_pots, PlayerContribution):
        players = [
            _p(PlayerContribution, "P1", 5, folded=True),
            _p(PlayerContribution, "P2", 40),
            _p(PlayerContribution, "P3", 200),
            _p(PlayerContribution, "P4", 25),
            _p(PlayerContribution, "P5", 40, folded=True),
            _p(PlayerContribution, "P6", 200),
        ]
        pots = calculate_side_pots(players)

        total = sum(p.amount for p in pots)
        assert total == 510

        assert len(pots[0].contributor_player_ids) == 6

        p4_eligible_pots = [p for p in pots if "P4" in p.eligible_winner_player_ids]
        assert len(p4_eligible_pots) >= 1

        for pot in pots:
            assert "P1" not in pot.eligible_winner_player_ids
            assert "P5" not in pot.eligible_winner_player_ids

        assert set(pots[-1].eligible_winner_player_ids) == {"P3", "P6"}