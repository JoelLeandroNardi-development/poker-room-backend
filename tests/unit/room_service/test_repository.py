from __future__ import annotations

import os

import pytest

from tests.service_loader import load_service_app_module

os.environ.setdefault("ROOM_DB", "sqlite+aiosqlite:///:memory:")
os.environ.setdefault("RABBIT_URL", "amqp://guest:guest@localhost:5672/")
os.environ.setdefault("EXCHANGE_NAME", "test_exchange")

@pytest.fixture(scope="module")
def room_db_module():
    return load_service_app_module(
        "room-service", "infrastructure/db",
        package_name="room_test_app",
        reload_modules=True,
    )

@pytest.fixture(scope="module")
def room_models_module(room_db_module):
    return load_service_app_module(
        "room-service", "domain/models",
        package_name="room_test_app",
    )

@pytest.fixture(scope="module")
def room_repository_module(room_models_module):
    return load_service_app_module(
        "room-service", "infrastructure/repositories/room_repository",
        package_name="room_test_app",
    )

@pytest.fixture(scope="module")
def room_player_repository_module(room_models_module):
    return load_service_app_module(
        "room-service", "infrastructure/repositories/room_player_repository",
        package_name="room_test_app",
    )

@pytest.fixture(scope="module")
def room_command_module(room_repository_module, room_player_repository_module):
    return load_service_app_module(
        "room-service", "application/commands/room_command_service",
        package_name="room_test_app",
    )

@pytest.fixture(scope="module")
def room_player_command_module(room_command_module):
    return load_service_app_module(
        "room-service", "application/commands/room_player_command_service",
        package_name="room_test_app",
    )

@pytest.fixture(scope="module")
def room_schema_module(room_player_command_module):
    return load_service_app_module(
        "room-service", "domain/schemas",
        package_name="room_test_app",
    )

@pytest.fixture(autouse=True)
async def _setup_tables(room_db_module, room_models_module):
    engine = room_db_module.engine
    async with engine.begin() as conn:
        await conn.run_sync(room_db_module.Base.metadata.create_all)
    yield
    async with engine.begin() as conn:
        await conn.run_sync(room_db_module.Base.metadata.drop_all)

async def _insert_room(room_db_module, room_models_module, *, room_id: str, code: str, max_players: int = 6):
    Room = room_models_module.Room
    async with room_db_module.SessionLocal() as db:
        db.add(Room(
            room_id=room_id,
            code=code,
            name="Test Room",
            status="WAITING",
            max_players=max_players,
            starting_chips=1000,
            antes_enabled=False,
            starting_dealer_seat=1,
            created_by="host",
        ))
        await db.commit()

async def _insert_player(room_db_module, room_models_module, *, room_id: str, player_id: str, player_name: str, seat: int):
    RoomPlayer = room_models_module.RoomPlayer
    async with room_db_module.SessionLocal() as db:
        db.add(RoomPlayer(
            room_id=room_id,
            player_id=player_id,
            player_name=player_name,
            seat_number=seat,
            chip_count=1000,
            is_active=True,
            is_eliminated=False,
        ))
        await db.commit()

@pytest.mark.unit
class TestGenerateUniqueCode:
    @pytest.mark.asyncio
    async def test_code_is_4_chars(self, room_db_module, room_repository_module):
        async with room_db_module.SessionLocal() as db:
            code = await room_repository_module.generate_unique_code(db)
        assert len(code) == 4

    @pytest.mark.asyncio
    async def test_code_is_alphanumeric_upper(self, room_db_module, room_repository_module):
        async with room_db_module.SessionLocal() as db:
            code = await room_repository_module.generate_unique_code(db)
        assert code.isalnum()
        assert code == code.upper()

    @pytest.mark.asyncio
    async def test_codes_are_unique(self, room_db_module, room_repository_module):
        codes = set()
        async with room_db_module.SessionLocal() as db:
            for _ in range(20):
                code = await room_repository_module.generate_unique_code(db)
                codes.add(code)
        assert len(codes) == 20

@pytest.mark.unit
class TestGetRoomByCode:
    @pytest.mark.asyncio
    async def test_found(self, room_db_module, room_models_module, room_repository_module):
        await _insert_room(room_db_module, room_models_module, room_id="r1", code="ABCD")
        async with room_db_module.SessionLocal() as db:
            room = await room_repository_module.get_room_by_code(db, "ABCD")
        assert room is not None
        assert room.room_id == "r1"

    @pytest.mark.asyncio
    async def test_case_insensitive(self, room_db_module, room_models_module, room_repository_module):
        await _insert_room(room_db_module, room_models_module, room_id="r2", code="XY12")
        async with room_db_module.SessionLocal() as db:
            room = await room_repository_module.get_room_by_code(db, "xy12")
        assert room is not None
        assert room.code == "XY12"

    @pytest.mark.asyncio
    async def test_not_found(self, room_db_module, room_repository_module):
        async with room_db_module.SessionLocal() as db:
            room = await room_repository_module.get_room_by_code(db, "ZZZZ")
        assert room is None

@pytest.mark.unit
class TestGetPlayersInRoom:
    @pytest.mark.asyncio
    async def test_returns_ordered_by_seat(self, room_db_module, room_models_module, room_player_repository_module):
        await _insert_room(room_db_module, room_models_module, room_id="r3", code="SEAT")
        await _insert_player(room_db_module, room_models_module, room_id="r3", player_id="p1", player_name="Alice", seat=3)
        await _insert_player(room_db_module, room_models_module, room_id="r3", player_id="p2", player_name="Bob", seat=1)
        await _insert_player(room_db_module, room_models_module, room_id="r3", player_id="p3", player_name="Carol", seat=2)

        async with room_db_module.SessionLocal() as db:
            players = await room_player_repository_module.get_players_in_room(db, "r3")

        seats = [p.seat_number for p in players]
        assert seats == [1, 2, 3]

    @pytest.mark.asyncio
    async def test_empty_room(self, room_db_module, room_models_module, room_player_repository_module):
        await _insert_room(room_db_module, room_models_module, room_id="r4", code="EMPT")
        async with room_db_module.SessionLocal() as db:
            players = await room_player_repository_module.get_players_in_room(db, "r4")
        assert players == []

@pytest.mark.unit
class TestCountPlayersInRoom:
    @pytest.mark.asyncio
    async def test_count(self, room_db_module, room_models_module, room_player_repository_module):
        await _insert_room(room_db_module, room_models_module, room_id="r5", code="CNT1")
        await _insert_player(room_db_module, room_models_module, room_id="r5", player_id="p10", player_name="A", seat=1)
        await _insert_player(room_db_module, room_models_module, room_id="r5", player_id="p11", player_name="B", seat=2)

        async with room_db_module.SessionLocal() as db:
            count = await room_player_repository_module.count_players_in_room(db, "r5")
        assert count == 2

@pytest.mark.unit
class TestPlayerNameExistsInRoom:
    @pytest.mark.asyncio
    async def test_duplicate(self, room_db_module, room_models_module, room_player_repository_module):
        await _insert_room(room_db_module, room_models_module, room_id="r6", code="DUP1")
        await _insert_player(room_db_module, room_models_module, room_id="r6", player_id="p20", player_name="Dave", seat=1)

        async with room_db_module.SessionLocal() as db:
            assert await room_player_repository_module.player_name_exists_in_room(db, "r6", "Dave") is True

    @pytest.mark.asyncio
    async def test_no_duplicate(self, room_db_module, room_models_module, room_player_repository_module):
        await _insert_room(room_db_module, room_models_module, room_id="r7", code="DUP2")

        async with room_db_module.SessionLocal() as db:
            assert await room_player_repository_module.player_name_exists_in_room(db, "r7", "Eve") is False

@pytest.mark.unit
class TestSeatNumberExistsInRoom:
    @pytest.mark.asyncio
    async def test_seat_exists(self, room_db_module, room_models_module, room_player_repository_module):
        await _insert_room(room_db_module, room_models_module, room_id="r8", code="SEA1")
        await _insert_player(room_db_module, room_models_module, room_id="r8", player_id="p30", player_name="Ana", seat=2)

        async with room_db_module.SessionLocal() as db:
            assert await room_player_repository_module.seat_number_exists_in_room(db, "r8", 2) is True
            assert await room_player_repository_module.seat_number_exists_in_room(db, "r8", 1) is False

@pytest.mark.unit
class TestRoomCommandSeatManagement:
    @pytest.mark.asyncio
    async def test_join_room_with_requested_seat(self, room_db_module, room_models_module, room_player_command_module, room_schema_module):
        await _insert_room(room_db_module, room_models_module, room_id="r9", code="J001")

        async with room_db_module.SessionLocal() as db:
            svc = room_player_command_module.RoomPlayerCommandService(db)
            response = await svc.join_room_by_code(
                "J001",
                room_schema_module.JoinRoom(player_name="Seat Four", seat_number=4),
            )

        assert response.seat_number == 4

    @pytest.mark.asyncio
    async def test_join_room_rejects_taken_seat(self, room_db_module, room_models_module, room_player_command_module, room_schema_module):
        from fastapi import HTTPException

        await _insert_room(room_db_module, room_models_module, room_id="r10", code="J002")
        await _insert_player(room_db_module, room_models_module, room_id="r10", player_id="p40", player_name="Taken", seat=2)

        async with room_db_module.SessionLocal() as db:
            svc = room_player_command_module.RoomPlayerCommandService(db)
            with pytest.raises(HTTPException) as exc:
                await svc.join_room_by_code(
                    "J002",
                    room_schema_module.JoinRoom(player_name="Blocked", seat_number=2),
                )

        assert exc.value.status_code == 409

    @pytest.mark.asyncio
    async def test_reorder_seats(self, room_db_module, room_models_module, room_command_module, room_schema_module):
        await _insert_room(room_db_module, room_models_module, room_id="r11", code="J003")
        await _insert_player(room_db_module, room_models_module, room_id="r11", player_id="p50", player_name="One", seat=1)
        await _insert_player(room_db_module, room_models_module, room_id="r11", player_id="p51", player_name="Two", seat=2)

        async with room_db_module.SessionLocal() as db:
            svc = room_command_module.RoomCommandService(db)
            response = await svc.reorder_seats(
                "r11",
                room_schema_module.ReorderSeats(assignments=[
                    room_schema_module.SeatAssignment(player_id="p50", seat_number=2),
                    room_schema_module.SeatAssignment(player_id="p51", seat_number=1),
                ]),
            )

        seats = {player.player_id: player.seat_number for player in response.players}
        assert seats == {"p50": 2, "p51": 1}