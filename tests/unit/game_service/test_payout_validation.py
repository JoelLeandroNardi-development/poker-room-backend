"""Unit tests for payout validation against computed side-pot structure."""

from __future__ import annotations

import os

import pytest

from tests.service_loader import load_service_app_module

os.environ.setdefault("GAME_DB", "sqlite+aiosqlite:///:memory:")
os.environ.setdefault("RABBIT_URL", "amqp://guest:guest@localhost:5672/")
os.environ.setdefault("EXCHANGE_NAME", "test_exchange")


@pytest.fixture(scope="module")
def validation_module():
    return load_service_app_module(
        "game-service",
        "domain/payout_validation",
        package_name="game_payout_val_test_app",
        reload_modules=True,
    )


@pytest.fixture(scope="module")
def models_module():
    return load_service_app_module(
        "game-service",
        "domain/models",
        package_name="game_payout_val_test_app",
    )


@pytest.fixture(scope="module")
def exceptions_module():
    return load_service_app_module(
        "game-service",
        "domain/exceptions",
        package_name="game_payout_val_test_app",
    )


@pytest.fixture
def validate(validation_module):
    return validation_module.validate_payouts_against_side_pots


@pytest.fixture
def RoundPlayer(models_module):
    return models_module.RoundPlayer


@pytest.fixture
def PayoutExceedsPot(exceptions_module):
    return exceptions_module.PayoutExceedsPot


@pytest.fixture
def PayoutMismatch(exceptions_module):
    return exceptions_module.PayoutMismatch


def _player(RP, pid, committed, *, folded=False, active=True):
    return RP(
        round_id="r1",
        player_id=pid,
        seat_number=int(pid[-1]),
        stack_remaining=1000 - committed,
        committed_this_street=committed,
        committed_this_hand=committed,
        has_folded=folded,
        is_all_in=False,
        is_active_in_hand=active,
    )


class TestPayoutValidation:
    def test_valid_single_pot(self, validate, RoundPlayer):
        """Standard main pot, single winner — should pass."""
        players = [
            _player(RoundPlayer, "p1", 100),
            _player(RoundPlayer, "p2", 100),
            _player(RoundPlayer, "p3", 100, folded=True, active=False),
        ]
        payouts = [
            {"pot_index": 0, "amount": 300, "winners": [
                {"player_id": "p1", "amount": 300},
            ]},
        ]
        computed = validate(players, payouts, 300)
        assert len(computed) >= 1

    def test_valid_split_pot(self, validate, RoundPlayer):
        """Two winners splitting the pot — should pass."""
        players = [
            _player(RoundPlayer, "p1", 100),
            _player(RoundPlayer, "p2", 100),
        ]
        payouts = [
            {"pot_index": 0, "amount": 200, "winners": [
                {"player_id": "p1", "amount": 100},
                {"player_id": "p2", "amount": 100},
            ]},
        ]
        validate(players, payouts, 200)

    def test_payout_exceeds_computed_pot(self, validate, RoundPlayer, PayoutExceedsPot):
        """Paying out more than the computed pot should fail."""
        players = [
            _player(RoundPlayer, "p1", 100),
            _player(RoundPlayer, "p2", 100),
        ]
        payouts = [
            {"pot_index": 0, "amount": 300, "winners": [
                {"player_id": "p1", "amount": 300},
            ]},
        ]
        with pytest.raises(PayoutExceedsPot):
            validate(players, payouts, 200)

    def test_ineligible_winner_rejected(self, validate, RoundPlayer, PayoutMismatch):
        """A folded player cannot win any pot."""
        players = [
            _player(RoundPlayer, "p1", 100),
            _player(RoundPlayer, "p2", 100),
            _player(RoundPlayer, "p3", 100, folded=True, active=False),
        ]
        payouts = [
            {"pot_index": 0, "amount": 300, "winners": [
                {"player_id": "p3", "amount": 300},
            ]},
        ]
        with pytest.raises(PayoutMismatch):
            validate(players, payouts, 300)

    def test_nonexistent_pot_index_rejected(self, validate, RoundPlayer, PayoutMismatch):
        """Submitting a pot_index that doesn't exist should fail."""
        players = [
            _player(RoundPlayer, "p1", 100),
            _player(RoundPlayer, "p2", 100),
        ]
        payouts = [
            {"pot_index": 5, "amount": 200, "winners": [
                {"player_id": "p1", "amount": 200},
            ]},
        ]
        with pytest.raises(PayoutMismatch):
            validate(players, payouts, 200)

    def test_side_pot_eligible_players(self, validate, RoundPlayer):
        """All-in player creates side pot — only non-all-in players eligible for side pot."""
        # p1 all-in for 50, p2 and p3 each committed 200
        p1 = RoundPlayer(
            round_id="r1", player_id="p1", seat_number=1,
            stack_remaining=0, committed_this_street=50,
            committed_this_hand=50, has_folded=False,
            is_all_in=True, is_active_in_hand=True,
        )
        p2 = _player(RoundPlayer, "p2", 200)
        p3 = _player(RoundPlayer, "p3", 200)
        players = [p1, p2, p3]

        # Computed pots: pot 0 = 150 (50*3, all eligible), pot 1 = 300 (150*2, p2+p3 eligible)
        # p1 eligible for pot 0 only
        payouts = [
            {"pot_index": 0, "amount": 150, "winners": [
                {"player_id": "p1", "amount": 150},
            ]},
            {"pot_index": 1, "amount": 300, "winners": [
                {"player_id": "p2", "amount": 300},
            ]},
        ]
        computed = validate(players, payouts, 450)
        assert len(computed) == 2

    def test_side_pot_ineligible_all_in_player(self, validate, RoundPlayer, PayoutMismatch):
        """All-in player cannot win from a side pot they didn't contribute to."""
        p1 = RoundPlayer(
            round_id="r1", player_id="p1", seat_number=1,
            stack_remaining=0, committed_this_street=50,
            committed_this_hand=50, has_folded=False,
            is_all_in=True, is_active_in_hand=True,
        )
        p2 = _player(RoundPlayer, "p2", 200)
        p3 = _player(RoundPlayer, "p3", 200)
        players = [p1, p2, p3]

        # Try to award side pot to p1 — should fail
        payouts = [
            {"pot_index": 0, "amount": 150, "winners": [
                {"player_id": "p1", "amount": 150},
            ]},
            {"pot_index": 1, "amount": 300, "winners": [
                {"player_id": "p1", "amount": 300},  # ineligible!
            ]},
        ]
        with pytest.raises(PayoutMismatch, match="not eligible"):
            validate(players, payouts, 450)
