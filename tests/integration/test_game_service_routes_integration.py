from __future__ import annotations

import os

import httpx
import pytest

from shared.core.time import utc_now
from tests.service_loader import load_service_app_module

os.environ["GAME_DB"] = "sqlite+aiosqlite:///:memory:"
os.environ["RABBIT_URL"] = "amqp://guest:guest@localhost:5672/"
os.environ["EXCHANGE_NAME"] = "test_exchange"

@pytest.fixture()
async def game_app_modules():
    package_name = "game_routes_integration_app"
    db_module = load_service_app_module(
        "game-service",
        "infrastructure/db",
        package_name=package_name,
        reload_modules=True,
    )
    models_module = load_service_app_module(
        "game-service",
        "domain/models",
        package_name=package_name,
    )
    main_module = load_service_app_module(
        "game-service",
        "main",
        package_name=package_name,
    )

    async with db_module.engine.begin() as conn:
        await conn.run_sync(db_module.Base.metadata.create_all)

    async with db_module.SessionLocal() as db:
        game = models_module.Game(
            game_id="game-route-1",
            room_id="room-route-1",
            status="ACTIVE",
            current_blind_level=1,
            level_started_at=utc_now(),
            current_dealer_seat=1,
            current_small_blind_seat=1,
            current_big_blind_seat=2,
            hands_played=0,
            hands_at_current_level=0,
        )
        game_round = models_module.Round(
            round_id="round-route-1",
            game_id="game-route-1",
            round_number=1,
            dealer_seat=1,
            small_blind_seat=1,
            big_blind_seat=2,
            small_blind_amount=5,
            big_blind_amount=10,
            ante_amount=0,
            status="ACTIVE",
            pot_amount=0,
            street="PRE_FLOP",
            acting_player_id="p1",
            current_highest_bet=0,
            minimum_raise_amount=10,
            is_action_closed=False,
            state_version=1,
        )
        players = [
            models_module.RoundPlayer(
                round_id="round-route-1",
                player_id="p1",
                seat_number=1,
                stack_remaining=100,
                committed_this_street=0,
                committed_this_hand=0,
                has_folded=False,
                is_all_in=False,
                is_active_in_hand=True,
            ),
            models_module.RoundPlayer(
                round_id="round-route-1",
                player_id="p2",
                seat_number=2,
                stack_remaining=100,
                committed_this_street=0,
                committed_this_hand=0,
                has_folded=False,
                is_all_in=False,
                is_active_in_hand=True,
            ),
        ]
        snapshot = models_module.RoomSnapshot(
            game_id="game-route-1",
            room_id="room-route-1",
            starting_dealer_seat=1,
            antes_enabled=True,
        )
        snapshot_players = [
            models_module.RoomSnapshotPlayer(
                game_id="game-route-1",
                player_id="p1",
                seat_number=1,
                chip_count=100,
                is_active=True,
                is_eliminated=False,
            ),
            models_module.RoomSnapshotPlayer(
                game_id="game-route-1",
                player_id="p2",
                seat_number=2,
                chip_count=100,
                is_active=True,
                is_eliminated=False,
            ),
        ]
        blind_levels = [
            models_module.RoomSnapshotBlindLevel(
                game_id="game-route-1",
                level=1,
                small_blind=5,
                big_blind=10,
                ante=1,
                duration_minutes=15,
            ),
            models_module.RoomSnapshotBlindLevel(
                game_id="game-route-1",
                level=2,
                small_blind=10,
                big_blind=20,
                ante=2,
                duration_minutes=15,
            ),
        ]

        db.add(game)
        db.add(game_round)
        db.add_all(players)
        db.add(snapshot)
        db.add_all(snapshot_players)
        db.add_all(blind_levels)
        await db.commit()

    yield main_module, db_module

    async with db_module.engine.begin() as conn:
        await conn.run_sync(db_module.Base.metadata.drop_all)
    await db_module.engine.dispose()

@pytest.mark.integration
@pytest.mark.asyncio
async def test_game_service_split_routes_query_bet_and_runtime_flow(game_app_modules):
    main_module, _db_module = game_app_modules

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=main_module.app),
        base_url="http://game-service.test",
    ) as client:
        health = await client.get("/health")
        assert health.status_code == 200
        assert health.json()["service"] == "game-service"

        game = await client.get("/games/game-route-1")
        assert game.status_code == 200
        assert game.json()["room_id"] == "room-route-1"

        by_room = await client.get("/games/room/room-route-1")
        assert by_room.status_code == 200
        assert by_room.json()["game_id"] == "game-route-1"

        rounds = await client.get("/games/game-route-1/rounds")
        assert rounds.status_code == 200
        assert [round_data["round_id"] for round_data in rounds.json()] == ["round-route-1"]

        active_round = await client.get("/games/game-route-1/rounds/active")
        assert active_round.status_code == 200
        assert active_round.json()["acting_player_id"] == "p1"

        table_state = await client.get("/rounds/round-route-1/table-state")
        assert table_state.status_code == 200
        assert table_state.json()["legal_actions"][0]["action"] == "FOLD"

        bet = await client.post(
            "/bets",
            json={
                "round_id": "round-route-1",
                "player_id": "p1",
                "action": "CHECK",
                "amount": 0,
                "idempotency_key": "route-check-1",
                "expected_version": 1,
            },
        )
        assert bet.status_code == 200
        assert bet.json()["action"] == "CHECK"

        repeated_bet = await client.post(
            "/bets",
            json={
                "round_id": "round-route-1",
                "player_id": "p1",
                "action": "CHECK",
                "amount": 0,
                "idempotency_key": "route-check-1",
            },
        )
        assert repeated_bet.status_code == 200
        assert repeated_bet.json()["bet_id"] == bet.json()["bet_id"]

        bets = await client.get("/bets/round/round-route-1")
        assert bets.status_code == 200
        assert [row["action"] for row in bets.json()] == ["CHECK"]

        pot = await client.get("/bets/round/round-route-1/pot")
        assert pot.status_code == 200
        assert pot.json()["total_pot"] == 0

        summaries = await client.get("/bets/round/round-route-1/players")
        assert summaries.status_code == 200
        assert summaries.json()[0]["last_action"] == "CHECK"

        ledger = await client.get("/rounds/round-route-1/ledger")
        assert ledger.status_code == 200
        assert ledger.json()[0]["entry_type"] == "BET_PLACED"

        hand_state = await client.get("/rounds/round-route-1/hand-state")
        assert hand_state.status_code == 200
        assert hand_state.json()["entry_count"] == 1

        session_status = await client.get("/games/game-route-1/session-status")
        assert session_status.status_code == 200
        assert session_status.json()["big_blind"] == 10

        paused = await client.post("/games/game-route-1/pause")
        assert paused.status_code == 200
        assert paused.json()["status"] == "PAUSED"

        resumed = await client.post("/games/game-route-1/resume")
        assert resumed.status_code == 200
        assert resumed.json()["status"] == "ACTIVE"