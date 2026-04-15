"""Integration tests for full action flows.

These tests compose the unified action pipeline with ORM model instances
to simulate realistic multi-step hand flows:

- Apply action → street close
- Full betting round with multiple players
- Side-pot settlement with payout validation
- Reverse / reopen correction flows
- Pure transition_hand_state round-trip
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
def pipeline_mod():
    return load_service_app_module(
        "game-service", "domain/action_pipeline",
        package_name="integ_test_app", reload_modules=True,
    )

@pytest.fixture(scope="module")
def models_mod():
    return load_service_app_module(
        "game-service", "domain/models",
        package_name="integ_test_app",
    )

@pytest.fixture(scope="module")
def constants_mod():
    return load_service_app_module(
        "game-service", "domain/constants",
        package_name="integ_test_app",
    )

@pytest.fixture(scope="module")
def exceptions_mod():
    return load_service_app_module(
        "game-service", "domain/exceptions",
        package_name="integ_test_app",
    )

@pytest.fixture(scope="module")
def validator_mod():
    return load_service_app_module(
        "game-service", "domain/validator",
        package_name="integ_test_app",
    )

@pytest.fixture(scope="module")
def payout_validation_mod():
    return load_service_app_module(
        "game-service", "domain/payout_validation",
        package_name="integ_test_app",
    )

@pytest.fixture(scope="module")
def hand_ledger_mod():
    return load_service_app_module(
        "game-service", "domain/hand_ledger",
        package_name="integ_test_app",
    )


# ── Shortcut fixtures ───────────────────────────────────────────────

@pytest.fixture
def apply_action(pipeline_mod):
    return pipeline_mod.apply_action

@pytest.fixture
def transition_hand_state(pipeline_mod):
    return pipeline_mod.transition_hand_state

@pytest.fixture
def Round(models_mod):
    return models_mod.Round

@pytest.fixture
def RoundPlayer(models_mod):
    return models_mod.RoundPlayer

@pytest.fixture
def BetAction(constants_mod):
    return constants_mod.BetAction

@pytest.fixture
def RoundStatus(constants_mod):
    return constants_mod.RoundStatus

@pytest.fixture
def Street(constants_mod):
    return constants_mod.Street

@pytest.fixture
def HandContext(validator_mod):
    return validator_mod.HandContext

@pytest.fixture
def PlayerState(validator_mod):
    return validator_mod.PlayerState


# ── Helpers ──────────────────────────────────────────────────────────

def _round(Round, Street, RoundStatus, **kw):
    defaults = dict(
        round_id="r1", game_id="g1", round_number=1,
        dealer_seat=1, small_blind_seat=2, big_blind_seat=3,
        small_blind_amount=50, big_blind_amount=100, ante_amount=0,
        status=RoundStatus.ACTIVE, pot_amount=150,
        street=Street.PRE_FLOP, acting_player_id="p4",
        current_highest_bet=100, minimum_raise_amount=100,
        is_action_closed=False, last_aggressor_seat=None,
    )
    defaults.update(kw)
    return Round(**defaults)


def _player(RP, pid, seat, stack, cs=0, ch=0, **kw):
    defaults = dict(
        round_id="r1", player_id=pid, seat_number=seat,
        stack_remaining=stack, committed_this_street=cs,
        committed_this_hand=ch, has_folded=False,
        is_all_in=False, is_active_in_hand=True,
    )
    defaults.update(kw)
    return RP(**defaults)


# ═══════════════════════════════════════════════════════════════════════
#  Full betting round flow
# ═══════════════════════════════════════════════════════════════════════

class TestFullBettingRound:
    """Simulate a complete pre-flop betting round: UTG calls, SB calls, BB checks."""

    def test_three_player_preflop_completes(self, apply_action, Round, RoundPlayer, BetAction, RoundStatus, Street):
        gr = _round(Round, Street, RoundStatus, acting_player_id="p4")
        players = [
            _player(RoundPlayer, "p2", 2, 950, 50, 50),   # SB
            _player(RoundPlayer, "p3", 3, 900, 100, 100), # BB (aggressor)
            _player(RoundPlayer, "p4", 4, 1000, 0, 0),    # UTG
        ]
        # BB is the initial aggressor pre-flop
        gr.last_aggressor_seat = 3

        # UTG calls
        r1 = apply_action(gr, players, "p4", "CALL", 0)
        assert r1.action == BetAction.CALL
        assert r1.is_round_closed is False
        assert gr.acting_player_id == "p2"

        # SB calls — round closes when wrapping back to BB (aggressor)
        # (This engine does not give BB a separate "live option" check)
        r2 = apply_action(gr, players, "p2", "CALL", 0)
        assert r2.action == BetAction.CALL
        assert r2.is_round_closed is True
        assert gr.is_action_closed is True

        # Pot = 150 (initial) + 100 (UTG) + 50 (SB) = 300
        assert gr.pot_amount == 300

    def test_raise_reopen_round(self, apply_action, Round, RoundPlayer, BetAction, RoundStatus, Street):
        """A raise reopens action for all players who already acted."""
        gr = _round(Round, Street, RoundStatus, acting_player_id="p4")
        players = [
            _player(RoundPlayer, "p2", 2, 950, 50, 50),
            _player(RoundPlayer, "p3", 3, 900, 100, 100),
            _player(RoundPlayer, "p4", 4, 1000, 0, 0),
        ]
        gr.last_aggressor_seat = 3

        # UTG raises to 200
        r1 = apply_action(gr, players, "p4", "RAISE", 200)
        assert r1.action == BetAction.RAISE
        assert r1.is_round_closed is False
        assert gr.last_aggressor_seat == 4

        # SB must now respond (folds)
        r2 = apply_action(gr, players, "p2", "FOLD", 0)
        assert r2.is_round_closed is False

        # BB must respond (calls)
        r3 = apply_action(gr, players, "p3", "CALL", 0)
        assert r3.is_round_closed is True
        assert gr.pot_amount == 150 + 200 + 100  # original + UTG raise + BB call


class TestStreetTransition:
    """Test that action flow works correctly on post-flop streets."""

    def test_bet_sets_aggressor(self, apply_action, Round, RoundPlayer, BetAction, RoundStatus, Street):
        """A bet on a fresh street sets last_aggressor_seat."""
        gr = _round(
            Round, Street, RoundStatus,
            acting_player_id="p1", pot_amount=300,
            current_highest_bet=0, minimum_raise_amount=100,
            street=Street.FLOP, last_aggressor_seat=None,
        )
        players = [
            _player(RoundPlayer, "p1", 1, 800, 0, 100),
            _player(RoundPlayer, "p2", 2, 800, 0, 100),
            _player(RoundPlayer, "p3", 3, 800, 0, 100),
        ]

        # p1 bets — becomes aggressor, round stays open
        r1 = apply_action(gr, players, "p1", "BET", 100)
        assert r1.is_round_closed is False
        assert gr.last_aggressor_seat == 1

        # p2 calls
        r2 = apply_action(gr, players, "p2", "CALL", 0)
        assert r2.is_round_closed is False

        # p3 calls — wraps back to aggressor, round closes
        r3 = apply_action(gr, players, "p3", "CALL", 0)
        assert r3.is_round_closed is True
        assert gr.pot_amount == 600  # 300 + 100 + 100 + 100

    def test_raise_shifts_aggressor(self, apply_action, Round, RoundPlayer, BetAction, RoundStatus, Street):
        """A raise moves last_aggressor_seat to the raiser."""
        gr = _round(
            Round, Street, RoundStatus,
            acting_player_id="p1", pot_amount=300,
            current_highest_bet=0, minimum_raise_amount=100,
            street=Street.FLOP, last_aggressor_seat=None,
        )
        players = [
            _player(RoundPlayer, "p1", 1, 800, 0, 100),
            _player(RoundPlayer, "p2", 2, 800, 0, 100),
        ]

        # p1 bets 100
        apply_action(gr, players, "p1", "BET", 100)
        assert gr.last_aggressor_seat == 1

        # p2 raises to 300
        apply_action(gr, players, "p2", "RAISE", 300)
        assert gr.last_aggressor_seat == 2

        # p1 calls — wraps back to aggressor (p2), round closes
        r3 = apply_action(gr, players, "p1", "CALL", 0)
        assert r3.is_round_closed is True


class TestAllInSidePotFlow:
    """Short-stack all-in creates side pots, validated at settlement."""

    def test_all_in_and_payout(self, apply_action, Round, RoundPlayer, BetAction, RoundStatus, Street, payout_validation_mod):
        validate = payout_validation_mod.validate_payouts_against_side_pots

        gr = _round(
            Round, Street, RoundStatus,
            acting_player_id="p1", pot_amount=0,
            current_highest_bet=0, minimum_raise_amount=100,
            street=Street.FLOP, last_aggressor_seat=None,
        )
        # p1 short stack (50 chips), p2 and p3 deep
        players = [
            _player(RoundPlayer, "p1", 1, 50, 0, 0),
            _player(RoundPlayer, "p2", 2, 1000, 0, 0),
            _player(RoundPlayer, "p3", 3, 1000, 0, 0),
        ]

        # p1 goes all-in for 50
        r1 = apply_action(gr, players, "p1", "ALL_IN", 0)
        assert r1.action == BetAction.ALL_IN
        assert r1.amount == 50
        assert players[0].is_all_in is True

        # p2 calls 50
        r2 = apply_action(gr, players, "p2", "CALL", 0)
        assert r2.amount == 50

        # p3 raises to 200
        r3 = apply_action(gr, players, "p3", "RAISE", 200)
        assert r3.amount == 200

        # p2 calls the raise
        r4 = apply_action(gr, players, "p2", "CALL", 0)

        total_pot = gr.pot_amount  # 50 + 50 + 200 + 150 = 450

        # Validate payouts: pot 0 = 150 (50*3), pot 1 = 300 (150*2)
        payouts = [
            {"pot_index": 0, "amount": 150, "winners": [{"player_id": "p1", "amount": 150}]},
            {"pot_index": 1, "amount": 300, "winners": [{"player_id": "p2", "amount": 300}]},
        ]
        computed = validate(players, payouts, total_pot)
        assert len(computed) == 2


class TestPayoutValidationRejection:
    """Payout validation catches invalid settlements."""

    def test_folded_player_cannot_win(self, apply_action, Round, RoundPlayer, BetAction, RoundStatus, Street, payout_validation_mod, exceptions_mod):
        validate = payout_validation_mod.validate_payouts_against_side_pots
        PayoutMismatch = exceptions_mod.PayoutMismatch

        gr = _round(
            Round, Street, RoundStatus,
            acting_player_id="p1", pot_amount=0,
            current_highest_bet=0, minimum_raise_amount=100,
            street=Street.FLOP, last_aggressor_seat=None,
        )
        players = [
            _player(RoundPlayer, "p1", 1, 1000, 0, 0),
            _player(RoundPlayer, "p2", 2, 1000, 0, 0),
            _player(RoundPlayer, "p3", 3, 1000, 0, 0),
        ]

        # p1 bets 100
        apply_action(gr, players, "p1", "BET", 100)
        # p2 folds
        apply_action(gr, players, "p2", "FOLD", 0)
        # p3 calls
        apply_action(gr, players, "p3", "CALL", 0)

        payouts = [{"pot_index": 0, "amount": 200, "winners": [{"player_id": "p2", "amount": 200}]}]
        with pytest.raises(PayoutMismatch, match="not eligible"):
            validate(players, payouts, gr.pot_amount)


# ═══════════════════════════════════════════════════════════════════════
#  Pure transition_hand_state tests
# ═══════════════════════════════════════════════════════════════════════

class TestPureTransition:
    """Verify transition_hand_state returns correct mutation plans
    without mutating input."""

    def test_fold_returns_fold_mutation(self, transition_hand_state, HandContext, PlayerState, BetAction, RoundStatus, Street):
        ctx = HandContext(
            round_id="r1", status=RoundStatus.ACTIVE, street=Street.FLOP,
            acting_player_id="p1", current_highest_bet=0,
            minimum_raise_amount=100, is_action_closed=False,
            players=[
                PlayerState("p1", 1, 1000, 0, 0, False, False, True),
                PlayerState("p2", 2, 1000, 0, 0, False, False, True),
            ],
        )

        result = transition_hand_state(ctx, "p1", "FOLD", 0, last_aggressor_seat=None)

        assert result.action == BetAction.FOLD
        assert result.amount == 0
        assert result.player_mutation.should_fold is True
        assert result.player_mutation.stack_delta == 0
        assert result.round_mutation.pot_delta == 0

    def test_bet_returns_bet_mutation(self, transition_hand_state, HandContext, PlayerState, BetAction, RoundStatus, Street):
        ctx = HandContext(
            round_id="r1", status=RoundStatus.ACTIVE, street=Street.FLOP,
            acting_player_id="p1", current_highest_bet=0,
            minimum_raise_amount=100, is_action_closed=False,
            players=[
                PlayerState("p1", 1, 1000, 0, 0, False, False, True),
                PlayerState("p2", 2, 1000, 0, 0, False, False, True),
            ],
        )

        result = transition_hand_state(ctx, "p1", "BET", 200, last_aggressor_seat=None)

        assert result.action == BetAction.BET
        assert result.amount == 200
        assert result.player_mutation.stack_delta == -200
        assert result.player_mutation.street_commit_delta == 200
        assert result.round_mutation.pot_delta == 200
        assert result.round_mutation.new_highest_bet == 200
        assert result.round_mutation.new_last_aggressor_seat == 1
        assert result.is_round_closed is False

    def test_transition_does_not_mutate_context(self, transition_hand_state, HandContext, PlayerState, BetAction, RoundStatus, Street):
        """The pure function must not change its inputs."""
        ctx = HandContext(
            round_id="r1", status=RoundStatus.ACTIVE, street=Street.FLOP,
            acting_player_id="p1", current_highest_bet=0,
            minimum_raise_amount=100, is_action_closed=False,
            players=[
                PlayerState("p1", 1, 1000, 0, 0, False, False, True),
                PlayerState("p2", 2, 1000, 0, 0, False, False, True),
            ],
        )
        original_stack = ctx.players[0].stack_remaining
        original_pot = 0

        transition_hand_state(ctx, "p1", "BET", 200, last_aggressor_seat=None)

        # HandContext and PlayerState are frozen dataclasses — verify
        assert ctx.players[0].stack_remaining == original_stack
        assert ctx.current_highest_bet == original_pot

    def test_round_closure_in_pure_transition(self, transition_hand_state, HandContext, PlayerState, BetAction, RoundStatus, Street):
        """When all players have matched, transition signals round closed."""
        ctx = HandContext(
            round_id="r1", status=RoundStatus.ACTIVE, street=Street.FLOP,
            acting_player_id="p2", current_highest_bet=100,
            minimum_raise_amount=100, is_action_closed=False,
            players=[
                PlayerState("p1", 1, 900, 100, 100, False, False, True),
                PlayerState("p2", 2, 1000, 0, 0, False, False, True),
            ],
        )

        result = transition_hand_state(ctx, "p2", "CALL", 0, last_aggressor_seat=1)

        assert result.is_round_closed is True
        assert result.round_mutation.is_action_closed is True


# ═══════════════════════════════════════════════════════════════════════
#  Hand ledger rebuild consistency
# ═══════════════════════════════════════════════════════════════════════

class TestLedgerConsistency:
    """Verify that actions + ledger entries produce consistent state."""

    def test_ledger_tracks_blind_and_bet(self, hand_ledger_mod):
        LedgerRow = hand_ledger_mod.LedgerRow
        rebuild = hand_ledger_mod.rebuild_hand_state

        entries = [
            LedgerRow("e1", "BLIND_POSTED", "p1", 50, {"role": "SB"}, None),
            LedgerRow("e2", "BLIND_POSTED", "p2", 100, {"role": "BB"}, None),
            LedgerRow("e3", "BET_PLACED", "p3", 100, {"action": "CALL"}, None),
            LedgerRow("e4", "BET_PLACED", "p1", 50, {"action": "CALL"}, None),
        ]
        state = rebuild(entries)

        assert state.pot_total == 300
        assert state.players["p1"].total_committed == 100  # 50 blind + 50 call
        assert state.players["p2"].total_committed == 100
        assert state.players["p3"].total_committed == 100

    def test_reversal_adjusts_ledger_state(self, hand_ledger_mod):
        LedgerRow = hand_ledger_mod.LedgerRow
        rebuild = hand_ledger_mod.rebuild_hand_state

        entries = [
            LedgerRow("e1", "BLIND_POSTED", "p1", 50, None, None),
            LedgerRow("e2", "BLIND_POSTED", "p2", 100, None, None),
            LedgerRow("e3", "BET_PLACED", "p1", 100, None, None),
            # Reverse e3
            LedgerRow("e4", "ACTION_REVERSED", "p1", 100, {"reason": "mistake"}, "e3"),
        ]
        state = rebuild(entries)

        assert state.pot_total == 150  # only blinds remain
        # p1: 50 (blind) + 100 (bet) - 100 (reversed) = 50
        assert state.players["p1"].total_committed == 50
        assert "e3" in state.reversed_entry_ids

    def test_reopen_and_correct_payout(self, hand_ledger_mod):
        LedgerRow = hand_ledger_mod.LedgerRow
        rebuild = hand_ledger_mod.rebuild_hand_state

        entries = [
            LedgerRow("e1", "BLIND_POSTED", "p1", 100, None, None),
            LedgerRow("e2", "BLIND_POSTED", "p2", 100, None, None),
            LedgerRow("e3", "PAYOUT_AWARDED", "p1", 200, None, None),
            LedgerRow("e4", "ROUND_COMPLETED", None, 200, None, None),
            # Reopen
            LedgerRow("e5", "HAND_REOPENED", None, None, None, None),
            # Correct: p1 shouldn't have won, p2 should
            LedgerRow("e6", "PAYOUT_CORRECTED", "p2", 200,
                       {"old_player_id": "p1", "old_amount": 200}, None),
        ]
        state = rebuild(entries)

        assert state.is_reopened is True
        assert state.players["p1"].total_won == 0   # 200 awarded - 200 corrected
        assert state.players["p2"].total_won == 200
