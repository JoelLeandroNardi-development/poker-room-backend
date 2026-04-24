from __future__ import annotations

import os

import httpx
import pytest
from fastapi import HTTPException
from sqlalchemy import select

from tests.service_loader import load_service_app_module

os.environ.setdefault("GAME_DB", "sqlite+aiosqlite:///:memory:")
os.environ.setdefault("ROOM_DB", "sqlite+aiosqlite:///:memory:")
os.environ.setdefault("RABBIT_URL", "amqp://guest:guest@localhost:5672/")
os.environ.setdefault("EXCHANGE_NAME", "test_exchange")

GAME_PACKAGE = "integration_game_room_status_game_app"
ROOM_PACKAGE = "integration_game_room_status_room_app"


@pytest.fixture
async def synced_game_room_modules(monkeypatch):
    room_db_module = load_service_app_module(
        "room-service",
        "infrastructure/db",
        package_name=ROOM_PACKAGE,
        reload_modules=True,
    )
    room_models_module = load_service_app_module(
        "room-service",
        "domain/models",
        package_name=ROOM_PACKAGE,
    )
    room_main_module = load_service_app_module(
        "room-service",
        "main",
        package_name=ROOM_PACKAGE,
    )

    async with room_db_module.engine.begin() as conn:
        await conn.run_sync(room_db_module.Base.metadata.create_all)

    game_db_module = load_service_app_module(
        "game-service",
        "infrastructure/db",
        package_name=GAME_PACKAGE,
        reload_modules=True,
    )
    game_models_module = load_service_app_module(
        "game-service",
        "domain/models",
        package_name=GAME_PACKAGE,
    )
    game_room_config_module = load_service_app_module(
        "game-service",
        "infrastructure/room_config",
        package_name=GAME_PACKAGE,
    )
    command_service_mod = load_service_app_module(
        "game-service",
        "application/commands/game_command_service",
        package_name=GAME_PACKAGE,
    )

    async with game_db_module.engine.begin() as conn:
        await conn.run_sync(game_db_module.Base.metadata.create_all)

    real_async_client = httpx.AsyncClient

    def room_service_client(*args, **kwargs):
        kwargs.setdefault("transport", httpx.ASGITransport(app=room_main_module.app))
        kwargs.setdefault("base_url", "http://room-service.test")
        return real_async_client(*args, **kwargs)

    monkeypatch.setattr(game_room_config_module.httpx, "AsyncClient", room_service_client)

    yield {
        "room_db_module": room_db_module,
        "room_models_module": room_models_module,
        "room_main_module": room_main_module,
        "game_db_module": game_db_module,
        "game_models_module": game_models_module,
        "command_service_mod": command_service_mod,
    }

    async with game_db_module.engine.begin() as conn:
        await conn.run_sync(game_db_module.Base.metadata.drop_all)
    await game_db_module.engine.dispose()

    async with room_db_module.engine.begin() as conn:
        await conn.run_sync(room_db_module.Base.metadata.drop_all)
    await room_db_module.engine.dispose()


async def _create_ready_room(room_main_module) -> tuple[str, str]:
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=room_main_module.app),
        base_url="http://room-service.test",
    ) as client:
        create = await client.post(
            "/rooms",
            json={
                "name": "Ready Room",
                "max_players": 6,
                "starting_chips": 1000,
                "antes_enabled": False,
                "created_by": "host@example.com",
            },
        )
        room = create.json()
        room_id = room["room_id"]
        code = room["code"]

        for player_name, seat_number in (("Alice", 1), ("Bob", 2), ("Cara", 3)):
            joined = await client.post(
                f"/rooms/join/{code}",
                json={"player_name": player_name, "seat_number": seat_number},
            )
            assert joined.status_code == 200

        blinds = await client.put(
            f"/rooms/{room_id}/blinds",
            json={
                "starting_dealer_seat": 1,
                "levels": [
                    {
                        "level": 1,
                        "small_blind": 5,
                        "big_blind": 10,
                        "ante": 0,
                        "duration_minutes": 15,
                    }
                ],
            },
        )
        assert blinds.status_code == 200

        return room_id, code


async def _load_room_status(room_main_module, room_id: str) -> str:
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=room_main_module.app),
        base_url="http://room-service.test",
    ) as client:
        response = await client.get(f"/rooms/{room_id}")
        assert response.status_code == 200
        return response.json()["room"]["status"]


@pytest.mark.integration
class TestGameRoomStatusSync:
    @pytest.mark.asyncio
    async def test_starting_game_marks_room_active(self, synced_game_room_modules):
        room_main_module = synced_game_room_modules["room_main_module"]
        game_db_module = synced_game_room_modules["game_db_module"]
        command_service_mod = synced_game_room_modules["command_service_mod"]

        room_id, _code = await _create_ready_room(room_main_module)

        async with game_db_module.SessionLocal() as db:
            service = command_service_mod.GameCommandService(db)
            response = await service.start_game(
                command_service_mod.StartGame(room_id=room_id)
            )

        assert response.room_id == room_id
        assert await _load_room_status(room_main_module, room_id) == "ACTIVE"

    @pytest.mark.asyncio
    async def test_ending_game_marks_room_finished(self, synced_game_room_modules):
        room_main_module = synced_game_room_modules["room_main_module"]
        game_db_module = synced_game_room_modules["game_db_module"]
        command_service_mod = synced_game_room_modules["command_service_mod"]

        room_id, _code = await _create_ready_room(room_main_module)

        async with game_db_module.SessionLocal() as db:
            service = command_service_mod.GameCommandService(db)
            game = await service.start_game(command_service_mod.StartGame(room_id=room_id))
            result = await service.end_game(game.game_id)

        assert result.game_id == game.game_id
        assert result.status == "FINISHED"
        assert await _load_room_status(room_main_module, room_id) == "FINISHED"

    @pytest.mark.asyncio
    async def test_start_game_rolls_back_when_room_activation_fails(
        self, synced_game_room_modules, monkeypatch,
    ):
        room_main_module = synced_game_room_modules["room_main_module"]
        game_db_module = synced_game_room_modules["game_db_module"]
        game_models_module = synced_game_room_modules["game_models_module"]
        command_service_mod = synced_game_room_modules["command_service_mod"]

        room_id, _code = await _create_ready_room(room_main_module)

        async def fail_activate(_room_id: str) -> None:
            raise HTTPException(status_code=502, detail="Failed to activate room in room-service")

        monkeypatch.setattr(command_service_mod, "mark_room_active_http", fail_activate)

        async with game_db_module.SessionLocal() as db:
            service = command_service_mod.GameCommandService(db)
            with pytest.raises(HTTPException) as exc:
                await service.start_game(command_service_mod.StartGame(room_id=room_id))

        assert exc.value.status_code == 502
        assert exc.value.detail == "Failed to activate room in room-service"

        async with game_db_module.SessionLocal() as db:
            games = (await db.execute(select(game_models_module.Game))).scalars().all()
            snapshots = (await db.execute(select(game_models_module.RoomSnapshot))).scalars().all()

        assert games == []
        assert snapshots == []
        assert await _load_room_status(room_main_module, room_id) == "WAITING"