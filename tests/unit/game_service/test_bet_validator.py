from __future__ import annotations

import os

import pytest

os.environ.setdefault("GAME_DB", "sqlite+aiosqlite:///:memory:")
os.environ.setdefault("RABBIT_URL", "amqp://guest:guest@localhost:5672/")
os.environ.setdefault("EXCHANGE_NAME", "test_exchange")

from tests.service_loader import load_service_app_module


@pytest.fixture(scope="module")
def validator_module():
    return load_service_app_module(
        "game-service", "domain/validator",
        package_name="bet_validator_test_app",
        reload_modules=True,
    )


@pytest.fixture(scope="module")
def constants_module():
    return load_service_app_module(
        "game-service", "domain/constants",
        package_name="bet_validator_test_app",
    )


@pytest.fixture(scope="module")
def HandContext(validator_module):
    return validator_module.HandContext


@pytest.fixture(scope="module")
def PlayerState(validator_module):
    return validator_module.PlayerState


@pytest.fixture(scope="module")
def validate_bet(validator_module):
    return validator_module.validate_bet


@pytest.fixture(scope="module")
def BetAction(constants_module):
    return constants_module.BetAction


@pytest.fixture(scope="module")
def ErrorMessage(constants_module):
    return constants_module.ErrorMessage


def _make_player(PlayerState, **overrides):
    defaults = dict(
        player_id="p1",
        seat_number=1,
        stack_remaining=1000,
        committed_this_street=0,
        committed_this_hand=0,
        has_folded=False,
        is_all_in=False,
        is_active_in_hand=True,
    )
    defaults.update(overrides)
    return PlayerState(**defaults)


def _make_ctx(HandContext, PlayerState, players=None, **overrides):
    defaults = dict(
        round_id="r1",
        status="ACTIVE",
        street="PRE_FLOP",
        acting_player_id="p1",
        current_highest_bet=0,
        minimum_raise_amount=20,
        is_action_closed=False,
        players=players or [_make_player(PlayerState)],
    )
    defaults.update(overrides)
    return HandContext(**defaults)


# ================================================================
# Round-level guards
# ================================================================

@pytest.mark.unit
class TestRoundGuards:
    def test_round_not_active(self, validate_bet, HandContext, PlayerState, ErrorMessage):
        ctx = _make_ctx(HandContext, PlayerState, status="COMPLETED")
        with pytest.raises(Exception) as exc_info:
            validate_bet(ctx, "p1", "FOLD", 0)
        assert ErrorMessage.ROUND_NOT_ACTIVE in str(exc_info.value.message)

    def test_action_closed(self, validate_bet, HandContext, PlayerState, ErrorMessage):
        ctx = _make_ctx(HandContext, PlayerState, is_action_closed=True)
        with pytest.raises(Exception) as exc_info:
            validate_bet(ctx, "p1", "FOLD", 0)
        assert ErrorMessage.ACTION_CLOSED in str(exc_info.value.message)


# ================================================================
# Player-level guards
# ================================================================

@pytest.mark.unit
class TestPlayerGuards:
    def test_player_not_in_hand(self, validate_bet, HandContext, PlayerState, ErrorMessage):
        ctx = _make_ctx(HandContext, PlayerState)
        with pytest.raises(Exception) as exc_info:
            validate_bet(ctx, "unknown_player", "FOLD", 0)
        assert ErrorMessage.PLAYER_NOT_IN_HAND in str(exc_info.value.message)

    def test_player_inactive(self, validate_bet, HandContext, PlayerState, ErrorMessage):
        p = _make_player(PlayerState, is_active_in_hand=False)
        ctx = _make_ctx(HandContext, PlayerState, players=[p])
        with pytest.raises(Exception) as exc_info:
            validate_bet(ctx, "p1", "FOLD", 0)
        assert ErrorMessage.PLAYER_NOT_IN_HAND in str(exc_info.value.message)

    def test_player_already_folded(self, validate_bet, HandContext, PlayerState, ErrorMessage):
        p = _make_player(PlayerState, has_folded=True)
        ctx = _make_ctx(HandContext, PlayerState, players=[p])
        with pytest.raises(Exception) as exc_info:
            validate_bet(ctx, "p1", "CHECK", 0)
        assert ErrorMessage.PLAYER_ALREADY_FOLDED in str(exc_info.value.message)

    def test_player_already_all_in(self, validate_bet, HandContext, PlayerState, ErrorMessage):
        p = _make_player(PlayerState, is_all_in=True, stack_remaining=0)
        ctx = _make_ctx(HandContext, PlayerState, players=[p])
        with pytest.raises(Exception) as exc_info:
            validate_bet(ctx, "p1", "CHECK", 0)
        assert ErrorMessage.PLAYER_ALL_IN in str(exc_info.value.message)


# ================================================================
# Turn order
# ================================================================

@pytest.mark.unit
class TestTurnOrder:
    def test_not_your_turn(self, validate_bet, HandContext, PlayerState, ErrorMessage):
        p1 = _make_player(PlayerState, player_id="p1", seat_number=1)
        p2 = _make_player(PlayerState, player_id="p2", seat_number=2)
        ctx = _make_ctx(HandContext, PlayerState, players=[p1, p2], acting_player_id="p1")
        with pytest.raises(Exception) as exc_info:
            validate_bet(ctx, "p2", "FOLD", 0)
        assert ErrorMessage.NOT_YOUR_TURN in str(exc_info.value.message)

    def test_correct_turn_succeeds(self, validate_bet, HandContext, PlayerState, BetAction):
        p1 = _make_player(PlayerState, player_id="p1", seat_number=1)
        ctx = _make_ctx(HandContext, PlayerState, players=[p1], acting_player_id="p1")
        result = validate_bet(ctx, "p1", "FOLD", 0)
        assert result.action == BetAction.FOLD

    def test_no_acting_player_allows_anyone(self, validate_bet, HandContext, PlayerState, BetAction):
        p1 = _make_player(PlayerState, player_id="p1", seat_number=1)
        ctx = _make_ctx(HandContext, PlayerState, players=[p1], acting_player_id=None)
        result = validate_bet(ctx, "p1", "FOLD", 0)
        assert result.action == BetAction.FOLD


# ================================================================
# FOLD
# ================================================================

@pytest.mark.unit
class TestFold:
    def test_fold_always_allowed(self, validate_bet, HandContext, PlayerState, BetAction):
        ctx = _make_ctx(HandContext, PlayerState, current_highest_bet=100)
        result = validate_bet(ctx, "p1", "FOLD", 0)
        assert result.action == BetAction.FOLD
        assert result.amount == 0

    def test_fold_ignores_amount(self, validate_bet, HandContext, PlayerState, BetAction):
        ctx = _make_ctx(HandContext, PlayerState)
        result = validate_bet(ctx, "p1", "FOLD", 999)
        assert result.amount == 0


# ================================================================
# CHECK
# ================================================================

@pytest.mark.unit
class TestCheck:
    def test_check_when_no_bet(self, validate_bet, HandContext, PlayerState, BetAction):
        ctx = _make_ctx(HandContext, PlayerState, current_highest_bet=0)
        result = validate_bet(ctx, "p1", "CHECK", 0)
        assert result.action == BetAction.CHECK
        assert result.amount == 0

    def test_check_when_already_matched(self, validate_bet, HandContext, PlayerState, BetAction):
        p = _make_player(PlayerState, committed_this_street=50)
        ctx = _make_ctx(HandContext, PlayerState, players=[p], current_highest_bet=50)
        result = validate_bet(ctx, "p1", "CHECK", 0)
        assert result.action == BetAction.CHECK

    def test_check_not_allowed_when_bet_exists(self, validate_bet, HandContext, PlayerState, ErrorMessage):
        ctx = _make_ctx(HandContext, PlayerState, current_highest_bet=50)
        with pytest.raises(Exception) as exc_info:
            validate_bet(ctx, "p1", "CHECK", 0)
        assert ErrorMessage.CHECK_NOT_ALLOWED in str(exc_info.value.message)


# ================================================================
# CALL
# ================================================================

@pytest.mark.unit
class TestCall:
    def test_call_pays_difference(self, validate_bet, HandContext, PlayerState, BetAction):
        p = _make_player(PlayerState, committed_this_street=20, stack_remaining=980)
        ctx = _make_ctx(HandContext, PlayerState, players=[p], current_highest_bet=50)
        result = validate_bet(ctx, "p1", "CALL", 0)
        assert result.action == BetAction.CALL
        assert result.amount == 30  # 50 - 20

    def test_call_not_allowed_when_nothing_to_call(self, validate_bet, HandContext, PlayerState, ErrorMessage):
        ctx = _make_ctx(HandContext, PlayerState, current_highest_bet=0)
        with pytest.raises(Exception) as exc_info:
            validate_bet(ctx, "p1", "CALL", 0)
        assert ErrorMessage.CALL_NOT_ALLOWED in str(exc_info.value.message)

    def test_call_all_in_when_stack_insufficient(self, validate_bet, HandContext, PlayerState, BetAction):
        p = _make_player(PlayerState, stack_remaining=10, committed_this_street=0)
        ctx = _make_ctx(HandContext, PlayerState, players=[p], current_highest_bet=50)
        result = validate_bet(ctx, "p1", "CALL", 0)
        assert result.action == BetAction.ALL_IN
        assert result.amount == 10

    def test_call_exact_stack_goes_all_in(self, validate_bet, HandContext, PlayerState, BetAction):
        p = _make_player(PlayerState, stack_remaining=50, committed_this_street=0)
        ctx = _make_ctx(HandContext, PlayerState, players=[p], current_highest_bet=50)
        result = validate_bet(ctx, "p1", "CALL", 0)
        assert result.action == BetAction.ALL_IN
        assert result.amount == 50


# ================================================================
# BET (opening bet, no previous bet on street)
# ================================================================

@pytest.mark.unit
class TestBet:
    def test_bet_opens_action(self, validate_bet, HandContext, PlayerState, BetAction):
        ctx = _make_ctx(HandContext, PlayerState, current_highest_bet=0, minimum_raise_amount=20)
        result = validate_bet(ctx, "p1", "BET", 40)
        assert result.action == BetAction.BET
        assert result.amount == 40

    def test_bet_not_allowed_when_bet_exists(self, validate_bet, HandContext, PlayerState, ErrorMessage):
        ctx = _make_ctx(HandContext, PlayerState, current_highest_bet=50)
        with pytest.raises(Exception) as exc_info:
            validate_bet(ctx, "p1", "BET", 100)
        assert ErrorMessage.BET_NOT_ALLOWED in str(exc_info.value.message)

    def test_bet_below_minimum_rejected(self, validate_bet, HandContext, PlayerState, ErrorMessage):
        ctx = _make_ctx(HandContext, PlayerState, current_highest_bet=0, minimum_raise_amount=20)
        with pytest.raises(Exception) as exc_info:
            validate_bet(ctx, "p1", "BET", 10)
        assert "below the minimum" in str(exc_info.value.message)

    def test_bet_below_minimum_allowed_if_all_in(self, validate_bet, HandContext, PlayerState, BetAction):
        p = _make_player(PlayerState, stack_remaining=10)
        ctx = _make_ctx(HandContext, PlayerState, players=[p], current_highest_bet=0, minimum_raise_amount=20)
        result = validate_bet(ctx, "p1", "BET", 10)
        assert result.action == BetAction.ALL_IN
        assert result.amount == 10

    def test_bet_zero_rejected(self, validate_bet, HandContext, PlayerState, ErrorMessage):
        ctx = _make_ctx(HandContext, PlayerState, current_highest_bet=0)
        with pytest.raises(Exception) as exc_info:
            validate_bet(ctx, "p1", "BET", 0)
        assert "must be greater than 0" in str(exc_info.value.message)

    def test_bet_exceeds_stack_rejected(self, validate_bet, HandContext, PlayerState, ErrorMessage):
        p = _make_player(PlayerState, stack_remaining=100)
        ctx = _make_ctx(HandContext, PlayerState, players=[p], current_highest_bet=0)
        with pytest.raises(Exception) as exc_info:
            validate_bet(ctx, "p1", "BET", 200)
        assert ErrorMessage.AMOUNT_EXCEEDS_STACK in str(exc_info.value.message)

    def test_bet_equal_to_stack_is_all_in(self, validate_bet, HandContext, PlayerState, BetAction):
        p = _make_player(PlayerState, stack_remaining=100)
        ctx = _make_ctx(HandContext, PlayerState, players=[p], current_highest_bet=0, minimum_raise_amount=20)
        result = validate_bet(ctx, "p1", "BET", 100)
        assert result.action == BetAction.ALL_IN
        assert result.amount == 100


# ================================================================
# RAISE
# ================================================================

@pytest.mark.unit
class TestRaise:
    def test_raise_succeeds(self, validate_bet, HandContext, PlayerState, BetAction):
        # highest bet is 50, player already committed 20, wants to commit 100 total
        # raise increment = 100 - 50 = 50, min raise = 20 => OK
        # additional chips = 100 - 20 = 80
        p = _make_player(PlayerState, committed_this_street=20, stack_remaining=980)
        ctx = _make_ctx(HandContext, PlayerState, players=[p], current_highest_bet=50, minimum_raise_amount=20)
        result = validate_bet(ctx, "p1", "RAISE", 100)
        assert result.action == BetAction.RAISE
        assert result.amount == 80  # additional chips

    def test_raise_not_allowed_no_bet(self, validate_bet, HandContext, PlayerState, ErrorMessage):
        ctx = _make_ctx(HandContext, PlayerState, current_highest_bet=0)
        with pytest.raises(Exception) as exc_info:
            validate_bet(ctx, "p1", "RAISE", 100)
        assert ErrorMessage.RAISE_NOT_ALLOWED in str(exc_info.value.message)

    def test_raise_below_minimum_rejected(self, validate_bet, HandContext, PlayerState, ErrorMessage):
        # highest bet = 50, raise to 55 => increment = 5, min = 20 => rejected
        p = _make_player(PlayerState, committed_this_street=0, stack_remaining=1000)
        ctx = _make_ctx(HandContext, PlayerState, players=[p], current_highest_bet=50, minimum_raise_amount=20)
        with pytest.raises(Exception) as exc_info:
            validate_bet(ctx, "p1", "RAISE", 55)
        assert ErrorMessage.RAISE_BELOW_MINIMUM in str(exc_info.value.message)

    def test_raise_under_minimum_allowed_if_all_in(self, validate_bet, HandContext, PlayerState, BetAction):
        # highest bet = 50, player has 60 chips, committed 0, raise to 60
        # increment = 60 - 50 = 10 < min=20, but additional = 60 = stack => all-in OK
        p = _make_player(PlayerState, committed_this_street=0, stack_remaining=60)
        ctx = _make_ctx(HandContext, PlayerState, players=[p], current_highest_bet=50, minimum_raise_amount=20)
        result = validate_bet(ctx, "p1", "RAISE", 60)
        assert result.action == BetAction.ALL_IN
        assert result.amount == 60

    def test_raise_exceeds_stack(self, validate_bet, HandContext, PlayerState, ErrorMessage):
        p = _make_player(PlayerState, committed_this_street=0, stack_remaining=50)
        ctx = _make_ctx(HandContext, PlayerState, players=[p], current_highest_bet=20, minimum_raise_amount=20)
        with pytest.raises(Exception) as exc_info:
            validate_bet(ctx, "p1", "RAISE", 200)
        assert "exceeds remaining stack" in str(exc_info.value.message)

    def test_raise_zero_additional_rejected(self, validate_bet, HandContext, PlayerState, ErrorMessage):
        # committed 50, raise to 50 => additional = 0 => rejected
        p = _make_player(PlayerState, committed_this_street=50, stack_remaining=950)
        ctx = _make_ctx(HandContext, PlayerState, players=[p], current_highest_bet=50, minimum_raise_amount=20)
        with pytest.raises(Exception) as exc_info:
            validate_bet(ctx, "p1", "RAISE", 50)
        assert "must be greater than 0" in str(exc_info.value.message)

    def test_raise_equal_to_stack_is_all_in(self, validate_bet, HandContext, PlayerState, BetAction):
        # stack=100, committed=0, highest=50, raise to 100 => additional=100=stack => ALL_IN
        p = _make_player(PlayerState, committed_this_street=0, stack_remaining=100)
        ctx = _make_ctx(HandContext, PlayerState, players=[p], current_highest_bet=50, minimum_raise_amount=20)
        result = validate_bet(ctx, "p1", "RAISE", 100)
        assert result.action == BetAction.ALL_IN
        assert result.amount == 100


# ================================================================
# ALL_IN (explicit)
# ================================================================

@pytest.mark.unit
class TestAllIn:
    def test_all_in_uses_full_stack(self, validate_bet, HandContext, PlayerState, BetAction):
        p = _make_player(PlayerState, stack_remaining=350)
        ctx = _make_ctx(HandContext, PlayerState, players=[p], current_highest_bet=100)
        result = validate_bet(ctx, "p1", "ALL_IN", 0)
        assert result.action == BetAction.ALL_IN
        assert result.amount == 350

    def test_all_in_ignores_amount_param(self, validate_bet, HandContext, PlayerState, BetAction):
        p = _make_player(PlayerState, stack_remaining=200)
        ctx = _make_ctx(HandContext, PlayerState, players=[p])
        result = validate_bet(ctx, "p1", "ALL_IN", 50)
        assert result.amount == 200

    def test_all_in_zero_stack_rejected(self, validate_bet, HandContext, PlayerState, ErrorMessage):
        p = _make_player(PlayerState, stack_remaining=0)
        ctx = _make_ctx(HandContext, PlayerState, players=[p])
        with pytest.raises(Exception) as exc_info:
            validate_bet(ctx, "p1", "ALL_IN", 0)
        assert ErrorMessage.PLAYER_ALL_IN in str(exc_info.value.message)

    def test_all_in_as_short_call(self, validate_bet, HandContext, PlayerState, BetAction):
        # Player has 30 chips, bet to call is 100. ALL_IN for 30.
        p = _make_player(PlayerState, stack_remaining=30)
        ctx = _make_ctx(HandContext, PlayerState, players=[p], current_highest_bet=100)
        result = validate_bet(ctx, "p1", "ALL_IN", 0)
        assert result.action == BetAction.ALL_IN
        assert result.amount == 30


# ================================================================
# Edge case: invalid action name
# ================================================================

@pytest.mark.unit
class TestInvalidAction:
    def test_completely_unknown_action(self, validate_bet, HandContext, PlayerState, ErrorMessage):
        ctx = _make_ctx(HandContext, PlayerState)
        with pytest.raises(Exception) as exc_info:
            validate_bet(ctx, "p1", "BLUFF", 0)
        assert ErrorMessage.INVALID_ACTION in str(exc_info.value.message)


# ================================================================
# Case-insensitive action matching
# ================================================================

@pytest.mark.unit
class TestCaseInsensitive:
    def test_lowercase_fold(self, validate_bet, HandContext, PlayerState, BetAction):
        ctx = _make_ctx(HandContext, PlayerState)
        result = validate_bet(ctx, "p1", "fold", 0)
        assert result.action == BetAction.FOLD

    def test_mixed_case_check(self, validate_bet, HandContext, PlayerState, BetAction):
        ctx = _make_ctx(HandContext, PlayerState, current_highest_bet=0)
        result = validate_bet(ctx, "p1", "Check", 0)
        assert result.action == BetAction.CHECK
