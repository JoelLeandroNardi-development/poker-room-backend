"""Tests for new engine features:

- Incremental replay (O(n) via apply_entry)
- Optimistic concurrency (state_version, StaleStateError)
- Idempotency key on Bet model
- Table runtime session layer
- RulesProfile wiring through apply_action
- Scenario runner using real blind posting
"""

from __future__ import annotations

import os

import pytest

from tests.service_loader import load_service_app_module

os.environ.setdefault("GAME_DB", "sqlite+aiosqlite:///:memory:")
os.environ.setdefault("RABBIT_URL", "amqp://guest:guest@localhost:5672/")
os.environ.setdefault("EXCHANGE_NAME", "test_exchange")

@pytest.fixture(scope="module")
def ledger_mod():
    return load_service_app_module(
        "game-service", "domain/ledger/hand_ledger",
        package_name="new_features_app", reload_modules=True,
    )

@pytest.fixture(scope="module")
def replay_mod():
    return load_service_app_module(
        "game-service", "domain/ledger/hand_replay",
        package_name="new_features_app",
    )

@pytest.fixture(scope="module")
def pipeline_mod():
    return load_service_app_module(
        "game-service", "domain/engine/action_pipeline",
        package_name="new_features_app",
    )

@pytest.fixture(scope="module")
def validator_mod():
    return load_service_app_module(
        "game-service", "domain/engine/validator",
        package_name="new_features_app",
    )

@pytest.fixture(scope="module")
def rules_mod():
    return load_service_app_module(
        "game-service", "domain/rules",
        package_name="new_features_app",
    )

@pytest.fixture(scope="module")
def exceptions_mod():
    return load_service_app_module(
        "game-service", "domain/exceptions",
        package_name="new_features_app",
    )

@pytest.fixture(scope="module")
def scenario_mod():
    return load_service_app_module(
        "game-service", "domain/scenario_runner",
        package_name="new_features_app",
    )

@pytest.fixture(scope="module")
def models_mod():
    return load_service_app_module(
        "game-service", "domain/models",
        package_name="new_features_app",
    )

@pytest.fixture(scope="module")
def table_runtime_mod():
    return load_service_app_module(
        "game-service", "domain/engine/table_runtime",
        package_name="new_features_app",
    )

@pytest.fixture(scope="module")
def room_adapter_mod():
    return load_service_app_module(
        "game-service", "domain/integration/room_adapter",
        package_name="new_features_app",
    )

@pytest.fixture(scope="module")
def game_command_mod(room_adapter_mod):
    return load_service_app_module(
        "game-service", "application/commands/game_command_service",
        package_name="new_features_app",
    )

@pytest.fixture
def LedgerRow(ledger_mod):
    return ledger_mod.LedgerRow

@pytest.fixture
def apply_entry(ledger_mod):
    return ledger_mod.apply_entry

@pytest.fixture
def HandState(ledger_mod):
    return ledger_mod.HandState

@pytest.fixture
def Round(models_mod):
    return models_mod.Round

@pytest.fixture
def RoundPlayer(models_mod):
    return models_mod.RoundPlayer

def _row(LedgerRow, entry_id, entry_type, player_id=None, amount=None,
         detail=None, original_entry_id=None):
    return LedgerRow(
        entry_id=entry_id,
        entry_type=entry_type,
        player_id=player_id,
        amount=amount,
        detail=detail,
        original_entry_id=original_entry_id,
    )

class TestApplyEntry:
    def test_apply_entry_blind(self, apply_entry, HandState, LedgerRow):
        state = HandState()
        row = _row(LedgerRow, "e1", "BLIND_POSTED", "p1", 50)
        apply_entry(state, row)
        assert state.pot_total == 50
        assert state.entry_count == 1
        assert state.players["p1"].total_committed == 50

    def test_apply_entry_sequence(self, apply_entry, HandState, LedgerRow):
        state = HandState()
        apply_entry(state, _row(LedgerRow, "e1", "BLIND_POSTED", "p1", 50))
        apply_entry(state, _row(LedgerRow, "e2", "BLIND_POSTED", "p2", 100))
        apply_entry(state, _row(LedgerRow, "e3", "BET_PLACED", "p3", 100))
        assert state.pot_total == 250
        assert state.entry_count == 3
        assert state.players["p1"].total_committed == 50
        assert state.players["p2"].total_committed == 100
        assert state.players["p3"].total_committed == 100

    def test_apply_entry_round_completed(self, apply_entry, HandState, LedgerRow):
        state = HandState()
        apply_entry(state, _row(LedgerRow, "e1", "BLIND_POSTED", "p1", 50))
        apply_entry(state, _row(LedgerRow, "e2", "ROUND_COMPLETED"))
        assert state.is_completed is True

    def test_apply_entry_reversal(self, apply_entry, HandState, LedgerRow):
        state = HandState()
        apply_entry(state, _row(LedgerRow, "e1", "BLIND_POSTED", "p1", 50))
        apply_entry(state, _row(LedgerRow, "e2", "BLIND_POSTED", "p2", 100))
        apply_entry(state, _row(LedgerRow, "e3", "ACTION_REVERSED", "p1", 50, original_entry_id="e1"))
        assert state.pot_total == 100
        assert "e1" in state.reversed_entry_ids
        assert state.players["p1"].is_action_reversed is True

    def test_apply_entry_payout(self, apply_entry, HandState, LedgerRow):
        state = HandState()
        apply_entry(state, _row(LedgerRow, "e1", "BLIND_POSTED", "p1", 50))
        apply_entry(state, _row(LedgerRow, "e2", "PAYOUT_AWARDED", "p1", 50))
        assert state.players["p1"].total_won == 50

    def test_incremental_matches_rebuild(self, ledger_mod, LedgerRow):
        entries = [
            _row(LedgerRow, "e1", "BLIND_POSTED", "p1", 50),
            _row(LedgerRow, "e2", "BLIND_POSTED", "p2", 100),
            _row(LedgerRow, "e3", "BET_PLACED", "p3", 100),
            _row(LedgerRow, "e4", "PAYOUT_AWARDED", "p2", 250),
            _row(LedgerRow, "e5", "ROUND_COMPLETED"),
        ]
        batch = ledger_mod.rebuild_hand_state(entries)
        incremental = ledger_mod.HandState()
        for e in entries:
            ledger_mod.apply_entry(incremental, e)

        assert incremental.pot_total == batch.pot_total
        assert incremental.entry_count == batch.entry_count
        assert incremental.is_completed == batch.is_completed
        for pid in batch.players:
            assert incremental.players[pid].total_committed == batch.players[pid].total_committed
            assert incremental.players[pid].total_won == batch.players[pid].total_won

class TestIncrementalReplay:
    def test_replay_hand_identical_results(self, replay_mod, LedgerRow):
        entries = [
            _row(LedgerRow, "e1", "BLIND_POSTED", "p1", 50),
            _row(LedgerRow, "e2", "BLIND_POSTED", "p2", 100),
            _row(LedgerRow, "e3", "BET_PLACED", "p1", 50),
            _row(LedgerRow, "e4", "ROUND_COMPLETED"),
        ]
        result = replay_mod.replay_hand(entries)
        assert len(result.steps) == 4
        assert result.steps[0].state_after.pot_total == 50
        assert result.steps[1].state_after.pot_total == 150
        assert result.steps[2].state_after.pot_total == 200
        assert result.final_state.pot_total == 200
        assert result.final_state.is_completed is True

class TestOptimisticConcurrency:
    def _make_round(self, Round, **overrides):
        defaults = dict(
            round_id="r1", game_id="g1", round_number=1,
            dealer_seat=1, small_blind_seat=2, big_blind_seat=3,
            small_blind_amount=50, big_blind_amount=100, ante_amount=0,
            status="ACTIVE", street="PRE_FLOP", pot_amount=150,
            current_highest_bet=100, minimum_raise_amount=100,
            is_action_closed=False, last_aggressor_seat=None,
            acting_player_id="p3", state_version=1,
        )
        defaults.update(overrides)
        return Round(**defaults)

    def _make_players(self, RoundPlayer):
        return [
            RoundPlayer(round_id="r1", player_id="p1", seat_number=1,
                        stack_remaining=950, committed_this_street=50,
                        committed_this_hand=50, has_folded=False,
                        is_all_in=False, is_active_in_hand=True),
            RoundPlayer(round_id="r1", player_id="p2", seat_number=2,
                        stack_remaining=900, committed_this_street=100,
                        committed_this_hand=100, has_folded=False,
                        is_all_in=False, is_active_in_hand=True),
            RoundPlayer(round_id="r1", player_id="p3", seat_number=3,
                        stack_remaining=1000, committed_this_street=0,
                        committed_this_hand=0, has_folded=False,
                        is_all_in=False, is_active_in_hand=True),
        ]

    def test_apply_action_bumps_version(self, pipeline_mod, Round, RoundPlayer):
        game_round = self._make_round(Round)
        players = self._make_players(RoundPlayer)
        pipeline_mod.apply_action(game_round, players, "p3", "CALL", 100)
        assert game_round.state_version == 2

    def test_stale_version_raises(self, pipeline_mod, exceptions_mod, Round, RoundPlayer):
        game_round = self._make_round(Round, state_version=5)
        players = self._make_players(RoundPlayer)
        with pytest.raises(exceptions_mod.StaleStateError):
            pipeline_mod.apply_action(
                game_round, players, "p3", "CALL", 100,
                expected_version=3,
            )

    def test_matching_version_succeeds(self, pipeline_mod, Round, RoundPlayer):
        game_round = self._make_round(Round, state_version=5)
        players = self._make_players(RoundPlayer)
        result = pipeline_mod.apply_action(
            game_round, players, "p3", "CALL", 100,
            expected_version=5,
        )
        assert result.action == "CALL"
        assert game_round.state_version == 6

    def test_no_expected_version_skips_check(self, pipeline_mod, Round, RoundPlayer):
        game_round = self._make_round(Round, state_version=99)
        players = self._make_players(RoundPlayer)
        result = pipeline_mod.apply_action(
            game_round, players, "p3", "FOLD", 0,
        )
        assert result.action == "FOLD"
        assert game_round.state_version == 100

class TestNewExceptions:
    def test_stale_state_error(self, exceptions_mod):
        err = exceptions_mod.StaleStateError("version mismatch")
        assert isinstance(err, exceptions_mod.DomainError)
        assert "version mismatch" in err.message

    def test_duplicate_action_error(self, exceptions_mod):
        err = exceptions_mod.DuplicateActionError("already applied")
        assert isinstance(err, exceptions_mod.DomainError)
        assert "already applied" in err.message

class TestRulesProfileWiring:
    def test_validate_bet_accepts_rules(self, validator_mod, rules_mod):
        ctx = validator_mod.HandContext(
            round_id="r1", status="ACTIVE", street="PRE_FLOP",
            acting_player_id="p1", current_highest_bet=0,
            minimum_raise_amount=100, is_action_closed=False,
            players=[
                validator_mod.PlayerState(
                    player_id="p1", seat_number=1,
                    stack_remaining=1000, committed_this_street=0,
                    committed_this_hand=0, has_folded=False,
                    is_all_in=False, is_active_in_hand=True,
                ),
            ],
        )
        result = validator_mod.validate_bet(
            ctx, "p1", "CHECK", 0,
            rules=rules_mod.NO_LIMIT_HOLDEM,
        )
        assert result.action == "CHECK"

    def test_transition_hand_state_accepts_rules(self, pipeline_mod, validator_mod, rules_mod):
        ctx = validator_mod.HandContext(
            round_id="r1", status="ACTIVE", street="PRE_FLOP",
            acting_player_id="p1", current_highest_bet=100,
            minimum_raise_amount=100, is_action_closed=False,
            players=[
                validator_mod.PlayerState(
                    player_id="p1", seat_number=1,
                    stack_remaining=1000, committed_this_street=0,
                    committed_this_hand=0, has_folded=False,
                    is_all_in=False, is_active_in_hand=True,
                ),
            ],
        )
        transition = pipeline_mod.transition_hand_state(
            ctx, "p1", "CALL", 100,
            last_aggressor_seat=None,
            rules=rules_mod.NO_LIMIT_HOLDEM,
        )
        assert transition.action == "CALL"

    def test_apply_action_accepts_rules(self, pipeline_mod, rules_mod, Round, RoundPlayer):
        game_round = Round(
            round_id="r1", game_id="g1", round_number=1,
            dealer_seat=1, small_blind_seat=2, big_blind_seat=3,
            small_blind_amount=50, big_blind_amount=100, ante_amount=0,
            status="ACTIVE", street="PRE_FLOP", pot_amount=150,
            current_highest_bet=100, minimum_raise_amount=100,
            is_action_closed=False, last_aggressor_seat=None,
            acting_player_id="p1", state_version=1,
        )
        players = [
            RoundPlayer(round_id="r1", player_id="p1", seat_number=1,
                        stack_remaining=950, committed_this_street=50,
                        committed_this_hand=50, has_folded=False,
                        is_all_in=False, is_active_in_hand=True),
        ]
        result = pipeline_mod.apply_action(
            game_round, players, "p1", "FOLD", 0,
            rules=rules_mod.NO_LIMIT_HOLDEM,
        )
        assert result.action == "FOLD"

class TestScenarioRunnerBlinds:
    def test_scenario_posts_correct_blinds(self, scenario_mod, pipeline_mod, Round, RoundPlayer):
        HandScenario = scenario_mod.HandScenario
        PlayerSetup = scenario_mod.PlayerSetup
        BlindSetup = scenario_mod.BlindSetup

        scenario = HandScenario(
            name="blind posting check",
            players=[
                PlayerSetup(player_id="p1", seat=1, stack=1000),
                PlayerSetup(player_id="p2", seat=2, stack=1000),
                PlayerSetup(player_id="p3", seat=3, stack=1000),
            ],
            blinds=BlindSetup(small=50, big=100),
            dealer_seat=1,
        )
        result = scenario_mod.run_scenario(
            scenario, pipeline_mod.apply_action, Round, RoundPlayer,
        )
        assert result.scenario_name == "blind posting check"
        assert result.actions_applied == 0

    def test_scenario_blinds_and_action(self, scenario_mod, pipeline_mod, Round, RoundPlayer):
        HandScenario = scenario_mod.HandScenario
        PlayerSetup = scenario_mod.PlayerSetup
        BlindSetup = scenario_mod.BlindSetup

        scenario = HandScenario(
            name="fold after blinds",
            players=[
                PlayerSetup(player_id="p1", seat=1, stack=1000),
                PlayerSetup(player_id="p2", seat=2, stack=1000),
                PlayerSetup(player_id="p3", seat=3, stack=1000),
            ],
            blinds=BlindSetup(small=50, big=100),
            dealer_seat=1,
        )
        scenario.add_action("p1", "FOLD", 0)
        scenario.expect_player_folded("p1")

        result = scenario_mod.run_scenario(
            scenario, pipeline_mod.apply_action, Round, RoundPlayer,
        )
        assert result.passed
        assert result.actions_applied == 1

    def test_scenario_with_ante(self, scenario_mod, pipeline_mod, Round, RoundPlayer):
        HandScenario = scenario_mod.HandScenario
        PlayerSetup = scenario_mod.PlayerSetup
        BlindSetup = scenario_mod.BlindSetup

        scenario = HandScenario(
            name="blinds+ante check",
            players=[
                PlayerSetup(player_id="p1", seat=1, stack=1000),
                PlayerSetup(player_id="p2", seat=2, stack=1000),
                PlayerSetup(player_id="p3", seat=3, stack=1000),
            ],
            blinds=BlindSetup(small=50, big=100, ante=10),
            dealer_seat=1,
        )
        scenario.expect_pot(180)

        result = scenario_mod.run_scenario(
            scenario, pipeline_mod.apply_action, Round, RoundPlayer,
        )
        assert result.passed

class TestTableRuntime:
    def _make_runtime(self, table_runtime_mod, num_seats=6, num_players=3):
        rt = table_runtime_mod.TableRuntime(game_id="g1")
        for i in range(1, num_seats + 1):
            pid = f"p{i}" if i <= num_players else None
            status = (
                table_runtime_mod.SeatStatus.ACTIVE if pid
                else table_runtime_mod.SeatStatus.EMPTY
            )
            rt.seats.append(table_runtime_mod.TableSeat(
                seat_number=i, player_id=pid,
                status=status, chip_count=1000 if pid else 0,
            ))
        return rt

    def test_start_session(self, table_runtime_mod):
        rt = self._make_runtime(table_runtime_mod)
        rt.start_session()
        assert rt.status == table_runtime_mod.TableStatus.RUNNING

    def test_start_session_requires_players(self, table_runtime_mod):
        rt = table_runtime_mod.TableRuntime(game_id="g1")
        rt.seats.append(table_runtime_mod.TableSeat(
            seat_number=1, player_id="p1",
            status=table_runtime_mod.SeatStatus.ACTIVE, chip_count=1000,
        ))
        with pytest.raises(table_runtime_mod.NotEnoughActivePlayers, match="at least 2"):
            rt.start_session()

    def test_pause_resume(self, table_runtime_mod):
        rt = self._make_runtime(table_runtime_mod)
        rt.start_session()
        rt.pause_session()
        assert rt.status == table_runtime_mod.TableStatus.PAUSED
        rt.resume_session()
        assert rt.status == table_runtime_mod.TableStatus.RUNNING

    def test_resume_non_paused_raises(self, table_runtime_mod):
        rt = self._make_runtime(table_runtime_mod)
        rt.start_session()
        with pytest.raises(table_runtime_mod.SessionNotPaused, match="paused"):
            rt.resume_session()

    def test_sit_out_sit_in(self, table_runtime_mod):
        rt = self._make_runtime(table_runtime_mod)
        rt.sit_out(1)
        assert rt.seats[0].status == table_runtime_mod.SeatStatus.SITTING_OUT
        assert len(rt.active_seats) == 2
        rt.sit_in(1)
        assert rt.seats[0].status == table_runtime_mod.SeatStatus.ACTIVE
        assert len(rt.active_seats) == 3

    def test_can_start_hand(self, table_runtime_mod):
        rt = self._make_runtime(table_runtime_mod)
        assert rt.can_start_hand() is False
        rt.start_session()
        assert rt.can_start_hand() is True

    def test_record_hand_completed(self, table_runtime_mod):
        rt = self._make_runtime(table_runtime_mod)
        rt.start_session()
        assert rt.hands_played == 0
        rt.record_hand_completed()
        assert rt.hands_played == 1
        assert rt.blind_clock.hands_at_level == 1
        assert rt.next_hand_number() == 2

    def test_finish_session(self, table_runtime_mod):
        rt = self._make_runtime(table_runtime_mod)
        rt.start_session()
        rt.finish_session()
        assert rt.status == table_runtime_mod.TableStatus.FINISHED

    def test_active_seats_property(self, table_runtime_mod):
        rt = self._make_runtime(table_runtime_mod, num_seats=6, num_players=4)
        assert len(rt.active_seats) == 4
        rt.sit_out(2)
        assert len(rt.active_seats) == 3

    def test_seated_count(self, table_runtime_mod):
        rt = self._make_runtime(table_runtime_mod, num_seats=6, num_players=3)
        assert rt.seated_count == 3

class TestBlindClock:
    def test_should_advance_by_hands(self, table_runtime_mod):
        clock = table_runtime_mod.BlindClock()
        assert clock.should_advance(hands_per_level=5) is False
        for _ in range(5):
            clock.record_hand()
        assert clock.should_advance(hands_per_level=5) is True

    def test_advance_resets(self, table_runtime_mod):
        clock = table_runtime_mod.BlindClock()
        for _ in range(5):
            clock.record_hand()
        new_level = clock.advance()
        assert new_level == 2
        assert clock.hands_at_level == 0
        assert clock.should_advance(hands_per_level=5) is False

    def test_should_advance_by_time(self, table_runtime_mod):
        from datetime import datetime, timedelta, timezone
        old_time = datetime.now(timezone.utc) - timedelta(seconds=600)
        clock = table_runtime_mod.BlindClock(level_started_at=old_time)
        assert clock.should_advance(seconds_per_level=300) is True
        assert clock.should_advance(seconds_per_level=900) is False

class TestAnteConfiguration:
    def _room_config(self, room_adapter_mod, *, antes_enabled: bool):
        return room_adapter_mod.RoomConfig(
            room_id="room-1",
            starting_dealer_seat=1,
            antes_enabled=antes_enabled,
            players=[],
            blind_levels=[],
        )

    def test_ante_is_zero_when_room_disables_antes(self, game_command_mod, room_adapter_mod):
        level = room_adapter_mod.BlindLevelConfig(
            level=1, small_blind=5, big_blind=10, ante=2,
        )
        room_config = self._room_config(room_adapter_mod, antes_enabled=False)
        assert game_command_mod.GameCommandService._ante_amount(room_config, level) == 0

    def test_ante_uses_blind_level_when_room_enables_antes(self, game_command_mod, room_adapter_mod):
        level = room_adapter_mod.BlindLevelConfig(
            level=1, small_blind=5, big_blind=10, ante=2,
        )
        room_config = self._room_config(room_adapter_mod, antes_enabled=True)
        assert game_command_mod.GameCommandService._ante_amount(room_config, level) == 2

class TestIdempotencyKey:
    def test_bet_has_idempotency_key(self, models_mod):
        bet = models_mod.Bet(
            bet_id="b1", round_id="r1", player_id="p1",
            action="CALL", amount=100, idempotency_key="idem-123",
        )
        assert bet.idempotency_key == "idem-123"

    def test_bet_idempotency_key_nullable(self, models_mod):
        bet = models_mod.Bet(
            bet_id="b2", round_id="r1", player_id="p1",
            action="FOLD", amount=0,
        )
        assert bet.idempotency_key is None
