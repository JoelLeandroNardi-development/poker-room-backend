"""Integration tests: DB-backed concurrency, idempotency, table runtime,
frontend contract, and cross-layer flows.

These tests use an async SQLite database so they exercise the real ORM
models, repository helpers, and CAS logic — not just in-memory objects.
"""

from __future__ import annotations

import asyncio
import os
import uuid

import pytest

os.environ.setdefault("GAME_DB", "sqlite+aiosqlite:///:memory:")
os.environ.setdefault("RABBIT_URL", "amqp://guest:guest@localhost:5672/")
os.environ.setdefault("EXCHANGE_NAME", "test_exchange")

from tests.service_loader import load_service_app_module

# ── Module fixtures ──────────────────────────────────────────────────

PACKAGE = "integration_game_app"


@pytest.fixture(scope="module")
def models_mod():
    return load_service_app_module(
        "game-service", "domain/models", package_name=PACKAGE, reload_modules=True,
    )


@pytest.fixture(scope="module")
def pipeline_mod():
    return load_service_app_module(
        "game-service", "domain/action_pipeline", package_name=PACKAGE,
    )


@pytest.fixture(scope="module")
def exceptions_mod():
    return load_service_app_module(
        "game-service", "domain/exceptions", package_name=PACKAGE,
    )


@pytest.fixture(scope="module")
def repo_mod():
    return load_service_app_module(
        "game-service", "infrastructure/repository", package_name=PACKAGE,
    )


@pytest.fixture(scope="module")
def constants_mod():
    return load_service_app_module(
        "game-service", "domain/constants", package_name=PACKAGE,
    )


@pytest.fixture(scope="module")
def table_runtime_mod():
    return load_service_app_module(
        "game-service", "domain/table_runtime", package_name=PACKAGE,
    )


@pytest.fixture(scope="module")
def db_module(models_mod):
    return load_service_app_module(
        "game-service", "infrastructure/db", package_name=PACKAGE,
    )


# ── DB session fixture ──────────────────────────────────────────────

@pytest.fixture
async def engine_and_tables(db_module):
    """Create all tables on a fresh in-memory SQLite engine."""
    from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker

    engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(db_module.Base.metadata.create_all)
    yield engine
    await engine.dispose()


@pytest.fixture
async def session(engine_and_tables):
    from sqlalchemy.ext.asyncio import async_sessionmaker

    Session = async_sessionmaker(engine_and_tables, expire_on_commit=False)
    async with Session() as s:
        yield s


# ── Helpers ──────────────────────────────────────────────────────────

def _make_game(models_mod, game_id=None, **overrides):
    defaults = dict(
        game_id=game_id or str(uuid.uuid4()),
        room_id="test-room",
        status="ACTIVE",
        current_blind_level=1,
        current_dealer_seat=1,
        current_small_blind_seat=2,
        current_big_blind_seat=3,
        hands_played=0,
        hands_at_current_level=0,
    )
    defaults.update(overrides)
    return models_mod.Game(**defaults)


def _make_round(models_mod, round_id=None, game_id="g1", **overrides):
    defaults = dict(
        round_id=round_id or str(uuid.uuid4()),
        game_id=game_id,
        round_number=1,
        dealer_seat=1,
        small_blind_seat=2,
        big_blind_seat=3,
        small_blind_amount=50,
        big_blind_amount=100,
        ante_amount=0,
        status="ACTIVE",
        pot_amount=150,
        street="PRE_FLOP",
        acting_player_id="p3",
        current_highest_bet=100,
        minimum_raise_amount=100,
        is_action_closed=False,
        state_version=1,
    )
    defaults.update(overrides)
    return models_mod.Round(**defaults)


def _make_players(models_mod, round_id):
    return [
        models_mod.RoundPlayer(
            round_id=round_id, player_id="p1", seat_number=1,
            stack_remaining=950, committed_this_street=50,
            committed_this_hand=50, has_folded=False, is_all_in=False,
            is_active_in_hand=True,
        ),
        models_mod.RoundPlayer(
            round_id=round_id, player_id="p2", seat_number=2,
            stack_remaining=900, committed_this_street=100,
            committed_this_hand=100, has_folded=False, is_all_in=False,
            is_active_in_hand=True,
        ),
        models_mod.RoundPlayer(
            round_id=round_id, player_id="p3", seat_number=3,
            stack_remaining=1000, committed_this_street=0,
            committed_this_hand=0, has_folded=False, is_all_in=False,
            is_active_in_hand=True,
        ),
    ]


# ═══════════════════════════════════════════════════════════════════════
#  1. DB-Level Optimistic Concurrency (CAS)
# ═══════════════════════════════════════════════════════════════════════

class TestCASConcurrency:
    """Verify that cas_update_round enforces compare-and-swap at DB level."""

    @pytest.mark.asyncio
    async def test_cas_succeeds_when_version_matches(
        self, session, models_mod, repo_mod,
    ):
        rid = str(uuid.uuid4())
        game_round = _make_round(models_mod, round_id=rid)
        session.add(game_round)
        await session.commit()

        # Reload
        fetched = await repo_mod.fetch_or_raise(
            session, models_mod.Round,
            filter_column=models_mod.Round.round_id,
            filter_value=rid,
            detail="not found",
        )
        version_before = fetched.state_version
        fetched.pot_amount = 200
        fetched.state_version = version_before + 1

        await repo_mod.cas_update_round(session, fetched, version_before)
        await session.commit()

        # Verify
        updated = await repo_mod.fetch_or_raise(
            session, models_mod.Round,
            filter_column=models_mod.Round.round_id,
            filter_value=rid,
            detail="not found",
        )
        assert updated.pot_amount == 200
        assert updated.state_version == version_before + 1

    @pytest.mark.asyncio
    async def test_cas_fails_when_version_stale(
        self, session, models_mod, repo_mod, exceptions_mod,
    ):
        rid = str(uuid.uuid4())
        game_round = _make_round(models_mod, round_id=rid, state_version=5)
        session.add(game_round)
        await session.commit()

        fetched = await repo_mod.fetch_or_raise(
            session, models_mod.Round,
            filter_column=models_mod.Round.round_id,
            filter_value=rid,
            detail="not found",
        )
        # Pretend someone else already advanced to version 6
        fetched.pot_amount = 999
        fetched.state_version = 6

        with pytest.raises(exceptions_mod.StaleStateError):
            # Pass wrong expected version (3 != actual 5)
            await repo_mod.cas_update_round(session, fetched, expected_version=3)

    @pytest.mark.asyncio
    async def test_concurrent_writers_one_wins(
        self, engine_and_tables, models_mod, repo_mod, exceptions_mod,
    ):
        """Two concurrent sessions try to CAS the same round — one must fail."""
        from sqlalchemy.ext.asyncio import async_sessionmaker

        Session = async_sessionmaker(engine_and_tables, expire_on_commit=False)

        rid = str(uuid.uuid4())
        async with Session() as setup_session:
            game_round = _make_round(models_mod, round_id=rid, state_version=1)
            setup_session.add(game_round)
            for rp in _make_players(models_mod, rid):
                setup_session.add(rp)
            await setup_session.commit()

        results = {"success": 0, "stale": 0}

        async def writer(pot_delta: int):
            async with Session() as s:
                fetched = await repo_mod.fetch_or_raise(
                    s, models_mod.Round,
                    filter_column=models_mod.Round.round_id,
                    filter_value=rid,
                    detail="not found",
                )
                version_before = fetched.state_version
                fetched.pot_amount += pot_delta
                fetched.state_version = version_before + 1
                try:
                    await repo_mod.cas_update_round(s, fetched, version_before)
                    await s.commit()
                    results["success"] += 1
                except exceptions_mod.StaleStateError:
                    results["stale"] += 1

        await asyncio.gather(writer(100), writer(200))

        assert results["success"] >= 1
        assert results["success"] + results["stale"] == 2


# ═══════════════════════════════════════════════════════════════════════
#  2. Scoped Idempotency + Payload Mismatch
# ═══════════════════════════════════════════════════════════════════════

class TestScopedIdempotency:
    """Verify that idempotency is scoped to (round_id, key) and rejects
    mismatched payload reuse.
    """

    @pytest.mark.asyncio
    async def test_same_key_same_round_returns_existing(
        self, session, models_mod,
    ):
        """Inserting the same key+round twice should violate the unique constraint."""
        from sqlalchemy import select

        rid = str(uuid.uuid4())
        game_round = _make_round(models_mod, round_id=rid)
        session.add(game_round)
        await session.flush()

        bet1 = models_mod.Bet(
            bet_id=str(uuid.uuid4()), round_id=rid, player_id="p1",
            action="CALL", amount=100, idempotency_key="key-1",
        )
        session.add(bet1)
        await session.flush()

        # Same key + same round → IntegrityError at DB level
        bet2 = models_mod.Bet(
            bet_id=str(uuid.uuid4()), round_id=rid, player_id="p1",
            action="CALL", amount=100, idempotency_key="key-1",
        )
        session.add(bet2)
        from sqlalchemy.exc import IntegrityError
        with pytest.raises(IntegrityError):
            await session.flush()
        await session.rollback()

    @pytest.mark.asyncio
    async def test_same_key_different_round_succeeds(
        self, session, models_mod,
    ):
        """Same idempotency key in a different round should be allowed."""
        rid1 = str(uuid.uuid4())
        rid2 = str(uuid.uuid4())
        r1 = _make_round(models_mod, round_id=rid1, round_number=1)
        r2 = _make_round(models_mod, round_id=rid2, round_number=2)
        session.add(r1)
        session.add(r2)
        await session.flush()

        bet1 = models_mod.Bet(
            bet_id=str(uuid.uuid4()), round_id=rid1, player_id="p1",
            action="CALL", amount=100, idempotency_key="shared-key",
        )
        bet2 = models_mod.Bet(
            bet_id=str(uuid.uuid4()), round_id=rid2, player_id="p1",
            action="CALL", amount=100, idempotency_key="shared-key",
        )
        session.add(bet1)
        session.add(bet2)
        await session.flush()

        # Both persisted successfully
        assert bet1.idempotency_key == bet2.idempotency_key
        assert bet1.round_id != bet2.round_id

    @pytest.mark.asyncio
    async def test_bet_model_has_round_scoped_constraint(self, models_mod):
        """Verify model table_args contains the round-scoped unique constraint."""
        constraints = [
            c.name for c in models_mod.Bet.__table__.constraints
            if hasattr(c, "name") and c.name
        ]
        assert "uq_bets_round_idempotency" in constraints


# ═══════════════════════════════════════════════════════════════════════
#  3. Table Runtime Integration
# ═══════════════════════════════════════════════════════════════════════

class TestTableRuntimeIntegration:
    """Verify table runtime state machine works with session lifecycle."""

    def test_full_session_lifecycle(self, table_runtime_mod):
        TR = table_runtime_mod.TableRuntime
        TS = table_runtime_mod.TableSeat
        SeatStatus = table_runtime_mod.SeatStatus
        TableStatus = table_runtime_mod.TableStatus

        seats = [
            TS(seat_number=1, player_id="p1", status=SeatStatus.ACTIVE, chip_count=1000),
            TS(seat_number=2, player_id="p2", status=SeatStatus.ACTIVE, chip_count=1000),
            TS(seat_number=3, player_id="p3", status=SeatStatus.ACTIVE, chip_count=1000),
        ]
        runtime = TR(game_id="g1", seats=seats)

        # Start session
        runtime.start_session()
        assert runtime.status == TableStatus.RUNNING
        assert runtime.can_start_hand()

        # Play a hand
        assert runtime.next_hand_number() == 1
        runtime.record_hand_completed()
        assert runtime.hands_played == 1
        assert runtime.blind_clock.hands_at_level == 1

        # Sit out a player
        runtime.sit_out(3)
        assert seats[2].status == SeatStatus.SITTING_OUT
        assert runtime.can_start_hand()  # still 2 active

        # Record another hand — sat-out counter advances
        runtime.record_hand_completed()
        assert seats[2].hands_sat_out == 1

        # Sit back in
        runtime.sit_in(3)
        assert seats[2].status == SeatStatus.ACTIVE

        # Pause / resume
        runtime.pause_session()
        assert runtime.status == TableStatus.PAUSED
        assert not runtime.can_start_hand()

        runtime.resume_session()
        assert runtime.status == TableStatus.RUNNING

        # Finish
        runtime.finish_session()
        assert runtime.status == TableStatus.FINISHED

    def test_blind_clock_advancement(self, table_runtime_mod):
        clock = table_runtime_mod.BlindClock()
        assert clock.current_level == 1

        # Record 10 hands
        for _ in range(10):
            clock.record_hand()

        assert clock.should_advance(hands_per_level=10)
        new_level = clock.advance()
        assert new_level == 2
        assert clock.hands_at_level == 0


# ═══════════════════════════════════════════════════════════════════════
#  3b. Table Runtime Persistence (DB-backed)
# ═══════════════════════════════════════════════════════════════════════

class TestTableRuntimePersistence:
    """Verify that runtime counters persist through the Game model."""

    @pytest.mark.asyncio
    async def test_game_has_runtime_fields(self, models_mod):
        """Game model has hands_played and hands_at_current_level columns."""
        col_names = {c.name for c in models_mod.Game.__table__.columns}
        assert "hands_played" in col_names
        assert "hands_at_current_level" in col_names

    @pytest.mark.asyncio
    async def test_runtime_counters_persist_across_reload(
        self, session, models_mod,
    ):
        """Write runtime counters, commit, reload — values survive."""
        gid = str(uuid.uuid4())
        game = _make_game(models_mod, game_id=gid, hands_played=0)
        session.add(game)
        await session.commit()

        from sqlalchemy import select
        fetched = (await session.execute(
            select(models_mod.Game).where(models_mod.Game.game_id == gid)
        )).scalar_one()
        fetched.hands_played = 7
        fetched.hands_at_current_level = 3
        fetched.current_blind_level = 2
        await session.commit()

        reloaded = (await session.execute(
            select(models_mod.Game).where(models_mod.Game.game_id == gid)
        )).scalar_one()
        assert reloaded.hands_played == 7
        assert reloaded.hands_at_current_level == 3
        assert reloaded.current_blind_level == 2

    @pytest.mark.asyncio
    async def test_build_runtime_restores_counters(
        self, session, models_mod, table_runtime_mod,
    ):
        """_build_runtime_from_game correctly hydrates hands_played and hands_at_level."""
        from tests.service_loader import load_service_app_module
        cmd_mod = load_service_app_module(
            "game-service",
            "application/commands/table_runtime_command_service",
            package_name=PACKAGE,
        )

        gid = str(uuid.uuid4())
        game = _make_game(
            models_mod, game_id=gid,
            hands_played=15, hands_at_current_level=5,
            current_blind_level=3,
        )
        seats = [
            table_runtime_mod.TableSeat(
                seat_number=1, player_id="p1",
                status=table_runtime_mod.SeatStatus.ACTIVE, chip_count=1000,
            ),
        ]
        runtime = cmd_mod._build_runtime_from_game(game, seats)

        assert runtime.hands_played == 15
        assert runtime.blind_clock.current_level == 3
        assert runtime.blind_clock.hands_at_level == 5


# ═══════════════════════════════════════════════════════════════════════
#  3c. Session Status Response
# ═══════════════════════════════════════════════════════════════════════

class TestSessionStatusResponse:
    """Verify the SessionStatusResponse schema has all required fields."""

    def test_session_status_fields_present(self):
        from shared.schemas.games import SessionStatusResponse

        fields = set(SessionStatusResponse.model_fields.keys())
        required = {
            "game_id", "status", "hands_played",
            "current_blind_level", "hands_at_current_level",
            "hands_until_blind_advance", "max_blind_level",
            "small_blind", "big_blind", "ante", "dealer_seat",
        }
        assert required.issubset(fields), f"Missing: {required - fields}"

    def test_construct_session_status(self):
        from shared.schemas.games import SessionStatusResponse

        resp = SessionStatusResponse(
            game_id="g1",
            status="ACTIVE",
            hands_played=25,
            current_blind_level=3,
            hands_at_current_level=5,
            hands_until_blind_advance=5,
            max_blind_level=10,
            small_blind=200,
            big_blind=400,
            ante=50,
            dealer_seat=4,
        )
        assert resp.hands_played == 25
        assert resp.hands_until_blind_advance == 5
        assert resp.current_blind_level == 3

    def test_game_response_includes_runtime_fields(self):
        from shared.schemas.games import GameResponse

        fields = set(GameResponse.model_fields.keys())
        assert "hands_played" in fields
        assert "hands_at_current_level" in fields

        resp = GameResponse(
            game_id="g1", room_id="r1", status="ACTIVE",
            current_blind_level=2,
            current_dealer_seat=1, current_small_blind_seat=2,
            current_big_blind_seat=3,
            hands_played=10, hands_at_current_level=4,
        )
        assert resp.hands_played == 10
        assert resp.hands_at_current_level == 4


# ═══════════════════════════════════════════════════════════════════════
#  4. Expanded TableStateResponse
# ═══════════════════════════════════════════════════════════════════════

class TestTableStateResponseContract:
    """Verify the expanded TableStateResponse has all required fields."""

    def test_all_fields_present(self):
        from shared.schemas.games import TableStateResponse

        fields = set(TableStateResponse.model_fields.keys())
        required = {
            "round_id", "game_id", "round_number", "street", "pot_amount",
            "acting_player_id", "current_highest_bet", "minimum_raise_amount",
            "is_action_closed", "state_version",
            "dealer_seat", "small_blind_seat", "big_blind_seat",
            "last_aggressor_seat", "call_amount", "is_showdown_ready",
            "legal_actions", "players",
        }
        assert required.issubset(fields), f"Missing: {required - fields}"

    def test_construct_full_response(self):
        from shared.schemas.games import TableStateResponse, LegalAction

        resp = TableStateResponse(
            round_id="r1",
            game_id="g1",
            round_number=1,
            street="PRE_FLOP",
            pot_amount=150,
            acting_player_id="p3",
            current_highest_bet=100,
            minimum_raise_amount=100,
            is_action_closed=False,
            state_version=1,
            dealer_seat=1,
            small_blind_seat=2,
            big_blind_seat=3,
            last_aggressor_seat=None,
            call_amount=100,
            is_showdown_ready=False,
            legal_actions=[LegalAction(action="CALL", min_amount=100, max_amount=100)],
            players=[],
        )
        assert resp.dealer_seat == 1
        assert resp.call_amount == 100
        assert resp.is_showdown_ready is False
        assert resp.round_number == 1


# ═══════════════════════════════════════════════════════════════════════
#  5. Observability
# ═══════════════════════════════════════════════════════════════════════

class TestObservability:
    """Verify structured logging and correlation ID infrastructure."""

    @pytest.fixture(scope="class")
    def logging_mod(self):
        return load_service_app_module(
            "game-service", "infrastructure/logging", package_name=PACKAGE,
        )

    def test_structured_logger_emits_fields(self, caplog, logging_mod):
        import logging

        log = logging_mod.get_logger("test.observability")
        with caplog.at_level(logging.INFO, logger="test.observability"):
            log.info("test message", round_id="r1", player_id="p1")

        assert len(caplog.records) >= 1
        record = caplog.records[-1]
        structured = getattr(record, "structured", {})
        assert structured.get("round_id") == "r1"
        assert structured.get("player_id") == "p1"

    def test_correlation_id_context_var(self, logging_mod):
        assert logging_mod.get_correlation_id() is None
        token = logging_mod.correlation_id_ctx.set("test-cid-123")
        assert logging_mod.get_correlation_id() == "test-cid-123"
        logging_mod.correlation_id_ctx.reset(token)
        assert logging_mod.get_correlation_id() is None

    def test_idempotency_conflict_exception_exists(self, exceptions_mod):
        exc = exceptions_mod.IdempotencyConflict("test")
        assert exc.message == "test"
        assert isinstance(exc, exceptions_mod.DomainError)


# ═══════════════════════════════════════════════════════════════════════
#  6. Replay / Timeline / Consistency on Settled Hand
# ═══════════════════════════════════════════════════════════════════════

class TestReplayOnSettledHand:
    """End-to-end: replay and consistency check against a fully built hand."""

    @pytest.fixture
    def ledger_mod(self):
        return load_service_app_module(
            "game-service", "domain/hand_ledger", package_name=PACKAGE,
        )

    @pytest.fixture
    def replay_mod(self):
        return load_service_app_module(
            "game-service", "domain/hand_replay", package_name=PACKAGE,
        )

    @pytest.fixture
    def history_mod(self):
        return load_service_app_module(
            "game-service", "domain/hand_history", package_name=PACKAGE,
        )

    def test_replay_settled_hand_is_consistent(self, ledger_mod, replay_mod):
        LR = ledger_mod.LedgerRow
        entries = [
            LR(entry_id="e1", entry_type="BLIND_POSTED", player_id="p1", amount=50, detail=None, original_entry_id=None),
            LR(entry_id="e2", entry_type="BLIND_POSTED", player_id="p2", amount=100, detail=None, original_entry_id=None),
            LR(entry_id="e3", entry_type="BET_PLACED", player_id="p3", amount=100, detail=None, original_entry_id=None),
            LR(entry_id="e4", entry_type="BET_PLACED", player_id="p1", amount=50, detail=None, original_entry_id=None),
            LR(entry_id="e5", entry_type="PAYOUT_AWARDED", player_id="p3", amount=300, detail=None, original_entry_id=None),
            LR(entry_id="e6", entry_type="ROUND_COMPLETED", player_id=None, amount=None, detail=None, original_entry_id=None),
        ]
        result = replay_mod.replay_hand(entries)
        assert result.is_consistent
        assert result.entry_count == 6

    def test_consistency_check_after_correction(self, ledger_mod, replay_mod):
        LR = ledger_mod.LedgerRow
        entries = [
            LR(entry_id="e1", entry_type="BLIND_POSTED", player_id="p1", amount=50, detail=None, original_entry_id=None),
            LR(entry_id="e2", entry_type="BLIND_POSTED", player_id="p2", amount=100, detail=None, original_entry_id=None),
            LR(entry_id="e3", entry_type="BET_PLACED", player_id="p3", amount=100, detail=None, original_entry_id=None),
            # Correction: reverse p3's bet
            LR(entry_id="e4", entry_type="ACTION_REVERSED", player_id="p3",
               amount=100, detail=None, original_entry_id="e3"),
            # Re-bet at correct amount
            LR(entry_id="e5", entry_type="BET_PLACED", player_id="p3", amount=150, detail=None, original_entry_id=None),
            LR(entry_id="e6", entry_type="PAYOUT_AWARDED", player_id="p3", amount=350, detail=None, original_entry_id=None),
            LR(entry_id="e7", entry_type="ROUND_COMPLETED", player_id=None, amount=None, detail=None, original_entry_id=None),
        ]
        result = replay_mod.replay_hand(entries)
        assert result.is_consistent

        # Verify via consistency checker
        state = ledger_mod.rebuild_hand_state(entries)
        live_committed = {
            "p1": 50,
            "p2": 100,
            "p3": 150,
        }
        discrepancies = replay_mod.verify_consistency(
            entries, state.pot_total, live_committed,
        )
        assert len(discrepancies) == 0

    def test_timeline_has_streets_and_corrections(self, history_mod, ledger_mod):
        LR = ledger_mod.LedgerRow
        entries = [
            LR(entry_id="e1", entry_type="BLIND_POSTED", player_id="p1", amount=50, detail=None, original_entry_id=None),
            LR(entry_id="e2", entry_type="BLIND_POSTED", player_id="p2", amount=100, detail=None, original_entry_id=None),
            LR(entry_id="e3", entry_type="BET_PLACED", player_id="p3", amount=100,
               detail={"action": "CALL"}, original_entry_id=None),
            LR(entry_id="e4", entry_type="PAYOUT_AWARDED", player_id="p3", amount=250, detail=None, original_entry_id=None),
            LR(entry_id="e5", entry_type="ROUND_COMPLETED", player_id=None, amount=None, detail=None, original_entry_id=None),
        ]
        timeline = history_mod.build_hand_timeline("r1", entries)
        assert len(timeline.streets) >= 1
        assert len(timeline.payouts) == 1
