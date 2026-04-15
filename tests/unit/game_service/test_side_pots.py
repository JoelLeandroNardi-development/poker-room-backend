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
        "domain/side_pots",
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
    """Shorthand for building a PlayerContribution."""
    return PlayerContribution(
        player_id=pid,
        committed_this_hand=committed,
        has_folded=folded,
        reached_showdown=showdown if not folded else False,
    )


# ================================================================
# Basic / degenerate cases
# ================================================================


@pytest.mark.unit
class TestBasicCases:
    def test_empty_input(self, calculate_side_pots):
        assert calculate_side_pots([]) == []

    def test_single_player_wins_everything(self, calculate_side_pots, PlayerContribution):
        """Everyone else folded pre-flop; one player left."""
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


# ================================================================
# 2-player scenarios
# ================================================================


@pytest.mark.unit
class TestTwoPlayer:
    def test_heads_up_all_in_unequal(self, calculate_side_pots, PlayerContribution):
        """A all-in for 100, B calls but committed 300 (excess returned conceptually)."""
        # In practice commitments should match, but if B over-committed:
        # Pot 1: 100 * 2 = 200  (A and B eligible)
        # Pot 2: 200 * 1 = 200  (only B eligible — A couldn't reach this tier)
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
        # A folded after committing 50; B committed 100.
        # Tier 1 (0→50):  contributors=A,B  slice=50*2=100  eligible=B
        # Tier 2 (50→100): contributors=B   slice=50*1=50   eligible=B
        # Both tiers have eligible winners → 2 separate pots
        assert len(pots) == 2
        assert pots[0].amount == 100
        assert set(pots[0].contributor_player_ids) == {"A", "B"}
        assert pots[0].eligible_winner_player_ids == ("B",)

        assert pots[1].amount == 50
        assert pots[1].contributor_player_ids == ("B",)
        assert pots[1].eligible_winner_player_ids == ("B",)

        assert sum(p.amount for p in pots) == 150


# ================================================================
# 3-player scenarios
# ================================================================


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
        """
        A all-in 50, B and C call 200 each.

        Main pot:  50 * 3 = 150   (A, B, C eligible)
        Side pot: 150 * 2 = 300   (B, C eligible)
        Total chips: 50 + 200 + 200 = 450  ✓
        """
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
        """
        A all-in 30, B all-in 80, C calls 200.

        Main pot:   30 * 3 = 90    (A, B, C eligible)
        Side pot 1: 50 * 2 = 100   (B, C eligible)
        Side pot 2: 120 * 1 = 120  (C eligible)
        Total: 30 + 80 + 200 = 310  ✓
        """
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
        """
        A folds after committing 40, B and C showdown at 100 each.

        Tier 1: 40 * 3 = 120  (B, C eligible — A folded)
        Tier 2: 60 * 2 = 120  (B, C eligible)
        → merged into 1 pot: 240  (B, C eligible)  since both tiers share same eligible set
        Actually, tier 1 has eligible {B,C} and tier 2 has eligible {B,C}, but they
        are separate pots in the raw calculation, then merged because tier 1 already
        has eligible winners. Let me re-check the algorithm...
        
        Tier 1: previous=0, level=40 → contributors = A,B,C → slice = 40*3=120
                 eligible = B, C (A folded)
        Tier 2: previous=40, level=100 → contributors with committed > 40 = B, C
                 slice = 60*2=120, eligible = B, C
        
        Both have eligible winners, so no merging needed → 2 pots.
        """
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
        """
        A folds after 20, B all-in 50, C calls 100.

        Tier 1 (0→20): contributors=A,B,C  slice=20*3=60   eligible=B,C
        Tier 2 (20→50): contributors=B,C   slice=30*2=60   eligible=B,C
        Tier 3 (50→100): contributors=C    slice=50*1=50   eligible=C only
        Total: 20+50+100 = 170 ✓
        """
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


# ================================================================
# 4-player scenarios
# ================================================================


@pytest.mark.unit
class TestFourPlayer:
    def test_four_players_cascading_all_ins(self, calculate_side_pots, PlayerContribution):
        """
        A all-in 25, B all-in 50, C all-in 100, D calls 100.

        Tier 1 (0→25):  4 contributors → 25*4 = 100   (A,B,C,D eligible)
        Tier 2 (25→50): 3 contributors → 25*3 = 75    (B,C,D eligible)
        Tier 3 (50→100): 2 contributors → 50*2 = 100  (C,D eligible)
        Total: 25+50+100+100 = 275  ✓
        """
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
        """
        A folds after 10, B folds after 30, C and D showdown at 200.

        Tier 1 (0→10):    contributors=A,B,C,D  slice=10*4=40   eligible=C,D
        Tier 2 (10→30):   contributors=B,C,D    slice=20*3=60   eligible=C,D
        Tier 3 (30→200):  contributors=C,D      slice=170*2=340 eligible=C,D
        Total: 10+30+200+200 = 440  ✓
        """
        players = [
            _p(PlayerContribution, "A", 10, folded=True),
            _p(PlayerContribution, "B", 30, folded=True),
            _p(PlayerContribution, "C", 200),
            _p(PlayerContribution, "D", 200),
        ]
        pots = calculate_side_pots(players)

        total = sum(p.amount for p in pots)
        assert total == 440

        # All pots should only have C,D as eligible winners
        for pot in pots:
            assert set(pot.eligible_winner_player_ids) == {"C", "D"}

    def test_four_players_fold_then_allin(self, calculate_side_pots, PlayerContribution):
        """
        A folds after 20, B all-in 60, C all-in 150, D calls 150.

        Tier 1 (0→20):    contributors=A,B,C,D  slice=20*4=80   eligible=B,C,D
        Tier 2 (20→60):   contributors=B,C,D    slice=40*3=120  eligible=B,C,D
        Tier 3 (60→150):  contributors=C,D      slice=90*2=180  eligible=C,D
        Total: 20+60+150+150 = 380  ✓
        """
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


# ================================================================
# Dead-pot merging
# ================================================================


@pytest.mark.unit
class TestDeadPotMerging:
    def test_all_players_fold(self, calculate_side_pots, PlayerContribution):
        """Edge case: everyone folded. Chips are dead."""
        players = [
            _p(PlayerContribution, "A", 10, folded=True),
            _p(PlayerContribution, "B", 20, folded=True),
        ]
        pots = calculate_side_pots(players)
        # All chips, no eligible winner
        assert len(pots) == 1
        assert pots[0].amount == 30
        assert pots[0].eligible_winner_player_ids == ()

    def test_folded_only_tier_merges_forward(self, calculate_side_pots, PlayerContribution):
        """
        A folds after 10 (only contributor to tier 1 who then folds).
        B and C showdown at 50.

        Tier 1 (0→10): contributors=A,B,C  eligible=B,C  ← has eligible, kept
        Tier 2 (10→50): contributors=B,C   eligible=B,C
        """
        players = [
            _p(PlayerContribution, "A", 10, folded=True),
            _p(PlayerContribution, "B", 50),
            _p(PlayerContribution, "C", 50),
        ]
        pots = calculate_side_pots(players)
        total = sum(p.amount for p in pots)
        assert total == 110

    def test_middle_tier_all_fold(self, calculate_side_pots, PlayerContribution):
        """
        A all-in 10 (showdown), B folds at 30, C showdown 100.

        Tier 1 (0→10):  contrib=A,B,C   eligible=A,C   → kept (has eligible)
        Tier 2 (10→30): contrib=B,C     eligible=C     → kept (has eligible)
        Tier 3 (30→100): contrib=C      eligible=C     → kept
        """
        players = [
            _p(PlayerContribution, "A", 10),
            _p(PlayerContribution, "B", 30, folded=True),
            _p(PlayerContribution, "C", 100),
        ]
        pots = calculate_side_pots(players)
        assert sum(p.amount for p in pots) == 140
        assert len(pots) == 3


# ================================================================
# Chip conservation (invariant tests)
# ================================================================


@pytest.mark.unit
class TestChipConservation:
    """The sum of all pot amounts must always equal the sum of all commitments."""

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


# ================================================================
# Pot index ordering
# ================================================================


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
        """The main pot (index 0) should have the most contributors."""
        players = [
            _p(PlayerContribution, "A", 10),
            _p(PlayerContribution, "B", 50),
            _p(PlayerContribution, "C", 100),
        ]
        pots = calculate_side_pots(players)
        assert len(pots[0].contributor_player_ids) >= len(pots[-1].contributor_player_ids)


# ================================================================
# Zero-commitment player
# ================================================================


@pytest.mark.unit
class TestZeroCommitment:
    def test_zero_commitment_player_excluded_from_pots(self, calculate_side_pots, PlayerContribution):
        """A player who committed 0 (e.g. posted nothing, sat out) should not affect pots."""
        players = [
            _p(PlayerContribution, "A", 0, folded=True),
            _p(PlayerContribution, "B", 100),
            _p(PlayerContribution, "C", 100),
        ]
        pots = calculate_side_pots(players)
        assert len(pots) == 1
        assert pots[0].amount == 200
        # A contributed nothing so shouldn't appear as contributor at the 100-level tier
        assert "A" not in pots[0].contributor_player_ids

    def test_all_zero(self, calculate_side_pots, PlayerContribution):
        players = [
            _p(PlayerContribution, "A", 0, folded=True),
            _p(PlayerContribution, "B", 0, folded=True),
        ]
        pots = calculate_side_pots(players)
        assert pots == []


# ================================================================
# Realistic hand scenario
# ================================================================


@pytest.mark.unit
class TestRealisticHand:
    def test_full_hand_scenario(self, calculate_side_pots, PlayerContribution):
        """
        6-player hand:
        - P1 folds pre-flop after posting SB of 5
        - P2 posts BB 10, calls a raise to 40
        - P3 raises to 40, calls all streets, committed 200 total
        - P4 all-in pre-flop for 25
        - P5 folds on the flop after committing 40
        - P6 calls all streets, committed 200

        Tier 1 (0→5):   contributors=P1,P2,P3,P4,P5,P6  slice=5*6=30    eligible=P2,P3,P6
        Tier 2 (5→25):  contributors=P2,P3,P4,P5,P6      slice=20*5=100  eligible=P2,P3,P4,P6
        Tier 3 (25→40): contributors=P2,P3,P5,P6          slice=15*4=60   eligible=P2,P3,P6
        Tier 4 (40→200):contributors=P3,P6                slice=160*2=320 eligible=P3,P6
        Total: 5+40+200+25+40+200 = 510 ✓
        """
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

        # Main pot should include all 6 as contributors
        assert len(pots[0].contributor_player_ids) == 6

        # P4 (all-in 25) should be eligible in pots covering tiers up to 25
        p4_eligible_pots = [p for p in pots if "P4" in p.eligible_winner_player_ids]
        assert len(p4_eligible_pots) >= 1

        # P1 and P5 folded — never eligible
        for pot in pots:
            assert "P1" not in pot.eligible_winner_player_ids
            assert "P5" not in pot.eligible_winner_player_ids

        # The last pot should only be eligible for P3 and P6
        assert set(pots[-1].eligible_winner_player_ids) == {"P3", "P6"}
