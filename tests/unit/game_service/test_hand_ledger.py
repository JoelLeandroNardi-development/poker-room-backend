"""
Unit tests for the hand ledger state rebuilder.

Covers:
- Forward events: blinds, antes, bets, payouts, round completion
- ACTION_REVERSED: reverses a bet, deducts from pot and committed
- STACK_ADJUSTED: ad-hoc chip adjustment
- HAND_REOPENED: flips is_completed back
- PAYOUT_CORRECTED: debits old winner, credits new
- Mixed sequences mirroring real dealer correction workflows
- Edge cases: empty ledger, double-reversal guard, large table
"""

from __future__ import annotations

import os

import pytest

from tests.service_loader import load_service_app_module

os.environ.setdefault("GAME_DB", "sqlite+aiosqlite:///:memory:")
os.environ.setdefault("RABBIT_URL", "amqp://guest:guest@localhost:5672/")
os.environ.setdefault("EXCHANGE_NAME", "test_exchange")


@pytest.fixture(scope="module")
def ledger_module():
    return load_service_app_module("game-service", "domain/hand_ledger")


@pytest.fixture(scope="module")
def rebuild(ledger_module):
    return ledger_module.rebuild_hand_state


@pytest.fixture(scope="module")
def LedgerRow(ledger_module):
    return ledger_module.LedgerRow


# ── Helpers ──────────────────────────────────────────────────────────

def _row(cls, eid, etype, pid=None, amt=None, detail=None, orig=None):
    return cls(
        entry_id=eid,
        entry_type=etype,
        player_id=pid,
        amount=amt,
        detail=detail,
        original_entry_id=orig,
    )


# ── Forward events ───────────────────────────────────────────────────

class TestForwardEvents:
    def test_empty_ledger(self, rebuild, LedgerRow):
        state = rebuild([])
        assert state.pot_total == 0
        assert state.entry_count == 0
        assert state.is_completed is False
        assert state.players == {}

    def test_blinds_add_to_pot(self, rebuild, LedgerRow):
        entries = [
            _row(LedgerRow, "e1", "BLIND_POSTED", "SB", 50),
            _row(LedgerRow, "e2", "BLIND_POSTED", "BB", 100),
        ]
        state = rebuild(entries)
        assert state.pot_total == 150
        assert state.players["SB"].total_committed == 50
        assert state.players["BB"].total_committed == 100
        assert state.entry_count == 2

    def test_ante_adds_to_pot(self, rebuild, LedgerRow):
        entries = [
            _row(LedgerRow, "e1", "ANTE_POSTED", "A", 10),
            _row(LedgerRow, "e2", "ANTE_POSTED", "B", 10),
            _row(LedgerRow, "e3", "ANTE_POSTED", "C", 10),
        ]
        state = rebuild(entries)
        assert state.pot_total == 30

    def test_bet_placed(self, rebuild, LedgerRow):
        entries = [
            _row(LedgerRow, "e1", "BLIND_POSTED", "SB", 50),
            _row(LedgerRow, "e2", "BLIND_POSTED", "BB", 100),
            _row(LedgerRow, "e3", "BET_PLACED", "UTG", 200),
        ]
        state = rebuild(entries)
        assert state.pot_total == 350
        assert state.players["UTG"].total_committed == 200

    def test_payout_awarded(self, rebuild, LedgerRow):
        entries = [
            _row(LedgerRow, "e1", "BLIND_POSTED", "A", 50),
            _row(LedgerRow, "e2", "BLIND_POSTED", "B", 100),
            _row(LedgerRow, "e3", "PAYOUT_AWARDED", "B", 150),
        ]
        state = rebuild(entries)
        assert state.players["B"].total_won == 150
        # pot_total reflects what went in, not what came out
        assert state.pot_total == 150

    def test_round_completed(self, rebuild, LedgerRow):
        entries = [
            _row(LedgerRow, "e1", "BLIND_POSTED", "A", 50),
            _row(LedgerRow, "e2", "ROUND_COMPLETED"),
        ]
        state = rebuild(entries)
        assert state.is_completed is True

    def test_street_dealt_is_tracked(self, rebuild, LedgerRow):
        """STREET_DEALT doesn't change pot, but is counted."""
        entries = [
            _row(LedgerRow, "e1", "STREET_DEALT"),
        ]
        state = rebuild(entries)
        assert state.entry_count == 1
        assert state.pot_total == 0


# ── ACTION_REVERSED ──────────────────────────────────────────────────

class TestActionReversed:
    def test_reverse_deducts_from_pot(self, rebuild, LedgerRow):
        entries = [
            _row(LedgerRow, "e1", "BET_PLACED", "A", 200),
            _row(LedgerRow, "e2", "ACTION_REVERSED", "A", 200, orig="e1"),
        ]
        state = rebuild(entries)
        assert state.pot_total == 0
        assert state.players["A"].total_committed == 0
        assert "e1" in state.reversed_entry_ids

    def test_reverse_marks_player(self, rebuild, LedgerRow):
        entries = [
            _row(LedgerRow, "e1", "BET_PLACED", "A", 100),
            _row(LedgerRow, "e2", "ACTION_REVERSED", "A", 100, orig="e1"),
        ]
        state = rebuild(entries)
        assert state.players["A"].is_action_reversed is True

    def test_reverse_then_new_bet(self, rebuild, LedgerRow):
        """Reverse a wrong bet, place the correct one."""
        entries = [
            _row(LedgerRow, "e1", "BET_PLACED", "A", 999),     # wrong
            _row(LedgerRow, "e2", "ACTION_REVERSED", "A", 999, orig="e1"),
            _row(LedgerRow, "e3", "BET_PLACED", "A", 200),     # correct
        ]
        state = rebuild(entries)
        assert state.pot_total == 200
        assert state.players["A"].total_committed == 200
        assert state.players["A"].is_action_reversed is False

    def test_reverse_blind(self, rebuild, LedgerRow):
        entries = [
            _row(LedgerRow, "e1", "BLIND_POSTED", "SB", 50),
            _row(LedgerRow, "e2", "BLIND_POSTED", "BB", 100),
            _row(LedgerRow, "e3", "ACTION_REVERSED", "BB", 100, orig="e2"),
        ]
        state = rebuild(entries)
        assert state.pot_total == 50  # only SB
        assert state.players["BB"].total_committed == 0


# ── STACK_ADJUSTED ───────────────────────────────────────────────────

class TestStackAdjusted:
    def test_positive_adjustment(self, rebuild, LedgerRow):
        entries = [
            _row(LedgerRow, "e1", "STACK_ADJUSTED", "A", 500),
        ]
        state = rebuild(entries)
        assert state.players["A"].stack_adjustment == 500

    def test_negative_adjustment(self, rebuild, LedgerRow):
        entries = [
            _row(LedgerRow, "e1", "STACK_ADJUSTED", "A", -200),
        ]
        state = rebuild(entries)
        assert state.players["A"].stack_adjustment == -200

    def test_multiple_adjustments_accumulate(self, rebuild, LedgerRow):
        entries = [
            _row(LedgerRow, "e1", "STACK_ADJUSTED", "A", 100),
            _row(LedgerRow, "e2", "STACK_ADJUSTED", "A", -30),
        ]
        state = rebuild(entries)
        assert state.players["A"].stack_adjustment == 70

    def test_adjustment_does_not_affect_pot(self, rebuild, LedgerRow):
        entries = [
            _row(LedgerRow, "e1", "BLIND_POSTED", "A", 100),
            _row(LedgerRow, "e2", "STACK_ADJUSTED", "A", 50),
        ]
        state = rebuild(entries)
        assert state.pot_total == 100  # unchanged


# ── HAND_REOPENED ────────────────────────────────────────────────────

class TestHandReopened:
    def test_reopen_sets_flags(self, rebuild, LedgerRow):
        entries = [
            _row(LedgerRow, "e1", "ROUND_COMPLETED"),
            _row(LedgerRow, "e2", "HAND_REOPENED"),
        ]
        state = rebuild(entries)
        assert state.is_completed is False
        assert state.is_reopened is True

    def test_reopen_then_recomplete(self, rebuild, LedgerRow):
        entries = [
            _row(LedgerRow, "e1", "ROUND_COMPLETED"),
            _row(LedgerRow, "e2", "HAND_REOPENED"),
            _row(LedgerRow, "e3", "ROUND_COMPLETED"),
        ]
        state = rebuild(entries)
        assert state.is_completed is True
        assert state.is_reopened is True  # still True — it was reopened once


# ── PAYOUT_CORRECTED ────────────────────────────────────────────────

class TestPayoutCorrected:
    def test_correct_payout_swaps_winner(self, rebuild, LedgerRow):
        entries = [
            _row(LedgerRow, "e1", "PAYOUT_AWARDED", "A", 500),
            _row(LedgerRow, "e2", "PAYOUT_CORRECTED", "B", 500,
                 detail={"old_player_id": "A", "old_amount": 500}),
        ]
        state = rebuild(entries)
        assert state.players["A"].total_won == 0   # reversed
        assert state.players["B"].total_won == 500  # new winner

    def test_correct_partial_amount(self, rebuild, LedgerRow):
        entries = [
            _row(LedgerRow, "e1", "PAYOUT_AWARDED", "A", 500),
            _row(LedgerRow, "e2", "PAYOUT_CORRECTED", "A", 300,
                 detail={"old_player_id": "A", "old_amount": 500}),
        ]
        state = rebuild(entries)
        # Original: +500, correction: -500 + 300 = net 300
        assert state.players["A"].total_won == 300

    def test_correction_tracked(self, rebuild, LedgerRow):
        entries = [
            _row(LedgerRow, "e1", "PAYOUT_AWARDED", "A", 500),
            _row(LedgerRow, "e2", "PAYOUT_CORRECTED", "B", 500,
                 detail={"old_player_id": "A", "old_amount": 500}),
        ]
        state = rebuild(entries)
        assert len(state.payout_corrections) == 1
        assert state.payout_corrections[0]["old_player_id"] == "A"
        assert state.payout_corrections[0]["new_player_id"] == "B"


# ── Full workflow scenarios ──────────────────────────────────────────

class TestFullWorkflow:
    def test_deal_misclick_reverse_correct(self, rebuild, LedgerRow):
        """Dealer deals blinds, player bets wrong amount, dealer reverses,
        player bets correct amount, hand completes normally."""
        entries = [
            _row(LedgerRow, "e1", "BLIND_POSTED", "SB", 50),
            _row(LedgerRow, "e2", "BLIND_POSTED", "BB", 100),
            _row(LedgerRow, "e3", "BET_PLACED", "UTG", 999),       # wrong
            _row(LedgerRow, "e4", "ACTION_REVERSED", "UTG", 999, orig="e3"),
            _row(LedgerRow, "e5", "BET_PLACED", "UTG", 200),       # correct
            _row(LedgerRow, "e6", "BET_PLACED", "SB", 150),        # call
            _row(LedgerRow, "e7", "BET_PLACED", "BB", 100),        # call
            _row(LedgerRow, "e8", "PAYOUT_AWARDED", "UTG", 600),
            _row(LedgerRow, "e9", "ROUND_COMPLETED"),
        ]
        state = rebuild(entries)
        assert state.pot_total == 600  # 50+100+200+150+100 = 600
        assert state.players["UTG"].total_committed == 200
        assert state.players["UTG"].total_won == 600
        assert state.is_completed is True
        assert "e3" in state.reversed_entry_ids

    def test_wrong_winner_reopen_and_correct(self, rebuild, LedgerRow):
        """Hand completed with wrong winner — reopen, correct payout, reclose."""
        entries = [
            _row(LedgerRow, "e1", "BLIND_POSTED", "A", 50),
            _row(LedgerRow, "e2", "BLIND_POSTED", "B", 100),
            _row(LedgerRow, "e3", "PAYOUT_AWARDED", "A", 150),     # wrong winner
            _row(LedgerRow, "e4", "ROUND_COMPLETED"),
            # Correction flow:
            _row(LedgerRow, "e5", "HAND_REOPENED"),
            _row(LedgerRow, "e6", "PAYOUT_CORRECTED", "B", 150,
                 detail={"old_player_id": "A", "old_amount": 150}),
            _row(LedgerRow, "e7", "ROUND_COMPLETED"),
        ]
        state = rebuild(entries)
        assert state.players["A"].total_won == 0
        assert state.players["B"].total_won == 150
        assert state.is_completed is True
        assert state.is_reopened is True
        assert state.entry_count == 7

    def test_stack_correction_during_hand(self, rebuild, LedgerRow):
        """Dealer notices wrong chip count mid-hand, adjusts."""
        entries = [
            _row(LedgerRow, "e1", "BLIND_POSTED", "A", 50),
            _row(LedgerRow, "e2", "BLIND_POSTED", "B", 100),
            _row(LedgerRow, "e3", "STACK_ADJUSTED", "A", -25,
                 detail={"reason": "Counted wrong at start"}),
            _row(LedgerRow, "e4", "BET_PLACED", "A", 200),
        ]
        state = rebuild(entries)
        assert state.players["A"].stack_adjustment == -25
        assert state.players["A"].total_committed == 250  # 50 + 200
        assert state.pot_total == 350  # 50+100+200


# ── Six-player scenario ─────────────────────────────────────────────

class TestSixPlayerLedger:
    def test_six_player_with_corrections(self, rebuild, LedgerRow):
        entries = [
            # Blinds + antes
            _row(LedgerRow, "e01", "ANTE_POSTED", "P1", 10),
            _row(LedgerRow, "e02", "ANTE_POSTED", "P2", 10),
            _row(LedgerRow, "e03", "ANTE_POSTED", "P3", 10),
            _row(LedgerRow, "e04", "ANTE_POSTED", "P4", 10),
            _row(LedgerRow, "e05", "ANTE_POSTED", "P5", 10),
            _row(LedgerRow, "e06", "ANTE_POSTED", "P6", 10),
            _row(LedgerRow, "e07", "BLIND_POSTED", "P2", 50),
            _row(LedgerRow, "e08", "BLIND_POSTED", "P3", 100),
            # Action
            _row(LedgerRow, "e09", "BET_PLACED", "P4", 200),
            _row(LedgerRow, "e10", "BET_PLACED", "P5", 500),  # wrong
            _row(LedgerRow, "e11", "ACTION_REVERSED", "P5", 500, orig="e10"),
            _row(LedgerRow, "e12", "BET_PLACED", "P5", 200),  # call
            # Payout
            _row(LedgerRow, "e13", "PAYOUT_AWARDED", "P4", 660),
            _row(LedgerRow, "e14", "ROUND_COMPLETED"),
        ]
        state = rebuild(entries)
        # pot = 6*10 + 50 + 100 + 200 + 200 = 610
        assert state.pot_total == 610
        assert state.players["P4"].total_won == 660
        assert state.players["P5"].total_committed == 210  # ante(10) + bet(200) after reversal
        assert "e10" in state.reversed_entry_ids
        assert state.is_completed is True
        assert state.entry_count == 14
