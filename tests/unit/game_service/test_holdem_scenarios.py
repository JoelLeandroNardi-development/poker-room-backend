"""
Texas Hold'em hand-flow scenario tests.

These tests compose multiple pure domain functions to simulate realistic
hand sequences:  blind posting → turn order → action validation →
street progression → side-pot calculation.

All tests are pure (no DB, no IO, no async).
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
def bp_module():
    return load_service_app_module(
        "game-service", "domain/blind_posting",
        package_name="scenario_test_app", reload_modules=True,
    )

@pytest.fixture(scope="module")
def te_module():
    return load_service_app_module(
        "game-service", "domain/turn_engine",
        package_name="scenario_test_app",
    )

@pytest.fixture(scope="module")
def sp_module():
    return load_service_app_module(
        "game-service", "domain/street_progression",
        package_name="scenario_test_app",
    )

@pytest.fixture(scope="module")
def sidepots_module():
    return load_service_app_module(
        "game-service", "domain/side_pots",
        package_name="scenario_test_app",
    )

@pytest.fixture(scope="module")
def val_module():
    return load_service_app_module(
        "game-service", "domain/validator",
        package_name="scenario_test_app",
    )

@pytest.fixture(scope="module")
def const_module():
    return load_service_app_module(
        "game-service", "domain/constants",
        package_name="scenario_test_app",
    )


# ── Class / function fixtures ────────────────────────────────────────

@pytest.fixture(scope="module")
def SeatPlayer(bp_module):
    return bp_module.SeatPlayer

@pytest.fixture(scope="module")
def post_blinds(bp_module):
    return bp_module.post_blinds_and_antes

@pytest.fixture(scope="module")
def ActionSeat(te_module):
    return te_module.ActionSeat

@pytest.fixture(scope="module")
def next_to_act(te_module):
    return te_module.next_to_act

@pytest.fixture(scope="module")
def PlayerSeat(sp_module):
    return sp_module.PlayerSeat

@pytest.fixture(scope="module")
def evaluate_street_end(sp_module):
    return sp_module.evaluate_street_end

@pytest.fixture(scope="module")
def find_first_to_act(sp_module):
    return sp_module.find_first_to_act

@pytest.fixture(scope="module")
def PlayerContribution(sidepots_module):
    return sidepots_module.PlayerContribution

@pytest.fixture(scope="module")
def calculate_side_pots(sidepots_module):
    return sidepots_module.calculate_side_pots

@pytest.fixture(scope="module")
def HandContext(val_module):
    return val_module.HandContext

@pytest.fixture(scope="module")
def PlayerState(val_module):
    return val_module.PlayerState

@pytest.fixture(scope="module")
def validate_bet(val_module):
    return val_module.validate_bet

@pytest.fixture(scope="module")
def Street(const_module):
    return const_module.Street

@pytest.fixture(scope="module")
def StreetAdvanceAction(const_module):
    return const_module.StreetAdvanceAction

@pytest.fixture(scope="module")
def BetAction(const_module):
    return const_module.BetAction


# ── Helpers ──────────────────────────────────────────────────────────

def _find(results, pid):
    """Look up a player by id in a blind-posting result."""
    for p in results.players:
        if p.player_id == pid:
            return p
    raise ValueError(f"Player {pid} not found")


def _action_seat(ActionSeat, pid, seat, *, committed=0, folded=False, all_in=False):
    return ActionSeat(
        player_id=pid, seat_number=seat,
        has_folded=folded, is_all_in=all_in,
        is_active_in_hand=True, committed_this_street=committed,
    )


def _player_seat(PlayerSeat, pid, seat, *, folded=False, all_in=False):
    return PlayerSeat(
        player_id=pid, seat_number=seat,
        has_folded=folded, is_all_in=all_in, is_active_in_hand=True,
    )


def _player_state(PlayerState, pid, seat, *, stack=1000, committed_street=0,
                   committed_hand=0, folded=False, all_in=False):
    return PlayerState(
        player_id=pid, seat_number=seat,
        stack_remaining=stack, committed_this_street=committed_street,
        committed_this_hand=committed_hand, has_folded=folded,
        is_all_in=all_in, is_active_in_hand=True,
    )


def _hand_ctx(HandContext, players, *, acting=None, highest_bet=0, min_raise=20,
              street="PRE_FLOP"):
    return HandContext(
        round_id="r1", status="ACTIVE", street=street,
        acting_player_id=acting, current_highest_bet=highest_bet,
        minimum_raise_amount=min_raise, is_action_closed=False,
        players=players,
    )


def _contribution(PC, pid, committed, *, folded=False, showdown=True):
    return PC(
        player_id=pid, committed_this_hand=committed,
        has_folded=folded, reached_showdown=showdown if not folded else False,
    )


# =====================================================================
# S1 — Heads-Up Blind Assignment
# =====================================================================


@pytest.mark.unit
class TestHeadsUpBlindAssignment:
    """Heads-up: BTN=SB posts first, non-dealer=BB posts second."""

    def test_standard_heads_up_blinds(self, post_blinds, SeatPlayer):
        """Seat 1 is dealer/SB, seat 2 is BB."""
        result = post_blinds(
            [SeatPlayer("BTN", 1, 1000), SeatPlayer("BB", 2, 1000)],
            small_blind_seat=1, big_blind_seat=2,
            small_blind_amount=10, big_blind_amount=20,
        )
        btn = _find(result, "BTN")
        bb = _find(result, "BB")
        assert btn.committed_this_street == 10
        assert bb.committed_this_street == 20
        assert result.current_highest_bet == 20
        assert result.pot_total == 30

    def test_short_stack_sb_all_in_on_blind(self, post_blinds, SeatPlayer):
        """SB has only 5 chips — posts all 5 and goes all-in."""
        result = post_blinds(
            [SeatPlayer("BTN", 1, 5), SeatPlayer("BB", 2, 1000)],
            small_blind_seat=1, big_blind_seat=2,
            small_blind_amount=10, big_blind_amount=20,
        )
        btn = _find(result, "BTN")
        assert btn.committed_this_street == 5
        assert btn.is_all_in is True
        assert btn.stack_remaining == 0

    def test_both_short_stacks_post_blinds(self, post_blinds, SeatPlayer):
        """Both players are short — each goes all-in on their blind."""
        result = post_blinds(
            [SeatPlayer("BTN", 1, 3), SeatPlayer("BB", 2, 8)],
            small_blind_seat=1, big_blind_seat=2,
            small_blind_amount=10, big_blind_amount=20,
        )
        btn = _find(result, "BTN")
        bb = _find(result, "BB")
        assert btn.is_all_in is True
        assert btn.committed_this_street == 3
        assert bb.is_all_in is True
        assert bb.committed_this_street == 8
        assert result.pot_total == 11


# =====================================================================
# S2 — Pre-Flop First-to-Act
# =====================================================================


@pytest.mark.unit
class TestPreFlopFirstToAct:
    """After blinds are posted, who acts first pre-flop?"""

    def test_three_player_utg_acts_first(self, post_blinds, SeatPlayer,
                                          next_to_act, ActionSeat):
        """
        3-player: dealer=1, SB=2, BB=3.
        After blinds, the first actor is seat 1 (UTG, left of BB wrapping).
        We simulate by calling next_to_act with current_actor_seat = BB seat
        and no aggressor so it walks clockwise from BB.
        """
        result = post_blinds(
            [SeatPlayer("D", 1, 1000), SeatPlayer("SB", 2, 1000),
             SeatPlayer("BB", 3, 1000)],
            small_blind_seat=2, big_blind_seat=3,
            small_blind_amount=10, big_blind_amount=20,
        )
        # Build ActionSeats from blind result
        seats = [
            _action_seat(ActionSeat, p.player_id, p.seat_number,
                         committed=p.committed_this_street, all_in=p.is_all_in)
            for p in result.players
        ]
        # Pre-flop: first to act is left of BB. We walk from BB's seat.
        nta = next_to_act(seats, current_actor_seat=3,
                          last_aggressor_seat=None,
                          current_highest_bet=result.current_highest_bet)
        assert nta.player_id == "D"  # UTG, seat 1 (wraps around)

    def test_six_player_utg_acts_first(self, post_blinds, SeatPlayer,
                                        next_to_act, ActionSeat):
        """6-player: D=1, SB=2, BB=3, UTG=4, MP=5, CO=6."""
        players = [
            SeatPlayer("D", 1, 1000), SeatPlayer("SB", 2, 1000),
            SeatPlayer("BB", 3, 1000), SeatPlayer("UTG", 4, 1000),
            SeatPlayer("MP", 5, 1000), SeatPlayer("CO", 6, 1000),
        ]
        result = post_blinds(
            players, small_blind_seat=2, big_blind_seat=3,
            small_blind_amount=10, big_blind_amount=20,
        )
        seats = [
            _action_seat(ActionSeat, p.player_id, p.seat_number,
                         committed=p.committed_this_street, all_in=p.is_all_in)
            for p in result.players
        ]
        nta = next_to_act(seats, current_actor_seat=3,
                          last_aggressor_seat=None,
                          current_highest_bet=20)
        assert nta.player_id == "UTG"

    def test_heads_up_sb_acts_first_preflop(self, post_blinds, SeatPlayer,
                                             next_to_act, ActionSeat):
        """
        Heads-up: seat 1 = BTN/SB, seat 2 = BB.
        Pre-flop the SB/BTN acts first.
        Walk clockwise from BB (seat 2) → next eligible owing chips is seat 1 (SB).
        """
        result = post_blinds(
            [SeatPlayer("BTN", 1, 1000), SeatPlayer("BB", 2, 1000)],
            small_blind_seat=1, big_blind_seat=2,
            small_blind_amount=10, big_blind_amount=20,
        )
        seats = [
            _action_seat(ActionSeat, p.player_id, p.seat_number,
                         committed=p.committed_this_street, all_in=p.is_all_in)
            for p in result.players
        ]
        nta = next_to_act(seats, current_actor_seat=2,
                          last_aggressor_seat=None,
                          current_highest_bet=20)
        assert nta.player_id == "BTN"

    def test_bb_gets_option_after_all_limp(self, post_blinds, SeatPlayer,
                                            next_to_act, ActionSeat):
        """
        3-player, everyone calls the BB. BB should get last option.
        After UTG and SB both call 20, next_to_act from SB should
        reach BB (who has committed 20 but hasn't acted voluntarily).
        We set BB's committed=0 to signal "hasn't acted" (the convention
        used by the turn engine).
        """
        # After blinds: D(0), SB(10), BB(20)
        # UTG calls 20: D(20), SB still owes 10
        # SB calls 20: SB(20)
        # Now BB should get the option.
        seats = [
            _action_seat(ActionSeat, "D", 1, committed=20),
            _action_seat(ActionSeat, "SB", 2, committed=20),
            _action_seat(ActionSeat, "BB", 3, committed=0),  # hasn't acted
        ]
        nta = next_to_act(seats, current_actor_seat=2,
                          last_aggressor_seat=None, current_highest_bet=20)
        assert nta.player_id == "BB"
        assert nta.is_round_closed is False


# =====================================================================
# S3 — Post-Flop First-to-Act
# =====================================================================


@pytest.mark.unit
class TestPostFlopFirstToAct:
    """Post-flop: first active player left of dealer acts first."""

    def test_three_player_left_of_dealer(self, evaluate_street_end, PlayerSeat,
                                          Street, StreetAdvanceAction):
        """D=1, SB=2, BB=3. Flop: first to act = seat 2 (left of D)."""
        players = [
            _player_seat(PlayerSeat, "D", 1),
            _player_seat(PlayerSeat, "SB", 2),
            _player_seat(PlayerSeat, "BB", 3),
        ]
        result = evaluate_street_end(Street.PRE_FLOP, dealer_seat=1,
                                     big_blind_seat=3, players=players)
        assert result.action == StreetAdvanceAction.NEXT_STREET
        assert result.next_street == Street.FLOP
        assert result.acting_player_id == "SB"

    def test_heads_up_bb_acts_first_postflop(self, evaluate_street_end, PlayerSeat,
                                              Street):
        """Heads-up: D/SB=1, BB=2. Post-flop BB acts first."""
        players = [
            _player_seat(PlayerSeat, "BTN", 1),
            _player_seat(PlayerSeat, "BB", 2),
        ]
        result = evaluate_street_end(Street.PRE_FLOP, dealer_seat=1,
                                     big_blind_seat=2, players=players)
        assert result.acting_player_id == "BB"

    def test_folded_player_skipped(self, evaluate_street_end, PlayerSeat,
                                    Street):
        """D=1, P2 folded (seat 2), P3 (seat 3). First to act = P3."""
        players = [
            _player_seat(PlayerSeat, "D", 1),
            _player_seat(PlayerSeat, "P2", 2, folded=True),
            _player_seat(PlayerSeat, "P3", 3),
            _player_seat(PlayerSeat, "P4", 4),
        ]
        result = evaluate_street_end(Street.FLOP, dealer_seat=1,
                                     big_blind_seat=3, players=players)
        assert result.acting_player_id == "P3"

    def test_all_in_player_skipped(self, evaluate_street_end, PlayerSeat,
                                    Street):
        """D=1, P2 all-in (seat 2), P3 active. First to act = P3."""
        players = [
            _player_seat(PlayerSeat, "D", 1),
            _player_seat(PlayerSeat, "P2", 2, all_in=True),
            _player_seat(PlayerSeat, "P3", 3),
            _player_seat(PlayerSeat, "P4", 4),
        ]
        result = evaluate_street_end(Street.FLOP, dealer_seat=1,
                                     big_blind_seat=4, players=players)
        assert result.acting_player_id == "P3"

    def test_wrap_around_to_find_first(self, evaluate_street_end, PlayerSeat,
                                        Street):
        """D=5, P1(seat 1) and P2(seat 3). Left of 5 wraps to seat 1."""
        players = [
            _player_seat(PlayerSeat, "P1", 1),
            _player_seat(PlayerSeat, "P2", 3),
            _player_seat(PlayerSeat, "D", 5),
        ]
        result = evaluate_street_end(Street.FLOP, dealer_seat=5,
                                     big_blind_seat=3, players=players)
        assert result.acting_player_id == "P1"


# =====================================================================
# S4 — Legal & Illegal Actions (Betting Sequences)
# =====================================================================


@pytest.mark.unit
class TestActionLegality:
    """Validate which actions are legal given street state."""

    def test_no_bet_check_legal_call_illegal(self, validate_bet, HandContext,
                                              PlayerState, BetAction):
        """When no bet exists: CHECK is legal, CALL is not."""
        p = _player_state(PlayerState, "p1", 1)
        ctx = _hand_ctx(HandContext, [p], acting="p1", highest_bet=0)
        r = validate_bet(ctx, "p1", "CHECK", 0)
        assert r.action == BetAction.CHECK

        with pytest.raises(Exception):
            validate_bet(ctx, "p1", "CALL", 0)

    def test_facing_bet_check_illegal_call_legal(self, validate_bet, HandContext,
                                                   PlayerState, BetAction):
        """When facing a bet: CHECK is illegal, CALL/RAISE/FOLD are legal."""
        p = _player_state(PlayerState, "p1", 1, stack=1000)
        ctx = _hand_ctx(HandContext, [p], acting="p1", highest_bet=50)

        with pytest.raises(Exception):
            validate_bet(ctx, "p1", "CHECK", 0)

        r = validate_bet(ctx, "p1", "CALL", 0)
        assert r.action == BetAction.CALL

    def test_facing_bet_raise_legal(self, validate_bet, HandContext,
                                     PlayerState, BetAction):
        p = _player_state(PlayerState, "p1", 1, stack=1000)
        ctx = _hand_ctx(HandContext, [p], acting="p1", highest_bet=50, min_raise=20)
        r = validate_bet(ctx, "p1", "RAISE", 100)
        assert r.action == BetAction.RAISE

    def test_facing_bet_fold_always_legal(self, validate_bet, HandContext,
                                           PlayerState, BetAction):
        p = _player_state(PlayerState, "p1", 1, stack=1000)
        ctx = _hand_ctx(HandContext, [p], acting="p1", highest_bet=100)
        r = validate_bet(ctx, "p1", "FOLD", 0)
        assert r.action == BetAction.FOLD

    def test_no_bet_raise_illegal(self, validate_bet, HandContext, PlayerState):
        """Can't RAISE when there's no bet — must BET instead."""
        p = _player_state(PlayerState, "p1", 1, stack=1000)
        ctx = _hand_ctx(HandContext, [p], acting="p1", highest_bet=0)
        with pytest.raises(Exception):
            validate_bet(ctx, "p1", "RAISE", 100)

    def test_existing_bet_bet_illegal(self, validate_bet, HandContext, PlayerState):
        """Can't BET when a bet already exists — must RAISE instead."""
        p = _player_state(PlayerState, "p1", 1, stack=1000)
        ctx = _hand_ctx(HandContext, [p], acting="p1", highest_bet=50)
        with pytest.raises(Exception):
            validate_bet(ctx, "p1", "BET", 100)


@pytest.mark.unit
class TestBettingSequence:
    """Simulate a multi-action betting round by threading state."""

    def test_check_bet_raise_call(self, validate_bet, HandContext, PlayerState,
                                   BetAction):
        """
        3-player post-flop:
          P1 checks → P2 bets 40 → P3 raises to 100 → P1 folds → P2 calls.
        """
        # P1 checks (no bet yet)
        p1 = _player_state(PlayerState, "P1", 1, stack=1000)
        p2 = _player_state(PlayerState, "P2", 2, stack=1000)
        p3 = _player_state(PlayerState, "P3", 3, stack=1000)
        ctx = _hand_ctx(HandContext, [p1, p2, p3], acting="P1", highest_bet=0,
                        street="FLOP")
        r1 = validate_bet(ctx, "P1", "CHECK", 0)
        assert r1.action == BetAction.CHECK
        assert r1.amount == 0

        # P2 bets 40
        ctx2 = _hand_ctx(HandContext, [p1, p2, p3], acting="P2", highest_bet=0,
                         min_raise=20, street="FLOP")
        r2 = validate_bet(ctx2, "P2", "BET", 40)
        assert r2.action == BetAction.BET
        assert r2.amount == 40

        # P3 raises to 100 (additional = 100 - 0 = 100 chips)
        p3_facing = _player_state(PlayerState, "P3", 3, stack=1000,
                                   committed_street=0)
        ctx3 = _hand_ctx(HandContext, [p1, p2, p3_facing], acting="P3",
                         highest_bet=40, min_raise=20, street="FLOP")
        r3 = validate_bet(ctx3, "P3", "RAISE", 100)
        assert r3.action == BetAction.RAISE
        assert r3.amount == 100  # additional chips from 0 committed

        # P1 folds
        ctx4 = _hand_ctx(HandContext, [p1, p2, p3], acting="P1",
                         highest_bet=100, street="FLOP")
        r4 = validate_bet(ctx4, "P1", "FOLD", 0)
        assert r4.action == BetAction.FOLD

        # P2 calls 100 (already committed 40, owes 60)
        p2_after = _player_state(PlayerState, "P2", 2, stack=960,
                                  committed_street=40)
        ctx5 = _hand_ctx(HandContext, [p1, p2_after, p3], acting="P2",
                         highest_bet=100, street="FLOP")
        r5 = validate_bet(ctx5, "P2", "CALL", 0)
        assert r5.action == BetAction.CALL
        assert r5.amount == 60  # 100 - 40


@pytest.mark.unit
class TestMinRaiseEnforcement:
    """Min-raise is enforced unless going all-in."""

    def test_under_min_raise_rejected(self, validate_bet, HandContext, PlayerState):
        p = _player_state(PlayerState, "p1", 1, stack=1000)
        ctx = _hand_ctx(HandContext, [p], acting="p1", highest_bet=50, min_raise=50)
        with pytest.raises(Exception):
            validate_bet(ctx, "p1", "RAISE", 80)  # increment 30 < min 50

    def test_under_min_raise_allowed_as_all_in(self, validate_bet, HandContext,
                                                PlayerState, BetAction):
        """Player has only 60 chips. Raise to 60, increment=10 < min=50, but it's all-in."""
        p = _player_state(PlayerState, "p1", 1, stack=60)
        ctx = _hand_ctx(HandContext, [p], acting="p1", highest_bet=50, min_raise=50)
        r = validate_bet(ctx, "p1", "RAISE", 60)
        assert r.action == BetAction.ALL_IN
        assert r.amount == 60

    def test_not_your_turn_rejected(self, validate_bet, HandContext, PlayerState):
        p1 = _player_state(PlayerState, "P1", 1)
        p2 = _player_state(PlayerState, "P2", 2)
        ctx = _hand_ctx(HandContext, [p1, p2], acting="P1", highest_bet=0)
        with pytest.raises(Exception):
            validate_bet(ctx, "P2", "CHECK", 0)


# =====================================================================
# S5 — Short-Stack All-In & Side Pots
# =====================================================================


@pytest.mark.unit
class TestShortStackAllInSidePots:
    """Chain blind posting and action validation into side-pot calculation."""

    def test_short_stack_allin_preflop_creates_side_pot(
        self, post_blinds, SeatPlayer, validate_bet, HandContext,
        PlayerState, calculate_side_pots, PlayerContribution, BetAction,
    ):
        """
        3-player: P1 has 15 chips (UTG, goes all-in), P2=SB(10), P3=BB(20).
        P1 all-in for 15. P2 calls 20. P3 checks (already at 20).

        Commitments: P1=15, P2=20, P3=20.
        Main pot (0→15): 15*3 = 45, eligible {P1, P2, P3}
        Side pot (15→20): 5*2 = 10, eligible {P2, P3}
        """
        result = post_blinds(
            [SeatPlayer("P1", 1, 15), SeatPlayer("P2", 2, 1000),
             SeatPlayer("P3", 3, 1000)],
            small_blind_seat=2, big_blind_seat=3,
            small_blind_amount=10, big_blind_amount=20,
        )
        p1 = _find(result, "P1")
        assert p1.stack_remaining == 15  # UTG didn't post blind

        # P1 goes all-in for 15
        p1s = _player_state(PlayerState, "P1", 1, stack=15)
        ctx = _hand_ctx(HandContext, [p1s], acting="P1", highest_bet=20)
        r = validate_bet(ctx, "P1", "ALL_IN", 0)
        assert r.action == BetAction.ALL_IN
        assert r.amount == 15

        # Build contributions
        contribs = [
            _contribution(PlayerContribution, "P1", 15),
            _contribution(PlayerContribution, "P2", 20),
            _contribution(PlayerContribution, "P3", 20),
        ]
        pots = calculate_side_pots(contribs)
        assert len(pots) == 2
        assert pots[0].amount == 45
        assert set(pots[0].eligible_winner_player_ids) == {"P1", "P2", "P3"}
        assert pots[1].amount == 10
        assert set(pots[1].eligible_winner_player_ids) == {"P2", "P3"}

    def test_three_way_allin_different_levels(
        self, calculate_side_pots, PlayerContribution,
    ):
        """
        P1 all-in 30, P2 all-in 80, P3 calls 200.
        Main pot: 30*3=90 (P1,P2,P3)
        Side 1:   50*2=100 (P2,P3)
        Side 2:   120*1=120 (P3 only)
        """
        contribs = [
            _contribution(PlayerContribution, "P1", 30),
            _contribution(PlayerContribution, "P2", 80),
            _contribution(PlayerContribution, "P3", 200),
        ]
        pots = calculate_side_pots(contribs)
        assert len(pots) == 3
        assert pots[0].amount == 90
        assert set(pots[0].eligible_winner_player_ids) == {"P1", "P2", "P3"}
        assert pots[1].amount == 100
        assert set(pots[1].eligible_winner_player_ids) == {"P2", "P3"}
        assert pots[2].amount == 120
        assert pots[2].eligible_winner_player_ids == ("P3",)
        assert sum(p.amount for p in pots) == 310

    def test_fold_plus_allin_folded_chips_ineligible(
        self, calculate_side_pots, PlayerContribution,
    ):
        """
        P1 folded after committing 40, P2 all-in 100, P3 calls 100.
        P1's 40 goes into the pot but P1 is not eligible.
        """
        contribs = [
            _contribution(PlayerContribution, "P1", 40, folded=True),
            _contribution(PlayerContribution, "P2", 100),
            _contribution(PlayerContribution, "P3", 100),
        ]
        pots = calculate_side_pots(contribs)
        total = sum(p.amount for p in pots)
        assert total == 240
        for pot in pots:
            assert "P1" not in pot.eligible_winner_player_ids

    def test_blind_short_stack_goes_allin_on_blind(
        self, post_blinds, SeatPlayer, calculate_side_pots, PlayerContribution,
    ):
        """
        BB has only 8 chips. Posts 8 (all-in on blind).
        SB posts 10. Other player calls 20.

        Commitments: SB=10, BB=8, UTG=20.
        Tier 1 (0→8): 8*3=24 (SB,BB,UTG)
        Tier 2 (8→10): 2*2=4 (SB,UTG)
        Tier 3 (10→20): 10*1=10 (UTG)
        """
        result = post_blinds(
            [SeatPlayer("UTG", 1, 1000), SeatPlayer("SB", 2, 1000),
             SeatPlayer("BB", 3, 8)],
            small_blind_seat=2, big_blind_seat=3,
            small_blind_amount=10, big_blind_amount=20,
        )
        bb = _find(result, "BB")
        assert bb.is_all_in is True
        assert bb.committed_this_street == 8

        contribs = [
            _contribution(PlayerContribution, "UTG", 20),
            _contribution(PlayerContribution, "SB", 10),
            _contribution(PlayerContribution, "BB", 8),
        ]
        pots = calculate_side_pots(contribs)
        assert pots[0].amount == 24
        assert set(pots[0].eligible_winner_player_ids) == {"UTG", "SB", "BB"}
        assert sum(p.amount for p in pots) == 38


# =====================================================================
# S6 — Split-Pot Settlement
# =====================================================================


@pytest.mark.unit
class TestSplitPotSettlement:
    """Side-pot eligibility determines who can win what."""

    def test_two_equal_stacks_single_pot(self, calculate_side_pots,
                                          PlayerContribution):
        """Equal commitments → single pot, both eligible."""
        contribs = [
            _contribution(PlayerContribution, "A", 200),
            _contribution(PlayerContribution, "B", 200),
        ]
        pots = calculate_side_pots(contribs)
        assert len(pots) == 1
        assert pots[0].amount == 400
        assert set(pots[0].eligible_winner_player_ids) == {"A", "B"}

    def test_short_allin_wins_main_side_to_caller(
        self, calculate_side_pots, PlayerContribution,
    ):
        """
        P1 all-in 50, P2 calls 200.
        Main pot: 50*2=100 (P1, P2 eligible)
        Side pot: 150*1=150 (P2 only — P1 can't win this)
        """
        contribs = [
            _contribution(PlayerContribution, "P1", 50),
            _contribution(PlayerContribution, "P2", 200),
        ]
        pots = calculate_side_pots(contribs)
        assert len(pots) == 2
        assert pots[0].amount == 100
        assert set(pots[0].eligible_winner_player_ids) == {"P1", "P2"}
        assert pots[1].amount == 150
        assert pots[1].eligible_winner_player_ids == ("P2",)

    def test_three_way_middle_wins_main_and_side1(
        self, calculate_side_pots, PlayerContribution,
    ):
        """
        P1 all-in 20, P2 all-in 80, P3 calls 200.
        Main:  20*3=60  (P1,P2,P3)
        Side1: 60*2=120 (P2,P3)
        Side2: 120*1=120 (P3 only)

        If P2 has best hand: P2 wins main (60) + side1 (120) = 180.
        P3 wins side2 (120).  P1 wins nothing.
        This test validates the eligibility sets support that payout logic.
        """
        contribs = [
            _contribution(PlayerContribution, "P1", 20),
            _contribution(PlayerContribution, "P2", 80),
            _contribution(PlayerContribution, "P3", 200),
        ]
        pots = calculate_side_pots(contribs)
        assert len(pots) == 3
        # P2 eligible for main + side1
        assert "P2" in pots[0].eligible_winner_player_ids
        assert "P2" in pots[1].eligible_winner_player_ids
        # P2 NOT eligible for side2
        assert "P2" not in pots[2].eligible_winner_player_ids
        # Total chips conserved
        assert sum(p.amount for p in pots) == 300


# =====================================================================
# S7 — Hand Auto-Complete (Fold-to-Win)
# =====================================================================


@pytest.mark.unit
class TestHandAutoComplete:
    """When all but one player fold, the hand settles immediately."""

    def test_walk_everyone_folds_to_bb(self, post_blinds, SeatPlayer,
                                        evaluate_street_end, PlayerSeat,
                                        Street, StreetAdvanceAction):
        """
        3-player: UTG folds, SB folds → BB wins (a "walk").
        """
        players = [
            _player_seat(PlayerSeat, "D", 1, folded=True),
            _player_seat(PlayerSeat, "SB", 2, folded=True),
            _player_seat(PlayerSeat, "BB", 3),
        ]
        result = evaluate_street_end(Street.PRE_FLOP, dealer_seat=1,
                                     big_blind_seat=3, players=players)
        assert result.action == StreetAdvanceAction.SETTLE_HAND
        assert result.winning_player_id == "BB"

    def test_heads_up_fold_on_flop(self, evaluate_street_end, PlayerSeat,
                                    Street, StreetAdvanceAction):
        """Heads-up, one folds on the flop → immediate settle."""
        players = [
            _player_seat(PlayerSeat, "A", 1),
            _player_seat(PlayerSeat, "B", 2, folded=True),
        ]
        result = evaluate_street_end(Street.FLOP, dealer_seat=1,
                                     big_blind_seat=2, players=players)
        assert result.action == StreetAdvanceAction.SETTLE_HAND
        assert result.winning_player_id == "A"

    def test_four_player_three_fold_on_turn(self, evaluate_street_end, PlayerSeat,
                                             Street, StreetAdvanceAction):
        """4-player, 3 fold on the turn → one player left → settle."""
        players = [
            _player_seat(PlayerSeat, "P1", 1, folded=True),
            _player_seat(PlayerSeat, "P2", 2, folded=True),
            _player_seat(PlayerSeat, "P3", 3),
            _player_seat(PlayerSeat, "P4", 4, folded=True),
        ]
        result = evaluate_street_end(Street.TURN, dealer_seat=1,
                                     big_blind_seat=2, players=players)
        assert result.action == StreetAdvanceAction.SETTLE_HAND
        assert result.winning_player_id == "P3"

    def test_folds_except_allin_player_showdown(self, evaluate_street_end,
                                                  PlayerSeat, Street,
                                                  StreetAdvanceAction):
        """2 active: 1 all-in + 1 folds → only all-in remains → settle (not showdown)."""
        players = [
            _player_seat(PlayerSeat, "P1", 1, all_in=True),
            _player_seat(PlayerSeat, "P2", 2, folded=True),
            _player_seat(PlayerSeat, "P3", 3, folded=True),
        ]
        result = evaluate_street_end(Street.FLOP, dealer_seat=1,
                                     big_blind_seat=3, players=players)
        assert result.action == StreetAdvanceAction.SETTLE_HAND
        assert result.winning_player_id == "P1"

    def test_two_allin_one_folds_showdown(self, evaluate_street_end,
                                           PlayerSeat, Street,
                                           StreetAdvanceAction):
        """2 all-in + 1 folds → 2 remain (both all-in) → showdown."""
        players = [
            _player_seat(PlayerSeat, "P1", 1, all_in=True),
            _player_seat(PlayerSeat, "P2", 2, all_in=True),
            _player_seat(PlayerSeat, "P3", 3, folded=True),
        ]
        result = evaluate_street_end(Street.FLOP, dealer_seat=1,
                                     big_blind_seat=3, players=players)
        assert result.action == StreetAdvanceAction.SHOWDOWN


# =====================================================================
# S8 — Full Hand Walkthroughs (Composite)
# =====================================================================


@pytest.mark.unit
class TestFullHandHeadsUp:
    """Walk through an entire heads-up hand: blinds → 4 streets → showdown."""

    def test_heads_up_all_streets_to_showdown(
        self, post_blinds, SeatPlayer, next_to_act, ActionSeat,
        validate_bet, HandContext, PlayerState, evaluate_street_end,
        PlayerSeat, calculate_side_pots, PlayerContribution,
        Street, StreetAdvanceAction, BetAction,
    ):
        """
        Heads-up hand: BTN/SB=seat1 (1000), BB=seat2 (1000).
        Blinds: 10/20.

        Pre-flop:  SB calls 20. BB checks.
        Flop:      BB checks. BTN bets 40. BB calls 40.
        Turn:      BB checks. BTN checks.
        River:     BB bets 60. BTN calls 60.
        → Showdown with pot 240.
        """

        # ── Blinds ──
        blind_result = post_blinds(
            [SeatPlayer("BTN", 1, 1000), SeatPlayer("BB", 2, 1000)],
            small_blind_seat=1, big_blind_seat=2,
            small_blind_amount=10, big_blind_amount=20,
        )
        assert blind_result.pot_total == 30
        btn_blind = _find(blind_result, "BTN")
        bb_blind = _find(blind_result, "BB")

        # ── Pre-flop: SB acts first (left of BB in heads-up) ──
        pf_seats = [
            _action_seat(ActionSeat, "BTN", 1,
                         committed=btn_blind.committed_this_street),
            _action_seat(ActionSeat, "BB", 2,
                         committed=bb_blind.committed_this_street),
        ]
        first = next_to_act(pf_seats, current_actor_seat=2,
                            last_aggressor_seat=None, current_highest_bet=20)
        assert first.player_id == "BTN"

        # BTN calls 20 (owes 10 more)
        btn_pf = _player_state(PlayerState, "BTN", 1, stack=990,
                                committed_street=10)
        ctx = _hand_ctx(HandContext, [btn_pf], acting="BTN", highest_bet=20)
        r_call = validate_bet(ctx, "BTN", "CALL", 0)
        assert r_call.action == BetAction.CALL
        assert r_call.amount == 10
        # BTN now committed 20, stack 980, pot = 40

        # BB checks (option)
        bb_pf = _player_state(PlayerState, "BB", 2, stack=980,
                               committed_street=20)
        ctx2 = _hand_ctx(HandContext, [bb_pf], acting="BB", highest_bet=20)
        r_check = validate_bet(ctx2, "BB", "CHECK", 0)
        assert r_check.action == BetAction.CHECK

        # Street end → FLOP
        pf_players = [
            _player_seat(PlayerSeat, "BTN", 1),
            _player_seat(PlayerSeat, "BB", 2),
        ]
        advance = evaluate_street_end(Street.PRE_FLOP, dealer_seat=1,
                                      big_blind_seat=2, players=pf_players)
        assert advance.action == StreetAdvanceAction.NEXT_STREET
        assert advance.next_street == Street.FLOP
        assert advance.acting_player_id == "BB"  # post-flop: left of dealer

        # ── Flop: BB checks, BTN bets 40, BB calls ──
        bb_f = _player_state(PlayerState, "BB", 2, stack=980)
        ctx_f1 = _hand_ctx(HandContext, [bb_f], acting="BB", highest_bet=0,
                           street="FLOP")
        validate_bet(ctx_f1, "BB", "CHECK", 0)

        btn_f = _player_state(PlayerState, "BTN", 1, stack=980)
        ctx_f2 = _hand_ctx(HandContext, [btn_f], acting="BTN", highest_bet=0,
                           min_raise=20, street="FLOP")
        r_bet = validate_bet(ctx_f2, "BTN", "BET", 40)
        assert r_bet.amount == 40

        bb_f2 = _player_state(PlayerState, "BB", 2, stack=980)
        ctx_f3 = _hand_ctx(HandContext, [bb_f2], acting="BB", highest_bet=40,
                           street="FLOP")
        r_call_f = validate_bet(ctx_f3, "BB", "CALL", 0)
        assert r_call_f.amount == 40
        # Pot: 40 + 40 + 40 = 120. Stacks: 940 each.

        # Street end → TURN
        adv_f = evaluate_street_end(Street.FLOP, dealer_seat=1,
                                    big_blind_seat=2, players=pf_players)
        assert adv_f.next_street == Street.TURN
        assert adv_f.acting_player_id == "BB"

        # ── Turn: both check ──
        bb_t = _player_state(PlayerState, "BB", 2, stack=940)
        ctx_t1 = _hand_ctx(HandContext, [bb_t], acting="BB", highest_bet=0,
                           street="TURN")
        validate_bet(ctx_t1, "BB", "CHECK", 0)

        btn_t = _player_state(PlayerState, "BTN", 1, stack=940)
        ctx_t2 = _hand_ctx(HandContext, [btn_t], acting="BTN", highest_bet=0,
                           street="TURN")
        validate_bet(ctx_t2, "BTN", "CHECK", 0)

        # Street end → RIVER
        adv_t = evaluate_street_end(Street.TURN, dealer_seat=1,
                                    big_blind_seat=2, players=pf_players)
        assert adv_t.next_street == Street.RIVER
        assert adv_t.acting_player_id == "BB"

        # ── River: BB bets 60, BTN calls ──
        bb_r = _player_state(PlayerState, "BB", 2, stack=940)
        ctx_r1 = _hand_ctx(HandContext, [bb_r], acting="BB", highest_bet=0,
                           min_raise=20, street="RIVER")
        r_bet_r = validate_bet(ctx_r1, "BB", "BET", 60)
        assert r_bet_r.amount == 60

        btn_r = _player_state(PlayerState, "BTN", 1, stack=940)
        ctx_r2 = _hand_ctx(HandContext, [btn_r], acting="BTN", highest_bet=60,
                           street="RIVER")
        r_call_r = validate_bet(ctx_r2, "BTN", "CALL", 0)
        assert r_call_r.amount == 60
        # Pot: 120 + 60 + 60 = 240. Stacks: 880 each.

        # Street end → SHOWDOWN
        adv_r = evaluate_street_end(Street.RIVER, dealer_seat=1,
                                    big_blind_seat=2, players=pf_players)
        assert adv_r.action == StreetAdvanceAction.SHOWDOWN

        # Side pots: equal commitments → single pot
        contribs = [
            _contribution(PlayerContribution, "BTN", 120),  # 20 + 40 + 0 + 60
            _contribution(PlayerContribution, "BB", 120),
        ]
        pots = calculate_side_pots(contribs)
        assert len(pots) == 1
        assert pots[0].amount == 240
        assert set(pots[0].eligible_winner_player_ids) == {"BTN", "BB"}


@pytest.mark.unit
class TestFullHandThreePlayerFold:
    """3-player hand where one folds on the flop → settle."""

    def test_three_player_fold_on_flop(
        self, post_blinds, SeatPlayer, next_to_act, ActionSeat,
        validate_bet, HandContext, PlayerState, evaluate_street_end,
        PlayerSeat, calculate_side_pots, PlayerContribution,
        Street, StreetAdvanceAction, BetAction,
    ):
        """
        3-player: D=1, SB=2, BB=3. Blinds 10/20.

        Pre-flop: D calls 20. SB calls 20. BB checks.
        Flop: SB bets 30. BB folds. D folds. → SB wins.
        """

        # ── Blinds ──
        blind_result = post_blinds(
            [SeatPlayer("D", 1, 1000), SeatPlayer("SB", 2, 1000),
             SeatPlayer("BB", 3, 1000)],
            small_blind_seat=2, big_blind_seat=3,
            small_blind_amount=10, big_blind_amount=20,
        )
        assert blind_result.pot_total == 30

        # ── Pre-flop: UTG (D, seat 1) acts first ──
        seats = [
            _action_seat(ActionSeat, p.player_id, p.seat_number,
                         committed=p.committed_this_street, all_in=p.is_all_in)
            for p in blind_result.players
        ]
        first = next_to_act(seats, current_actor_seat=3,
                            last_aggressor_seat=None, current_highest_bet=20)
        assert first.player_id == "D"  # UTG

        # D calls 20, SB calls 20, BB checks → all at 20
        # Street end → FLOP
        pf_players = [
            _player_seat(PlayerSeat, "D", 1),
            _player_seat(PlayerSeat, "SB", 2),
            _player_seat(PlayerSeat, "BB", 3),
        ]
        advance = evaluate_street_end(Street.PRE_FLOP, dealer_seat=1,
                                      big_blind_seat=3, players=pf_players)
        assert advance.next_street == Street.FLOP
        assert advance.acting_player_id == "SB"  # left of dealer

        # ── Flop: SB bets 30 ──
        sb_f = _player_state(PlayerState, "SB", 2, stack=980)
        ctx_f = _hand_ctx(HandContext, [sb_f], acting="SB", highest_bet=0,
                          min_raise=20, street="FLOP")
        validate_bet(ctx_f, "SB", "BET", 30)

        # BB folds, D folds → only SB remains
        flop_players = [
            _player_seat(PlayerSeat, "D", 1, folded=True),
            _player_seat(PlayerSeat, "SB", 2),
            _player_seat(PlayerSeat, "BB", 3, folded=True),
        ]
        result = evaluate_street_end(Street.FLOP, dealer_seat=1,
                                     big_blind_seat=3, players=flop_players)
        assert result.action == StreetAdvanceAction.SETTLE_HAND
        assert result.winning_player_id == "SB"

        # Side pots: D and BB folded after committing 20 each
        contribs = [
            _contribution(PlayerContribution, "D", 20, folded=True),
            _contribution(PlayerContribution, "SB", 50),  # 20 pre + 30 flop
            _contribution(PlayerContribution, "BB", 20, folded=True),
        ]
        pots = calculate_side_pots(contribs)
        total = sum(p.amount for p in pots)
        assert total == 90
        for pot in pots:
            assert "SB" in pot.eligible_winner_player_ids
            assert "D" not in pot.eligible_winner_player_ids
            assert "BB" not in pot.eligible_winner_player_ids


@pytest.mark.unit
class TestFullHandSixPlayerAllIn:
    """6-player hand with multiple all-ins leading to showdown."""

    def test_six_player_two_allin_one_fold(
        self, post_blinds, SeatPlayer, evaluate_street_end, PlayerSeat,
        calculate_side_pots, PlayerContribution,
        Street, StreetAdvanceAction,
    ):
        """
        6-player, blinds 10/20:
        D=1, SB=2, BB=3, UTG=4, MP=5, CO=6.

        Pre-flop: UTG all-in 50, MP calls 50, CO folds,
                  D folds, SB folds, BB calls 50.
        Flop: BB and MP both check.
        Turn: MP all-in 200, BB calls.
        Commitments: UTG=50, MP=250, BB=250, others folded.
        → Showdown with 3 pots.
        """
        # Post blinds
        players_in = [
            SeatPlayer("D", 1, 1000), SeatPlayer("SB", 2, 1000),
            SeatPlayer("BB", 3, 1000), SeatPlayer("UTG", 4, 50),
            SeatPlayer("MP", 5, 1000), SeatPlayer("CO", 6, 1000),
        ]
        blind_result = post_blinds(
            players_in, small_blind_seat=2, big_blind_seat=3,
            small_blind_amount=10, big_blind_amount=20,
        )
        utg = _find(blind_result, "UTG")
        assert utg.stack_remaining == 50  # UTG has 50 total, no blind

        # After pre-flop action:
        # D folded(0), SB folded(10), BB(50), UTG all-in(50), MP(50), CO folded(0)
        preflop_end = [
            _player_seat(PlayerSeat, "D", 1, folded=True),
            _player_seat(PlayerSeat, "SB", 2, folded=True),
            _player_seat(PlayerSeat, "BB", 3),
            _player_seat(PlayerSeat, "UTG", 4, all_in=True),
            _player_seat(PlayerSeat, "MP", 5),
            _player_seat(PlayerSeat, "CO", 6, folded=True),
        ]

        # Pre-flop end → should go to flop (BB and MP can act)
        adv_pf = evaluate_street_end(Street.PRE_FLOP, dealer_seat=1,
                                     big_blind_seat=3, players=preflop_end)
        assert adv_pf.action == StreetAdvanceAction.NEXT_STREET
        assert adv_pf.next_street == Street.FLOP

        # Flop: both check → turn
        adv_f = evaluate_street_end(Street.FLOP, dealer_seat=1,
                                    big_blind_seat=3, players=preflop_end)
        assert adv_f.action == StreetAdvanceAction.NEXT_STREET
        assert adv_f.next_street == Street.TURN

        # Turn: MP goes all-in → only BB can act → showdown
        turn_end = [
            _player_seat(PlayerSeat, "D", 1, folded=True),
            _player_seat(PlayerSeat, "SB", 2, folded=True),
            _player_seat(PlayerSeat, "BB", 3),
            _player_seat(PlayerSeat, "UTG", 4, all_in=True),
            _player_seat(PlayerSeat, "MP", 5, all_in=True),
            _player_seat(PlayerSeat, "CO", 6, folded=True),
        ]

        # After BB calls, only 1 can act (BB) with 2 all-in → showdown
        # But first let's check: if BB also commits, all remaining are
        # accounted for. With UTG and MP all-in, BB is the only actor.
        adv_t = evaluate_street_end(Street.TURN, dealer_seat=1,
                                    big_blind_seat=3, players=turn_end)
        assert adv_t.action == StreetAdvanceAction.SHOWDOWN

        # Final pot calculation
        contribs = [
            _contribution(PlayerContribution, "D", 0, folded=True),
            _contribution(PlayerContribution, "SB", 10, folded=True),
            _contribution(PlayerContribution, "BB", 250),
            _contribution(PlayerContribution, "UTG", 50),
            _contribution(PlayerContribution, "MP", 250),
            _contribution(PlayerContribution, "CO", 0, folded=True),
        ]
        pots = calculate_side_pots(contribs)
        total = sum(p.amount for p in pots)
        assert total == 560  # 10 + 250 + 50 + 250

        # UTG eligible in main pot only (up to 50 tier)
        utg_pots = [p for p in pots if "UTG" in p.eligible_winner_player_ids]
        assert len(utg_pots) >= 1

        # folded players never eligible
        for pot in pots:
            assert "D" not in pot.eligible_winner_player_ids
            assert "SB" not in pot.eligible_winner_player_ids
            assert "CO" not in pot.eligible_winner_player_ids

        # Last pot should be BB and MP only
        assert set(pots[-1].eligible_winner_player_ids) == {"BB", "MP"}
