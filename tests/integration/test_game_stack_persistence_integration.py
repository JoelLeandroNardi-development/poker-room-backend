from __future__ import annotations

import os
import uuid

import pytest
from sqlalchemy import select

from tests.service_loader import load_service_app_module

os.environ.setdefault("GAME_DB", "sqlite+aiosqlite:///:memory:")
os.environ.setdefault("RABBIT_URL", "amqp://guest:guest@localhost:5672/")
os.environ.setdefault("EXCHANGE_NAME", "test_exchange")

PACKAGE = "integration_stack_persistence_app"


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
    seats: list[tuple[str, int, int]],
    positions: tuple[int, int, int],
    blind_amounts: tuple[int, int, int] = (5, 10, 0),
):
    dealer_seat, small_blind_seat, big_blind_seat = positions
    small_blind, big_blind, ante = blind_amounts

    game = models_mod.Game(
        game_id=game_id,
        room_id=f"room-{game_id}",
        status="ACTIVE",
        current_blind_level=1,
        current_dealer_seat=dealer_seat,
        current_small_blind_seat=small_blind_seat,
        current_big_blind_seat=big_blind_seat,
        hands_played=0,
        hands_at_current_level=0,
    )
    snapshot = models_mod.RoomSnapshot(
        game_id=game_id,
        room_id=game.room_id,
        starting_dealer_seat=dealer_seat,
        antes_enabled=ante > 0,
    )
    snapshot_players = [
        models_mod.RoomSnapshotPlayer(
            game_id=game_id,
            player_id=player_id,
            seat_number=seat_number,
            chip_count=chip_count,
            is_active=chip_count > 0,
            is_eliminated=chip_count <= 0,
        )
        for player_id, seat_number, chip_count in seats
    ]
    blind_levels = [
        models_mod.RoomSnapshotBlindLevel(
            game_id=game_id,
            level=1,
            small_blind=small_blind,
            big_blind=big_blind,
            ante=ante,
            duration_minutes=15,
        )
    ]

    session.add(game)
    session.add(snapshot)
    session.add_all(snapshot_players)
    session.add_all(blind_levels)
    await session.flush()
    return game


async def _seed_round(
    session,
    models_mod,
    *,
    game_id: str,
    round_id: str,
    positions: tuple[int, int, int],
    pot_amount: int,
    players: list[tuple[str, int, int, int]],
):
    dealer_seat, small_blind_seat, big_blind_seat = positions
    game_round = models_mod.Round(
        round_id=round_id,
        game_id=game_id,
        round_number=1,
        dealer_seat=dealer_seat,
        small_blind_seat=small_blind_seat,
        big_blind_seat=big_blind_seat,
        small_blind_amount=5,
        big_blind_amount=10,
        ante_amount=0,
        status="ACTIVE",
        pot_amount=pot_amount,
        street="SHOWDOWN",
        acting_player_id=None,
        current_highest_bet=max((committed for _player_id, _seat, _stack, committed in players), default=0),
        minimum_raise_amount=10,
        is_action_closed=True,
        state_version=1,
    )
    round_players = [
        models_mod.RoundPlayer(
            round_id=round_id,
            player_id=player_id,
            seat_number=seat_number,
            stack_remaining=stack_remaining,
            committed_this_street=committed_this_hand,
            committed_this_hand=committed_this_hand,
            has_folded=False,
            is_all_in=stack_remaining <= 0,
            is_active_in_hand=True,
        )
        for player_id, seat_number, stack_remaining, committed_this_hand in players
    ]

    session.add(game_round)
    session.add_all(round_players)
    await session.flush()
    return game_round


async def _load_snapshot_players(session, models_mod, game_id: str):
    result = await session.execute(
        select(models_mod.RoomSnapshotPlayer)
        .where(models_mod.RoomSnapshotPlayer.game_id == game_id)
        .order_by(models_mod.RoomSnapshotPlayer.seat_number.asc())
    )
    return result.scalars().all()


async def _load_round_players(session, models_mod, round_id: str):
    result = await session.execute(
        select(models_mod.RoundPlayer)
        .where(models_mod.RoundPlayer.round_id == round_id)
        .order_by(models_mod.RoundPlayer.seat_number.asc())
    )
    return result.scalars().all()


async def _load_game(session, models_mod, game_id: str):
    result = await session.execute(
        select(models_mod.Game).where(models_mod.Game.game_id == game_id)
    )
    return result.scalar_one()


@pytest.mark.integration
class TestHandToHandStackPersistence:
    @pytest.mark.asyncio
    async def test_resolving_hand_updates_room_snapshot_player_chip_counts(
        self, session, models_mod, command_service_mod,
    ):
        game_id = str(uuid.uuid4())
        round_id = str(uuid.uuid4())
        await _seed_game_snapshot(
            session,
            models_mod,
            game_id=game_id,
            seats=[("p1", 1, 100), ("p2", 2, 100), ("p3", 3, 50)],
            positions=(1, 2, 3),
        )
        await _seed_round(
            session,
            models_mod,
            game_id=game_id,
            round_id=round_id,
            positions=(1, 2, 3),
            pot_amount=150,
            players=[
                ("p1", 1, 50, 50),
                ("p2", 2, 50, 50),
                ("p3", 3, 0, 50),
            ],
        )

        service = command_service_mod.GameCommandService(session)
        await service.resolve_hand(
            round_id,
            command_service_mod.ResolveHandRequest(
                payouts=[
                    {
                        "pot_index": 0,
                        "pot_type": "main",
                        "amount": 150,
                        "winners": [{"player_id": "p1", "amount": 150}],
                    }
                ]
            ),
        )

        snapshot_players = {
            player.player_id: player
            for player in await _load_snapshot_players(session, models_mod, game_id)
        }

        assert snapshot_players["p1"].chip_count == 200
        assert snapshot_players["p1"].is_active is True
        assert snapshot_players["p1"].is_eliminated is False
        assert snapshot_players["p2"].chip_count == 50
        assert snapshot_players["p2"].is_active is True
        assert snapshot_players["p2"].is_eliminated is False
        assert snapshot_players["p3"].chip_count == 0
        assert snapshot_players["p3"].is_active is False
        assert snapshot_players["p3"].is_eliminated is True

    @pytest.mark.asyncio
    async def test_starting_next_round_uses_previous_hand_final_stacks(
        self, session, models_mod, command_service_mod,
    ):
        game_id = str(uuid.uuid4())
        round_id = str(uuid.uuid4())
        await _seed_game_snapshot(
            session,
            models_mod,
            game_id=game_id,
            seats=[("p1", 1, 100), ("p2", 2, 100), ("p3", 3, 50)],
            positions=(1, 2, 3),
        )
        await _seed_round(
            session,
            models_mod,
            game_id=game_id,
            round_id=round_id,
            positions=(1, 2, 3),
            pot_amount=150,
            players=[
                ("p1", 1, 50, 50),
                ("p2", 2, 50, 50),
                ("p3", 3, 50, 50),
            ],
        )

        service = command_service_mod.GameCommandService(session)
        await service.resolve_hand(
            round_id,
            command_service_mod.ResolveHandRequest(
                payouts=[
                    {
                        "pot_index": 0,
                        "pot_type": "main",
                        "amount": 150,
                        "winners": [{"player_id": "p3", "amount": 150}],
                    }
                ]
            ),
        )
        next_round = await service.start_round(
            game_id,
            command_service_mod.StartRoundRequest(started_by_controller=True),
        )

        next_round_players = {
            player.player_id: player
            for player in await _load_round_players(session, models_mod, next_round.round_id)
        }

        assert next_round_players["p1"].stack_remaining == 40
        assert next_round_players["p1"].committed_this_hand == 10
        assert next_round_players["p2"].stack_remaining == 50
        assert next_round_players["p2"].committed_this_hand == 0
        assert next_round_players["p3"].stack_remaining == 195
        assert next_round_players["p3"].committed_this_hand == 5

    @pytest.mark.asyncio
    async def test_busted_players_are_excluded_from_next_hand_position_rotation(
        self, session, models_mod, command_service_mod,
    ):
        game_id = str(uuid.uuid4())
        round_id = str(uuid.uuid4())
        await _seed_game_snapshot(
            session,
            models_mod,
            game_id=game_id,
            seats=[("p1", 1, 100), ("p2", 2, 100), ("p3", 3, 100)],
            positions=(1, 2, 3),
        )
        await _seed_round(
            session,
            models_mod,
            game_id=game_id,
            round_id=round_id,
            positions=(1, 2, 3),
            pot_amount=150,
            players=[
                ("p1", 1, 50, 50),
                ("p2", 2, 50, 50),
                ("p3", 3, 0, 50),
            ],
        )

        service = command_service_mod.GameCommandService(session)
        await service.resolve_hand(
            round_id,
            command_service_mod.ResolveHandRequest(
                payouts=[
                    {
                        "pot_index": 0,
                        "pot_type": "main",
                        "amount": 150,
                        "winners": [{"player_id": "p1", "amount": 150}],
                    }
                ]
            ),
        )

        game = await _load_game(session, models_mod, game_id)
        assert game.status == "ACTIVE"
        assert (game.current_dealer_seat, game.current_small_blind_seat, game.current_big_blind_seat) == (2, 2, 1)

        next_round = await service.start_round(
            game_id,
            command_service_mod.StartRoundRequest(started_by_controller=True),
        )
        next_round_players = await _load_round_players(session, models_mod, next_round.round_id)

        assert {player.player_id for player in next_round_players} == {"p1", "p2"}
        assert {player.seat_number for player in next_round_players} == {1, 2}

    @pytest.mark.asyncio
    async def test_game_finishes_when_fewer_than_two_players_remain(
        self, session, models_mod, command_service_mod,
    ):
        game_id = str(uuid.uuid4())
        round_id = str(uuid.uuid4())
        await _seed_game_snapshot(
            session,
            models_mod,
            game_id=game_id,
            seats=[("p1", 1, 100), ("p2", 2, 100)],
            positions=(1, 1, 2),
        )
        await _seed_round(
            session,
            models_mod,
            game_id=game_id,
            round_id=round_id,
            positions=(1, 1, 2),
            pot_amount=200,
            players=[
                ("p1", 1, 0, 100),
                ("p2", 2, 0, 100),
            ],
        )

        service = command_service_mod.GameCommandService(session)
        result = await service.declare_winner(
            round_id,
            command_service_mod.DeclareWinner(winner_player_id="p2"),
        )

        game = await _load_game(session, models_mod, game_id)
        snapshot_players = {
            player.player_id: player
            for player in await _load_snapshot_players(session, models_mod, game_id)
        }

        assert result.winner_player_id == "p2"
        assert game.status == "FINISHED"
        assert snapshot_players["p1"].chip_count == 0
        assert snapshot_players["p1"].is_active is False
        assert snapshot_players["p1"].is_eliminated is True
        assert snapshot_players["p2"].chip_count == 200
        assert snapshot_players["p2"].is_active is True
        assert snapshot_players["p2"].is_eliminated is False

        with pytest.raises(command_service_mod.GameNotActive):
            await service.start_round(
                game_id,
                command_service_mod.StartRoundRequest(started_by_controller=True),
            )