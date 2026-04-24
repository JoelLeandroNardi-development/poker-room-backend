"""Postgres-backed integration tests for CAS and idempotency paths.

These tests exercise the real Postgres locking / transaction isolation
behaviour that SQLite-in-memory cannot fully replicate.  They require
a running PostgreSQL instance (docker-compose up postgres).

Run explicitly with:
    pytest tests/integration/test_postgres_concurrency.py -m postgres

Skipped automatically when no Postgres connection is available.
"""

from __future__ import annotations

import asyncio
import os
import uuid

import pytest

PG_URL = os.environ.get(
    "GAME_DB_PG",
    "postgresql+asyncpg://poker:poker@localhost:5432/game_db",
)

_pg_available: bool | None = None

def _check_pg() -> bool:
    global _pg_available
    if _pg_available is not None:
        return _pg_available
    try:
        import asyncpg  # noqa: F401
    except ImportError:
        _pg_available = False
        return False
    try:
        loop = asyncio.new_event_loop()
        loop.run_until_complete(_try_connect())
        loop.close()
        _pg_available = True
    except Exception:
        _pg_available = False
    return _pg_available

async def _try_connect():
    from sqlalchemy.ext.asyncio import create_async_engine

    engine = create_async_engine(PG_URL, echo=False)
    async with engine.connect() as conn:
        await conn.execute(
            __import__("sqlalchemy").text("SELECT 1")
        )
    await engine.dispose()

requires_postgres = pytest.mark.skipif(
    not _check_pg(),
    reason="PostgreSQL not available (set GAME_DB_PG or run docker-compose up postgres)",
)

os.environ.setdefault("GAME_DB", "sqlite+aiosqlite:///:memory:")
os.environ.setdefault("RABBIT_URL", "amqp://guest:guest@localhost:5672/")
os.environ.setdefault("EXCHANGE_NAME", "test_exchange")

from tests.service_loader import load_service_app_module

PACKAGE = "pg_integration_app"

@pytest.fixture(scope="module")
def models_mod():
    return load_service_app_module(
        "game-service", "domain/models", package_name=PACKAGE, reload_modules=True,
    )

@pytest.fixture(scope="module")
def game_repo_mod():
    return load_service_app_module(
        "game-service", "infrastructure/repositories/game_repository", package_name=PACKAGE,
    )

@pytest.fixture(scope="module")
def round_state_repo_mod():
    return load_service_app_module(
        "game-service", "infrastructure/repositories/round_state_repository", package_name=PACKAGE,
    )

@pytest.fixture(scope="module")
def exceptions_mod():
    return load_service_app_module(
        "game-service", "domain/exceptions", package_name=PACKAGE,
    )

@pytest.fixture(scope="module")
def db_module(models_mod):
    return load_service_app_module(
        "game-service", "infrastructure/db", package_name=PACKAGE,
    )

@pytest.fixture(scope="module")
def command_service_mod():
    return load_service_app_module(
        "game-service", "application/commands/game_command_service", package_name=PACKAGE,
    )

@pytest.fixture(scope="module")
async def pg_engine(db_module):
    from sqlalchemy.ext.asyncio import create_async_engine

    engine = create_async_engine(PG_URL, echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(db_module.Base.metadata.create_all)
    yield engine
    # Drop all test tables to leave DB clean
    async with engine.begin() as conn:
        await conn.run_sync(db_module.Base.metadata.drop_all)
    await engine.dispose()

@pytest.fixture
async def session(pg_engine):
    from sqlalchemy.ext.asyncio import async_sessionmaker

    Session = async_sessionmaker(pg_engine, expire_on_commit=False)
    async with Session() as s:
        yield s
        await s.rollback()

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

@requires_postgres
@pytest.mark.postgres
class TestPostgresCAS:
    @pytest.mark.asyncio
    async def test_cas_success_under_postgres(
        self, session, models_mod, game_repo_mod, round_state_repo_mod,
    ):
        gid = str(uuid.uuid4())
        game = _make_game(models_mod, game_id=gid)
        session.add(game)
        await session.flush()

        rid = str(uuid.uuid4())
        game_round = _make_round(models_mod, round_id=rid, game_id=gid)
        session.add(game_round)
        await session.commit()

        fetched = await game_repo_mod.fetch_or_raise(
            session, models_mod.Round,
            filter_column=models_mod.Round.round_id,
            filter_value=rid,
            detail="not found",
        )
        version_before = fetched.state_version
        fetched.pot_amount = 300
        fetched.state_version = version_before + 1

        await round_state_repo_mod.cas_update_round(session, fetched, version_before)
        await session.commit()

        updated = await game_repo_mod.fetch_or_raise(
            session, models_mod.Round,
            filter_column=models_mod.Round.round_id,
            filter_value=rid,
            detail="not found",
        )
        assert updated.pot_amount == 300
        assert updated.state_version == version_before + 1

    @pytest.mark.asyncio
    async def test_cas_rejects_stale_version(
        self, session, models_mod, game_repo_mod, round_state_repo_mod, exceptions_mod,
    ):
        gid = str(uuid.uuid4())
        game = _make_game(models_mod, game_id=gid)
        session.add(game)
        await session.flush()

        rid = str(uuid.uuid4())
        game_round = _make_round(
            models_mod, round_id=rid, game_id=gid, state_version=5,
        )
        session.add(game_round)
        await session.commit()

        fetched = await game_repo_mod.fetch_or_raise(
            session, models_mod.Round,
            filter_column=models_mod.Round.round_id,
            filter_value=rid,
            detail="not found",
        )
        fetched.pot_amount = 999
        fetched.state_version = 6

        with pytest.raises(exceptions_mod.StaleStateError):
            await round_state_repo_mod.cas_update_round(session, fetched, expected_version=3)

    @pytest.mark.asyncio
    async def test_concurrent_cas_one_wins_postgres(
        self, pg_engine, models_mod, game_repo_mod, round_state_repo_mod, exceptions_mod,
    ):
        from sqlalchemy.ext.asyncio import async_sessionmaker

        Session = async_sessionmaker(pg_engine, expire_on_commit=False)

        gid = str(uuid.uuid4())
        rid = str(uuid.uuid4())
        async with Session() as setup:
            game = _make_game(models_mod, game_id=gid)
            setup.add(game)
            await setup.flush()
            game_round = _make_round(
                models_mod, round_id=rid, game_id=gid, state_version=1,
            )
            setup.add(game_round)
            await setup.commit()

        results = {"success": 0, "stale": 0}

        async def writer(pot_delta: int):
            async with Session() as s:
                fetched = await game_repo_mod.fetch_or_raise(
                    s, models_mod.Round,
                    filter_column=models_mod.Round.round_id,
                    filter_value=rid,
                    detail="not found",
                )
                version_before = fetched.state_version
                fetched.pot_amount += pot_delta
                fetched.state_version = version_before + 1
                try:
                    await round_state_repo_mod.cas_update_round(s, fetched, version_before)
                    await s.commit()
                    results["success"] += 1
                except exceptions_mod.StaleStateError:
                    results["stale"] += 1

        await asyncio.gather(writer(100), writer(200))

        assert results["success"] >= 1
        assert results["success"] + results["stale"] == 2

        # Verify the winning write is consistent
        async with Session() as s:
            final = await game_repo_mod.fetch_or_raise(
                s, models_mod.Round,
                filter_column=models_mod.Round.round_id,
                filter_value=rid,
                detail="not found",
            )
            assert final.state_version == 2
            assert final.pot_amount in (250, 350)  # 150+100 or 150+200

@requires_postgres
@pytest.mark.postgres
class TestPostgresIdempotency:
    @pytest.mark.asyncio
    async def test_duplicate_key_same_round_rejected(
        self, session, models_mod,
    ):
        from sqlalchemy.exc import IntegrityError

        gid = str(uuid.uuid4())
        game = _make_game(models_mod, game_id=gid)
        session.add(game)
        await session.flush()

        rid = str(uuid.uuid4())
        game_round = _make_round(models_mod, round_id=rid, game_id=gid)
        session.add(game_round)
        await session.flush()

        bet1 = models_mod.Bet(
            bet_id=str(uuid.uuid4()), round_id=rid, player_id="p1",
            action="CALL", amount=100, idempotency_key="key-dup",
        )
        session.add(bet1)
        await session.flush()

        bet2 = models_mod.Bet(
            bet_id=str(uuid.uuid4()), round_id=rid, player_id="p1",
            action="CALL", amount=100, idempotency_key="key-dup",
        )
        session.add(bet2)
        with pytest.raises(IntegrityError):
            await session.flush()
        await session.rollback()

    @pytest.mark.asyncio
    async def test_same_key_different_rounds_allowed(
        self, session, models_mod,
    ):
        gid = str(uuid.uuid4())
        game = _make_game(models_mod, game_id=gid)
        session.add(game)
        await session.flush()

        rid1 = str(uuid.uuid4())
        rid2 = str(uuid.uuid4())
        r1 = _make_round(models_mod, round_id=rid1, game_id=gid, round_number=1)
        r2 = _make_round(models_mod, round_id=rid2, game_id=gid, round_number=2)
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

        assert bet1.round_id != bet2.round_id
        assert bet1.idempotency_key == bet2.idempotency_key

    @pytest.mark.asyncio
    async def test_concurrent_duplicate_inserts(
        self, pg_engine, models_mod,
    ):
        from sqlalchemy.ext.asyncio import async_sessionmaker
        from sqlalchemy.exc import IntegrityError

        Session = async_sessionmaker(pg_engine, expire_on_commit=False)

        gid = str(uuid.uuid4())
        rid = str(uuid.uuid4())
        async with Session() as setup:
            game = _make_game(models_mod, game_id=gid)
            setup.add(game)
            await setup.flush()
            r = _make_round(models_mod, round_id=rid, game_id=gid)
            setup.add(r)
            await setup.commit()

        results = {"success": 0, "rejected": 0}

        async def inserter(player_id: str):
            async with Session() as s:
                bet = models_mod.Bet(
                    bet_id=str(uuid.uuid4()), round_id=rid,
                    player_id=player_id, action="CALL", amount=100,
                    idempotency_key="race-key",
                )
                s.add(bet)
                try:
                    await s.commit()
                    results["success"] += 1
                except IntegrityError:
                    results["rejected"] += 1

        await asyncio.gather(inserter("p1"), inserter("p2"))

        assert results["success"] == 1
        assert results["rejected"] == 1

@requires_postgres
@pytest.mark.postgres
class TestPostgresRuntimePersistence:
    @pytest.mark.asyncio
    async def test_hands_played_survives_commit(
        self, session, models_mod,
    ):
        gid = str(uuid.uuid4())
        game = _make_game(models_mod, game_id=gid, hands_played=0)
        session.add(game)
        await session.commit()

        fetched = await fetch_game_row(session, models_mod, gid)
        fetched.hands_played = 5
        fetched.hands_at_current_level = 5
        await session.commit()

        reloaded = await fetch_game_row(session, models_mod, gid)
        assert reloaded.hands_played == 5
        assert reloaded.hands_at_current_level == 5

    @pytest.mark.asyncio
    async def test_blind_advancement_persisted(
        self, session, models_mod,
    ):
        gid = str(uuid.uuid4())
        game = _make_game(
            models_mod, game_id=gid,
            hands_played=9, hands_at_current_level=9,
            current_blind_level=1,
        )
        session.add(game)
        await session.commit()

        fetched = await fetch_game_row(session, models_mod, gid)
        fetched.hands_played = 10
        fetched.hands_at_current_level = 0
        fetched.current_blind_level = 2
        await session.commit()

        reloaded = await fetch_game_row(session, models_mod, gid)
        assert reloaded.current_blind_level == 2
        assert reloaded.hands_at_current_level == 0
        assert reloaded.hands_played == 10

@requires_postgres
@pytest.mark.postgres
class TestPostgresRoundStart:
    @pytest.mark.asyncio
    async def test_start_round_persists_round_before_ledger_entries(
        self, db_module, models_mod, command_service_mod,
    ):
        from sqlalchemy import select
        from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

        gid = str(uuid.uuid4())
        engine = create_async_engine(PG_URL, echo=False)

        try:
            async with engine.begin() as conn:
                await conn.run_sync(db_module.Base.metadata.create_all)

            Session = async_sessionmaker(engine, expire_on_commit=False)
            async with Session() as session:
                game = _make_game(
                    models_mod,
                    game_id=gid,
                    current_dealer_seat=1,
                    current_small_blind_seat=1,
                    current_big_blind_seat=2,
                )
                snapshot = models_mod.RoomSnapshot(
                    game_id=gid,
                    room_id=game.room_id,
                    starting_dealer_seat=1,
                    antes_enabled=False,
                )
                snapshot_players = [
                    models_mod.RoomSnapshotPlayer(
                        game_id=gid,
                        player_id="p1",
                        seat_number=1,
                        chip_count=200,
                        is_active=True,
                        is_eliminated=False,
                    ),
                    models_mod.RoomSnapshotPlayer(
                        game_id=gid,
                        player_id="p2",
                        seat_number=2,
                        chip_count=200,
                        is_active=True,
                        is_eliminated=False,
                    ),
                ]
                blind_levels = [
                    models_mod.RoomSnapshotBlindLevel(
                        game_id=gid,
                        level=1,
                        small_blind=5,
                        big_blind=10,
                        ante=0,
                        duration_minutes=15,
                    )
                ]

                session.add(game)
                session.add(snapshot)
                session.add_all(snapshot_players)
                session.add_all(blind_levels)
                await session.flush()

                service = command_service_mod.GameCommandService(session)
                response = await service.start_round(
                    gid,
                    command_service_mod.StartRoundRequest(started_by_controller=True),
                )

                round_row = (
                    await session.execute(
                        select(models_mod.Round).where(models_mod.Round.round_id == response.round_id)
                    )
                ).scalar_one()
                ledger_rows = (
                    await session.execute(
                        select(models_mod.HandLedgerEntry)
                        .where(models_mod.HandLedgerEntry.round_id == response.round_id)
                    )
                ).scalars().all()

                assert round_row.round_id == response.round_id
                assert round_row.pot_amount == 15
                assert len(ledger_rows) == 2
                assert {
                    (row.entry_type, row.player_id, row.amount)
                    for row in ledger_rows
                } == {
                    ("BLIND_POSTED", "p1", 5),
                    ("BLIND_POSTED", "p2", 10),
                }
        finally:
            await engine.dispose()

async def fetch_game_row(session, models_mod, game_id):
    from sqlalchemy import select
    res = await session.execute(
        select(models_mod.Game).where(models_mod.Game.game_id == game_id)
    )
    return res.scalar_one()