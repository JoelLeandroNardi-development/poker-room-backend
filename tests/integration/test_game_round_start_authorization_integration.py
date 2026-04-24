from __future__ import annotations

import os
import uuid

import pytest

from tests.service_loader import load_service_app_module

os.environ.setdefault("GAME_DB", "sqlite+aiosqlite:///:memory:")
os.environ.setdefault("RABBIT_URL", "amqp://guest:guest@localhost:5672/")
os.environ.setdefault("EXCHANGE_NAME", "test_exchange")

PACKAGE = "integration_round_start_auth_app"


@pytest.fixture(scope="module")
def models_mod():
    return load_service_app_module(
        "game-service", "domain/models", package_name=PACKAGE, reload_modules=True,
    )


@pytest.fixture(scope="module")
def command_service_mod():
    return load_service_app_module(
        "game-service", "application/commands/game_command_service", package_name=PACKAGE,
    )


@pytest.fixture(scope="module")
def db_module(models_mod):
    return load_service_app_module(
        "game-service", "infrastructure/db", package_name=PACKAGE,
    )


@pytest.fixture
async def engine_and_tables(db_module):
    from sqlalchemy.ext.asyncio import create_async_engine

    engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(db_module.Base.metadata.create_all)
    yield engine
    await engine.dispose()


@pytest.fixture
async def session(engine_and_tables):
    from sqlalchemy.ext.asyncio import async_sessionmaker

    Session = async_sessionmaker(engine_and_tables, expire_on_commit=False)
    async with Session() as db:
        yield db


async def _seed_game_snapshot(
    session,
    models_mod,
    *,
    game_id: str,
    current_dealer_seat: int,
    current_small_blind_seat: int,
    current_big_blind_seat: int,
    players: list[tuple[str, int, int]],
):
    game = models_mod.Game(
        game_id=game_id,
        room_id=f"room-{game_id}",
        status="ACTIVE",
        current_blind_level=1,
        current_dealer_seat=current_dealer_seat,
        current_small_blind_seat=current_small_blind_seat,
        current_big_blind_seat=current_big_blind_seat,
        hands_played=0,
        hands_at_current_level=0,
    )
    snapshot = models_mod.RoomSnapshot(
        game_id=game_id,
        room_id=game.room_id,
        starting_dealer_seat=current_dealer_seat,
        antes_enabled=False,
    )
    snapshot_players = [
        models_mod.RoomSnapshotPlayer(
            game_id=game_id,
            player_id=player_id,
            seat_number=seat_number,
            chip_count=chip_count,
            is_active=True,
            is_eliminated=False,
        )
        for player_id, seat_number, chip_count in players
    ]
    blind_levels = [
        models_mod.RoomSnapshotBlindLevel(
            game_id=game_id,
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


async def _seed_active_round(session, models_mod, *, game_id: str):
    session.add(
        models_mod.Round(
            round_id=str(uuid.uuid4()),
            game_id=game_id,
            round_number=1,
            dealer_seat=2,
            small_blind_seat=3,
            big_blind_seat=1,
            small_blind_amount=5,
            big_blind_amount=10,
            ante_amount=0,
            status="ACTIVE",
            pot_amount=15,
            street="PRE_FLOP",
            acting_player_id="p2",
            current_highest_bet=10,
            minimum_raise_amount=10,
            is_action_closed=False,
            state_version=1,
        )
    )
    await session.flush()


@pytest.mark.integration
class TestStartRoundAuthorization:
    @pytest.mark.asyncio
    async def test_controller_can_start_round(self, session, models_mod, command_service_mod):
        game_id = str(uuid.uuid4())
        await _seed_game_snapshot(
            session,
            models_mod,
            game_id=game_id,
            current_dealer_seat=2,
            current_small_blind_seat=3,
            current_big_blind_seat=1,
            players=[("p1", 1, 100), ("p2", 2, 100), ("p3", 3, 100)],
        )

        service = command_service_mod.GameCommandService(session)
        response = await service.start_round(
            game_id,
            command_service_mod.StartRoundRequest(started_by_controller=True),
        )

        assert response.game_id == game_id
        assert response.dealer_seat == 2

    @pytest.mark.asyncio
    async def test_current_button_player_can_start_round(self, session, models_mod, command_service_mod):
        game_id = str(uuid.uuid4())
        await _seed_game_snapshot(
            session,
            models_mod,
            game_id=game_id,
            current_dealer_seat=2,
            current_small_blind_seat=3,
            current_big_blind_seat=1,
            players=[("p1", 1, 100), ("p2", 2, 100), ("p3", 3, 100)],
        )

        service = command_service_mod.GameCommandService(session)
        response = await service.start_round(
            game_id,
            command_service_mod.StartRoundRequest(started_by_player_id="p2"),
        )

        assert response.game_id == game_id
        assert response.dealer_seat == 2

    @pytest.mark.asyncio
    async def test_non_button_player_cannot_start_round(self, session, models_mod, command_service_mod):
        game_id = str(uuid.uuid4())
        await _seed_game_snapshot(
            session,
            models_mod,
            game_id=game_id,
            current_dealer_seat=2,
            current_small_blind_seat=3,
            current_big_blind_seat=1,
            players=[("p1", 1, 100), ("p2", 2, 100), ("p3", 3, 100)],
        )

        service = command_service_mod.GameCommandService(session)
        with pytest.raises(command_service_mod.RoundStartNotAllowed) as exc:
            await service.start_round(
                game_id,
                command_service_mod.StartRoundRequest(started_by_player_id="p1"),
            )

        assert exc.value.message == command_service_mod.ErrorMessage.ROUND_START_NOT_ALLOWED

    @pytest.mark.asyncio
    async def test_start_round_still_rejects_when_active_round_exists(
        self, session, models_mod, command_service_mod,
    ):
        game_id = str(uuid.uuid4())
        await _seed_game_snapshot(
            session,
            models_mod,
            game_id=game_id,
            current_dealer_seat=2,
            current_small_blind_seat=3,
            current_big_blind_seat=1,
            players=[("p1", 1, 100), ("p2", 2, 100), ("p3", 3, 100)],
        )
        await _seed_active_round(session, models_mod, game_id=game_id)

        service = command_service_mod.GameCommandService(session)
        with pytest.raises(command_service_mod.GameNotActive) as exc:
            await service.start_round(
                game_id,
                command_service_mod.StartRoundRequest(started_by_controller=True),
            )

        assert exc.value.message == command_service_mod.ErrorMessage.ROUND_ALREADY_ACTIVE