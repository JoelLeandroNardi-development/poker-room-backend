"""Tests for the hand replay engine, settlement explainer, and hand history timeline.

Covers:
- Hand replay step-by-step correctness
- Replay consistency verification
- Settlement explanation with single/multiple pots
- Settlement narrative generation
- Hand history timeline construction
- Corrections in replays and timelines
"""

from __future__ import annotations

import os

import pytest

from tests.service_loader import load_service_app_module

os.environ.setdefault("GAME_DB", "sqlite+aiosqlite:///:memory:")
os.environ.setdefault("RABBIT_URL", "amqp://guest:guest@localhost:5672/")
os.environ.setdefault("EXCHANGE_NAME", "test_exchange")


# ── Module fixtures ──────────────────────────────────────────────────

@pytest.fixture(scope="module")
def replay_mod():
    return load_service_app_module(
        "game-service", "domain/hand_replay",
        package_name="engine_test_app", reload_modules=True,
    )


@pytest.fixture(scope="module")
def explainer_mod():
    return load_service_app_module(
        "game-service", "domain/settlement_explainer",
        package_name="engine_test_app",
    )


@pytest.fixture(scope="module")
def timeline_mod():
    return load_service_app_module(
        "game-service", "domain/hand_history",
        package_name="engine_test_app",
    )


@pytest.fixture(scope="module")
def ledger_mod():
    return load_service_app_module(
        "game-service", "domain/hand_ledger",
        package_name="engine_test_app",
    )


@pytest.fixture(scope="module")
def side_pots_mod():
    return load_service_app_module(
        "game-service", "domain/side_pots",
        package_name="engine_test_app",
    )


@pytest.fixture(scope="module")
def rules_mod():
    return load_service_app_module(
        "game-service", "domain/rules",
        package_name="engine_test_app",
    )


# ── Shortcut fixtures ───────────────────────────────────────────────

@pytest.fixture
def LedgerRow(ledger_mod):
    return ledger_mod.LedgerRow


@pytest.fixture
def replay_hand(replay_mod):
    return replay_mod.replay_hand


@pytest.fixture
def verify_consistency(replay_mod):
    return replay_mod.verify_consistency


@pytest.fixture
def explain_settlement(explainer_mod):
    return explainer_mod.explain_settlement


@pytest.fixture
def PlayerContribution(side_pots_mod):
    return side_pots_mod.PlayerContribution


@pytest.fixture
def build_hand_timeline(timeline_mod):
    return timeline_mod.build_hand_timeline


# ── Helpers ──────────────────────────────────────────────────────────

def _ledger(LedgerRow, entry_id, entry_type, player_id=None, amount=None,
            detail=None, original_entry_id=None):
    return LedgerRow(
        entry_id=entry_id,
        entry_type=entry_type,
        player_id=player_id,
        amount=amount,
        detail=detail,
        original_entry_id=original_entry_id,
    )


# ═══════════════════════════════════════════════════════════════════════
#  Hand Replay Engine
# ═══════════════════════════════════════════════════════════════════════

class TestHandReplay:
    """Step-by-step replay of a hand from ledger entries."""

    def test_empty_entries(self, replay_hand, LedgerRow):
        result = replay_hand([])
        assert result.entry_count == 0
        assert result.steps == []
        assert result.final_state.pot_total == 0

    def test_single_blind(self, replay_hand, LedgerRow):
        entries = [
            _ledger(LedgerRow, "e1", "BLIND_POSTED", "p1", 50),
        ]
        result = replay_hand(entries)
        assert result.entry_count == 1
        assert len(result.steps) == 1
        step = result.steps[0]
        assert step.step_number == 1
        assert step.entry_id == "e1"
        assert step.state_after.pot_total == 50
        assert result.final_state.pot_total == 50

    def test_full_pre_flop_replay(self, replay_hand, LedgerRow):
        """Blinds → bet → call → round complete."""
        entries = [
            _ledger(LedgerRow, "e1", "BLIND_POSTED", "p1", 50),
            _ledger(LedgerRow, "e2", "BLIND_POSTED", "p2", 100),
            _ledger(LedgerRow, "e3", "BET_PLACED", "p3", 100),   # call
            _ledger(LedgerRow, "e4", "BET_PLACED", "p1", 50),    # SB completes
            _ledger(LedgerRow, "e5", "ROUND_COMPLETED", None, None),
        ]
        result = replay_hand(entries)
        assert result.entry_count == 5
        assert len(result.steps) == 5

        # Check intermediate states
        assert result.steps[0].state_after.pot_total == 50
        assert result.steps[1].state_after.pot_total == 150
        assert result.steps[2].state_after.pot_total == 250
        assert result.steps[3].state_after.pot_total == 300
        assert result.steps[4].state_after.is_completed is True

        # Final
        assert result.final_state.pot_total == 300
        assert result.final_state.is_completed is True
        assert result.final_state.players["p1"].total_committed == 100
        assert result.final_state.players["p2"].total_committed == 100
        assert result.final_state.players["p3"].total_committed == 100

    def test_replay_with_payouts(self, replay_hand, LedgerRow):
        entries = [
            _ledger(LedgerRow, "e1", "BLIND_POSTED", "p1", 50),
            _ledger(LedgerRow, "e2", "BLIND_POSTED", "p2", 100),
            _ledger(LedgerRow, "e3", "BET_PLACED", "p1", 50),
            _ledger(LedgerRow, "e4", "PAYOUT_AWARDED", "p2", 200),
            _ledger(LedgerRow, "e5", "ROUND_COMPLETED", None, None),
        ]
        result = replay_hand(entries)
        assert result.final_state.players["p2"].total_won == 200
        assert result.final_state.pot_total == 200
        assert result.final_state.is_completed is True

    def test_replay_with_correction(self, replay_hand, LedgerRow):
        entries = [
            _ledger(LedgerRow, "e1", "BLIND_POSTED", "p1", 50),
            _ledger(LedgerRow, "e2", "BLIND_POSTED", "p2", 100),
            _ledger(LedgerRow, "e3", "BET_PLACED", "p1", 50),
            _ledger(LedgerRow, "e4", "ROUND_COMPLETED", None, None),
            _ledger(LedgerRow, "e5", "HAND_REOPENED", None, None),
            _ledger(LedgerRow, "e6", "ACTION_REVERSED", "p1", 50, original_entry_id="e3"),
        ]
        result = replay_hand(entries)
        assert result.final_state.is_reopened is True
        assert result.final_state.is_completed is False
        assert "e3" in result.final_state.reversed_entry_ids
        assert result.final_state.pot_total == 150  # (50 + 100 + 50) - 50 reversed

        # Step-by-step check
        assert result.steps[3].state_after.is_completed is True
        assert result.steps[4].state_after.is_completed is False
        assert result.steps[4].state_after.is_reopened is True


class TestVerifyConsistency:
    """Verify replayed state matches live projection."""

    def test_consistent_state(self, verify_consistency, LedgerRow):
        entries = [
            _ledger(LedgerRow, "e1", "BLIND_POSTED", "p1", 50),
            _ledger(LedgerRow, "e2", "BLIND_POSTED", "p2", 100),
        ]
        discrepancies = verify_consistency(
            entries, live_pot_total=150,
            live_player_committed={"p1": 50, "p2": 100},
        )
        assert discrepancies == []

    def test_pot_mismatch(self, verify_consistency, LedgerRow):
        entries = [
            _ledger(LedgerRow, "e1", "BLIND_POSTED", "p1", 50),
            _ledger(LedgerRow, "e2", "BLIND_POSTED", "p2", 100),
        ]
        discrepancies = verify_consistency(
            entries, live_pot_total=999,
            live_player_committed={"p1": 50, "p2": 100},
        )
        assert len(discrepancies) == 1
        assert "Pot mismatch" in discrepancies[0]

    def test_player_committed_mismatch(self, verify_consistency, LedgerRow):
        entries = [
            _ledger(LedgerRow, "e1", "BLIND_POSTED", "p1", 50),
            _ledger(LedgerRow, "e2", "BLIND_POSTED", "p2", 100),
        ]
        discrepancies = verify_consistency(
            entries, live_pot_total=150,
            live_player_committed={"p1": 999, "p2": 100},
        )
        assert len(discrepancies) == 1
        assert "p1" in discrepancies[0]

    def test_extra_player_in_live(self, verify_consistency, LedgerRow):
        entries = [
            _ledger(LedgerRow, "e1", "BLIND_POSTED", "p1", 50),
        ]
        discrepancies = verify_consistency(
            entries, live_pot_total=50,
            live_player_committed={"p1": 50, "p_phantom": 0},
        )
        assert any("p_phantom" in d for d in discrepancies)

    def test_extra_player_in_replay(self, verify_consistency, LedgerRow):
        entries = [
            _ledger(LedgerRow, "e1", "BLIND_POSTED", "p1", 50),
            _ledger(LedgerRow, "e2", "BLIND_POSTED", "p2", 100),
        ]
        discrepancies = verify_consistency(
            entries, live_pot_total=150,
            live_player_committed={"p1": 50},
        )
        assert any("p2" in d for d in discrepancies)


# ═══════════════════════════════════════════════════════════════════════
#  Settlement Explanation Engine
# ═══════════════════════════════════════════════════════════════════════

class TestSettlementExplainer:
    """Structured settlement explanation with narrative."""

    def test_single_pot_no_payouts(self, explain_settlement, PlayerContribution):
        contributions = [
            PlayerContribution("p1", 100, False, True),
            PlayerContribution("p2", 100, True, False),
        ]
        result = explain_settlement(contributions)

        assert result.total_pot == 200
        assert len(result.pots) == 1
        assert result.pots[0].pot_label == "Main Pot"
        assert result.pots[0].amount == 200
        assert "p1" in result.pots[0].eligible_player_ids
        assert "p2" not in result.pots[0].eligible_player_ids
        assert result.pots[0].ineligible_reasons["p2"] == "folded"
        assert result.total_awarded == 0

    def test_single_pot_with_payouts(self, explain_settlement, PlayerContribution):
        contributions = [
            PlayerContribution("p1", 100, False, True),
            PlayerContribution("p2", 100, True, False),
        ]
        payouts = [{"pot_index": 0, "winners": [{"player_id": "p1", "amount": 200}]}]
        result = explain_settlement(contributions, payouts)

        assert result.total_awarded == 200
        assert result.total_unclaimed == 0
        assert result.pots[0].winners[0].player_id == "p1"
        assert result.pots[0].winners[0].amount == 200

    def test_side_pot_structure(self, explain_settlement, PlayerContribution):
        """3 players, one all-in short → creates main + side pot."""
        contributions = [
            PlayerContribution("p1", 50, False, True),    # short all-in
            PlayerContribution("p2", 200, False, True),
            PlayerContribution("p3", 200, True, False),   # folded
        ]
        payouts = [
            {"pot_index": 0, "winners": [{"player_id": "p1", "amount": 150}]},
            {"pot_index": 1, "winners": [{"player_id": "p2", "amount": 300}]},
        ]
        result = explain_settlement(contributions, payouts)

        assert len(result.pots) == 2
        assert result.pots[0].pot_label == "Main Pot"
        assert result.pots[1].pot_label == "Side Pot 1"
        assert result.total_awarded == 450
        assert "p3" in result.pots[0].ineligible_reasons

    def test_narrative_single_pot(self, explain_settlement, PlayerContribution):
        contributions = [
            PlayerContribution("p1", 100, False, True),
            PlayerContribution("p2", 100, False, True),
        ]
        result = explain_settlement(contributions)
        assert any("Total pot: 200" in line for line in result.narrative)
        assert any("Single pot" in line for line in result.narrative)

    def test_narrative_multiple_pots(self, explain_settlement, PlayerContribution):
        contributions = [
            PlayerContribution("p1", 50, False, True),
            PlayerContribution("p2", 200, False, True),
            PlayerContribution("p3", 200, False, True),
        ]
        result = explain_settlement(contributions)
        assert any("2 pots" in line for line in result.narrative)

    def test_dead_pot_narrative(self, explain_settlement, PlayerContribution):
        """All players fold — dead pot scenario."""
        contributions = [
            PlayerContribution("p1", 50, True, False),
            PlayerContribution("p2", 100, True, False),
        ]
        result = explain_settlement(contributions)
        assert result.total_pot == 150
        assert any("dead pot" in line.lower() for line in result.narrative)


# ═══════════════════════════════════════════════════════════════════════
#  Hand History Timeline
# ═══════════════════════════════════════════════════════════════════════

class TestHandTimeline:
    """Structured per-street timeline from ledger entries."""

    def test_empty_entries(self, build_hand_timeline, LedgerRow):
        tl = build_hand_timeline("r1", [])
        assert tl.round_id == "r1"
        assert tl.total_entries == 0
        # Still has the implicit PRE_FLOP street
        assert len(tl.streets) == 1
        assert tl.streets[0].street == "PRE_FLOP"

    def test_blinds_only(self, build_hand_timeline, LedgerRow):
        entries = [
            _ledger(LedgerRow, "e1", "BLIND_POSTED", "p1", 50),
            _ledger(LedgerRow, "e2", "BLIND_POSTED", "p2", 100),
        ]
        tl = build_hand_timeline("r1", entries)
        assert len(tl.streets) == 1
        assert len(tl.streets[0].actions) == 2
        assert tl.streets[0].pot_at_end == 150

    def test_street_transition(self, build_hand_timeline, LedgerRow):
        """PRE_FLOP → FLOP transition."""
        entries = [
            _ledger(LedgerRow, "e1", "BLIND_POSTED", "p1", 50),
            _ledger(LedgerRow, "e2", "BLIND_POSTED", "p2", 100),
            _ledger(LedgerRow, "e3", "BET_PLACED", "p1", 50),
            _ledger(LedgerRow, "e4", "STREET_DEALT", None, None, detail={"street": "FLOP"}),
            _ledger(LedgerRow, "e5", "BET_PLACED", "p1", 100),
        ]
        tl = build_hand_timeline("r1", entries)
        assert len(tl.streets) == 2
        assert tl.streets[0].street == "PRE_FLOP"
        assert tl.streets[0].pot_at_end == 200
        assert tl.streets[1].street == "FLOP"
        assert tl.streets[1].pot_at_start == 200
        assert tl.streets[1].pot_at_end == 300

    def test_payouts_tracked(self, build_hand_timeline, LedgerRow):
        entries = [
            _ledger(LedgerRow, "e1", "BLIND_POSTED", "p1", 100),
            _ledger(LedgerRow, "e2", "BLIND_POSTED", "p2", 100),
            _ledger(LedgerRow, "e3", "PAYOUT_AWARDED", "p1", 200),
            _ledger(LedgerRow, "e4", "ROUND_COMPLETED", None, None),
        ]
        tl = build_hand_timeline("r1", entries)
        assert len(tl.payouts) == 1
        assert tl.payouts[0].player_id == "p1"
        assert tl.payouts[0].amount == 200
        assert tl.is_completed is True

    def test_corrections_tracked(self, build_hand_timeline, LedgerRow):
        entries = [
            _ledger(LedgerRow, "e1", "BLIND_POSTED", "p1", 50),
            _ledger(LedgerRow, "e2", "ROUND_COMPLETED", None, None),
            _ledger(LedgerRow, "e3", "HAND_REOPENED", None, None),
            _ledger(LedgerRow, "e4", "ACTION_REVERSED", "p1", 50, original_entry_id="e1"),
        ]
        tl = build_hand_timeline("r1", entries)
        assert tl.is_reopened is True
        assert tl.is_completed is False
        assert len(tl.corrections) == 2
        assert tl.corrections[0].correction_type == "HAND_REOPENED"
        assert tl.corrections[1].correction_type == "ACTION_REVERSED"
        assert tl.corrections[1].original_entry_id == "e1"

    def test_pot_running_totals(self, build_hand_timeline, LedgerRow):
        """Each action tracks a running pot total."""
        entries = [
            _ledger(LedgerRow, "e1", "BLIND_POSTED", "p1", 50),
            _ledger(LedgerRow, "e2", "BLIND_POSTED", "p2", 100),
            _ledger(LedgerRow, "e3", "BET_PLACED", "p3", 200),
        ]
        tl = build_hand_timeline("r1", entries)
        actions = tl.streets[0].actions
        assert actions[0].pot_running_total == 50
        assert actions[1].pot_running_total == 150
        assert actions[2].pot_running_total == 350

    def test_multi_street_full_hand(self, build_hand_timeline, LedgerRow):
        """PRE_FLOP → FLOP → TURN → RIVER with actions on each street."""
        entries = [
            _ledger(LedgerRow, "e1", "BLIND_POSTED", "p1", 50),
            _ledger(LedgerRow, "e2", "BLIND_POSTED", "p2", 100),
            _ledger(LedgerRow, "e3", "STREET_DEALT", None, None, detail={"street": "FLOP"}),
            _ledger(LedgerRow, "e4", "BET_PLACED", "p1", 100),
            _ledger(LedgerRow, "e5", "BET_PLACED", "p2", 100),
            _ledger(LedgerRow, "e6", "STREET_DEALT", None, None, detail={"street": "TURN"}),
            _ledger(LedgerRow, "e7", "BET_PLACED", "p1", 200),
            _ledger(LedgerRow, "e8", "STREET_DEALT", None, None, detail={"street": "RIVER"}),
            _ledger(LedgerRow, "e9", "PAYOUT_AWARDED", "p1", 550),
            _ledger(LedgerRow, "e10", "ROUND_COMPLETED", None, None),
        ]
        tl = build_hand_timeline("r1", entries)
        assert len(tl.streets) == 4
        assert tl.streets[0].street == "PRE_FLOP"
        assert tl.streets[1].street == "FLOP"
        assert tl.streets[2].street == "TURN"
        assert tl.streets[3].street == "RIVER"
        assert tl.is_completed is True
        assert len(tl.payouts) == 1


# ═══════════════════════════════════════════════════════════════════════
#  Rules Profile
# ═══════════════════════════════════════════════════════════════════════

class TestRulesProfile:
    """Verify the pre-built rules profile."""

    def test_nlhe_profile_exists(self, rules_mod):
        profile = rules_mod.NO_LIMIT_HOLDEM
        assert profile.name == "No-Limit Texas Hold'em"
        assert profile.betting_structure == "no_limit"
        assert profile.forced_bets == "blinds"
        assert profile.min_players == 2
        assert profile.max_players == 10
        assert len(profile.streets) == 5
        assert profile.unlimited_raises is True
        assert profile.engine_version == "0.15.0"

    def test_rules_profile_is_frozen(self, rules_mod):
        import dataclasses
        profile = rules_mod.NO_LIMIT_HOLDEM
        assert dataclasses.is_dataclass(profile)
        with pytest.raises(AttributeError):
            profile.name = "something else"
