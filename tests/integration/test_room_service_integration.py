from __future__ import annotations

import os

import httpx
import pytest

from tests.service_loader import load_service_app_module

os.environ["ROOM_DB"] = "sqlite+aiosqlite:///:memory:"
os.environ["RABBIT_URL"] = "amqp://guest:guest@localhost:5672/"
os.environ["EXCHANGE_NAME"] = "test_exchange"

@pytest.fixture()
async def room_app_modules():
    package_name = "room_integration_app"
    db_module = load_service_app_module(
        "room-service",
        "infrastructure/db",
        package_name=package_name,
        reload_modules=True,
    )
    load_service_app_module(
        "room-service",
        "domain/models",
        package_name=package_name,
    )
    main_module = load_service_app_module(
        "room-service",
        "main",
        package_name=package_name,
    )

    async with db_module.engine.begin() as conn:
        await conn.run_sync(db_module.Base.metadata.create_all)

    yield main_module, db_module

    async with db_module.engine.begin() as conn:
        await conn.run_sync(db_module.Base.metadata.drop_all)
    await db_module.engine.dispose()

@pytest.mark.integration
@pytest.mark.asyncio
async def test_room_service_split_routes_full_room_flow(room_app_modules):
    main_module, _db_module = room_app_modules

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=main_module.app),
        base_url="http://room-service.test",
    ) as client:
        health = await client.get("/health")
        assert health.status_code == 200
        assert health.json()["service"] == "room-service"

        create = await client.post(
            "/rooms",
            json={
                "name": "Friday Poker",
                "max_players": 6,
                "starting_chips": 1500,
                "antes_enabled": True,
                "created_by": "host@example.com",
            },
        )
        assert create.status_code == 200
        room = create.json()
        room_id = room["room_id"]
        code = room["code"]

        list_rooms = await client.get("/rooms")
        assert list_rooms.status_code == 200
        assert [room["room_id"] for room in list_rooms.json()] == [room_id]

        get_room = await client.get(f"/rooms/{room_id}")
        assert get_room.status_code == 200
        assert get_room.json()["room"]["room_id"] == room_id

        get_by_code = await client.get(f"/rooms/code/{code.lower()}")
        assert get_by_code.status_code == 200
        assert get_by_code.json()["room"]["code"] == code

        alice = await client.post(
            f"/rooms/join/{code}",
            json={"player_name": "Alice", "seat_number": 2},
        )
        assert alice.status_code == 200
        alice_body = alice.json()
        assert alice_body["seat_number"] == 2

        bob = await client.post(
            f"/rooms/join/{code}",
            json={"player_name": "Bob", "seat_number": 1},
        )
        assert bob.status_code == 200
        bob_body = bob.json()

        duplicate_seat = await client.post(
            f"/rooms/join/{code}",
            json={"player_name": "Carol", "seat_number": 1},
        )
        assert duplicate_seat.status_code == 409

        fetched_player = await client.get(f"/players/{alice_body['player_id']}")
        assert fetched_player.status_code == 200
        assert fetched_player.json()["player_name"] == "Alice"

        chips = await client.put(
            f"/players/{alice_body['player_id']}/chips",
            json={"chip_count": 1200},
        )
        assert chips.status_code == 200
        assert chips.json()["chip_count"] == 1200

        reorder = await client.put(
            f"/rooms/{room_id}/seats",
            json={
                "assignments": [
                    {"player_id": alice_body["player_id"], "seat_number": 1},
                    {"player_id": bob_body["player_id"], "seat_number": 2},
                ],
            },
        )
        assert reorder.status_code == 200
        seats = {
            player["player_id"]: player["seat_number"]
            for player in reorder.json()["players"]
        }
        assert seats == {
            alice_body["player_id"]: 1,
            bob_body["player_id"]: 2,
        }

        blinds = await client.put(
            f"/rooms/{room_id}/blinds",
            json={
                "starting_dealer_seat": 1,
                "levels": [
                    {
                        "level": 1,
                        "small_blind": 5,
                        "big_blind": 10,
                        "ante": 1,
                        "duration_minutes": 15,
                    }
                ],
            },
        )
        assert blinds.status_code == 200
        assert blinds.json()["blind_levels"][0]["big_blind"] == 10

        eliminated = await client.post(f"/players/{bob_body['player_id']}/eliminate")
        assert eliminated.status_code == 200
        assert eliminated.json()["is_eliminated"] is True

        deleted = await client.delete(f"/rooms/{room_id}")
        assert deleted.status_code == 200
        assert deleted.json()["room_id"] == room_id

        missing = await client.get(f"/rooms/{room_id}")
        assert missing.status_code == 404


@pytest.mark.integration
@pytest.mark.asyncio
async def test_room_status_routes_block_late_joins(room_app_modules):
    main_module, _db_module = room_app_modules

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=main_module.app),
        base_url="http://room-service.test",
    ) as client:
        create = await client.post(
            "/rooms",
            json={
                "name": "Status Guard",
                "max_players": 6,
                "starting_chips": 1000,
                "antes_enabled": False,
                "created_by": "host@example.com",
            },
        )
        assert create.status_code == 200
        room = create.json()
        room_id = room["room_id"]
        code = room["code"]

        active = await client.post(f"/rooms/{room_id}/activate")
        assert active.status_code == 200
        assert active.json()["status"] == "ACTIVE"

        join_active = await client.post(
            f"/rooms/join/{code}",
            json={"player_name": "Late Alice"},
        )
        assert join_active.status_code == 400
        assert join_active.json()["detail"] == "Room is not in WAITING status"

        finished = await client.post(f"/rooms/{room_id}/finish")
        assert finished.status_code == 200
        assert finished.json()["status"] == "FINISHED"

        join_finished = await client.post(
            f"/rooms/join/{code}",
            json={"player_name": "Late Bob"},
        )
        assert join_finished.status_code == 400
        assert join_finished.json()["detail"] == "Room is not in WAITING status"