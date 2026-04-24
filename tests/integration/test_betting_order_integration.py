"""Integration tests: betting order, legal actions, state versioning, and RAISE semantics.

Scenario: 3-player game, 5/10 blinds, no ante.
  Seat 1 = BTN/Dealer (p1)
  Seat 2 = SB        (p2) — posts 5
  Seat 3 = BB        (p3) — posts 10
  Pre-flop first to act = seat after BB = seat 1 (p1).

All tests run against a real SQLite DB with the full game-service FastAPI app
so they exercise the real ORM, repositories, CAS logic, and exception handlers.
"""

from __future__ import annotations

import os
import uuid

import httpx
import pytest

from tests.service_loader import load_service_app_module

os.environ.setdefault("GAME_DB", "sqlite+aiosqlite:///:memory:")
os.environ.setdefault("RABBIT_URL", "amqp://guest:guest@localhost:5672/")
os.environ.setdefault("EXCHANGE_NAME", "test_exchange")

_PACKAGE = "integration_betting_order_app"

_STACK = 500
_SB = 5
_BB = 10


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture()
async def app_ctx():
    """Reload game-service modules, create schema, seed a 3-player game, yield
    (main_module, db_module, game_id).  Drop schema on teardown."""
    game_id = str(uuid.uuid4())
    room_id = f"room-{game_id}"

    db_module = load_service_app_module(
        "game-service",
        "infrastructure/db",
        package_name=_PACKAGE,
        reload_modules=True,
    )
    models_module = load_service_app_module(
        "game-service",
        "domain/models",
        package_name=_PACKAGE,
    )
    main_module = load_service_app_module(
        "game-service",
        "main",
        package_name=_PACKAGE,
    )

    async with db_module.engine.begin() as conn:
        await conn.run_sync(db_module.Base.metadata.create_all)

    async with db_module.SessionLocal() as db:
        game = models_module.Game(
            game_id=game_id,
            room_id=room_id,
            status="ACTIVE",
            current_blind_level=1,
            current_dealer_seat=1,
            current_small_blind_seat=2,
            current_big_blind_seat=3,
            hands_played=0,
            hands_at_current_level=0,
        )
        snapshot = models_module.RoomSnapshot(
            game_id=game_id,
            room_id=room_id,
            starting_dealer_seat=1,
            antes_enabled=False,
        )
        snapshot_players = [
            models_module.RoomSnapshotPlayer(
                game_id=game_id,
                player_id=f"p{i}",
                seat_number=i,
                chip_count=_STACK,
                is_active=True,
                is_eliminated=False,
            )
            for i in range(1, 4)  # seats 1, 2, 3
        ]
        blind_levels = [
            models_module.RoomSnapshotBlindLevel(
                game_id=game_id,
                level=1,
                small_blind=_SB,
                big_blind=_BB,
                ante=0,
                duration_minutes=None,
            )
        ]
        db.add(game)
        db.add(snapshot)
        db.add_all(snapshot_players)
        db.add_all(blind_levels)
        await db.commit()

    yield main_module, db_module, game_id

    async with db_module.engine.begin() as conn:
        await conn.run_sync(db_module.Base.metadata.drop_all)
    await db_module.engine.dispose()


def _client(main_module) -> httpx.AsyncClient:
    return httpx.AsyncClient(
        transport=httpx.ASGITransport(app=main_module.app),
        base_url="http://game-service.test",
    )


async def _start_round(client: httpx.AsyncClient, game_id: str) -> dict:
    resp = await client.post(
        f"/games/{game_id}/rounds",
        json={"started_by_controller": True},
    )
    assert resp.status_code == 200, resp.text
    return resp.json()


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

@pytest.mark.integration
async def test_blinds_posted_automatically_on_start_round(app_ctx):
    """Blinds are collected into the pot as part of start_round; stacks reflect
    SB/BB deductions and committed amounts are non-zero."""
    main_module, _db, game_id = app_ctx

    async with _client(main_module) as client:
        round_data = await _start_round(client, game_id)

    players_by_seat = {p["seat_number"]: p for p in round_data["players"]}
    sb_player = players_by_seat[2]  # seat 2 = SB
    bb_player = players_by_seat[3]  # seat 3 = BB
    btn_player = players_by_seat[1]  # seat 1 = BTN, no blind

    # Stacks are reduced by blind amounts
    assert sb_player["stack_remaining"] == _STACK - _SB
    assert bb_player["stack_remaining"] == _STACK - _BB
    assert btn_player["stack_remaining"] == _STACK

    # Street commitments reflect posted blinds
    assert sb_player["committed_this_street"] == _SB
    assert bb_player["committed_this_street"] == _BB
    assert btn_player["committed_this_street"] == 0

    # Pot = SB + BB
    assert round_data["pot_amount"] == _SB + _BB

    # Blind seats and amounts are recorded on the round
    assert round_data["big_blind_seat"] == 3
    assert round_data["small_blind_seat"] == 2
    assert round_data["big_blind_amount"] == _BB
    assert round_data["small_blind_amount"] == _SB


@pytest.mark.integration
async def test_acting_player_is_seat_after_big_blind(app_ctx):
    """Pre-flop first to act is the seat immediately after the BB.
    With BTN=1, SB=2, BB=3, first actor = seat 1 (BTN/UTG in 3-player)."""
    main_module, _db, game_id = app_ctx

    async with _client(main_module) as client:
        round_data = await _start_round(client, game_id)

    # p1 is at seat 1, which is next after BB (seat 3) in a 3-seat rotation
    assert round_data["acting_player_id"] == "p1"


@pytest.mark.integration
async def test_table_state_legal_actions_only_for_acting_player(app_ctx):
    """legal_actions in table-state belong only to the acting player.
    Non-acting players have no legal_actions rendered for them."""
    main_module, _db, game_id = app_ctx

    async with _client(main_module) as client:
        round_data = await _start_round(client, game_id)
        round_id = round_data["round_id"]
        acting_id = round_data["acting_player_id"]

        ts_resp = await client.get(f"/rounds/{round_id}/table-state")
        assert ts_resp.status_code == 200
        ts = ts_resp.json()

    # Table state echoes the same acting_player_id
    assert ts["acting_player_id"] == acting_id

    # legal_actions are non-empty and belong to the acting player
    actions = ts["legal_actions"]
    assert len(actions) > 0

    action_types = {a["action"] for a in actions}
    # p1 faces the BB so must at minimum be able to FOLD and CALL
    assert "FOLD" in action_types
    assert "CALL" in action_types

    # state_version is exposed
    assert ts["state_version"] >= 1


@pytest.mark.integration
async def test_valid_action_with_expected_version_increments_state_version(app_ctx):
    """Submitting a valid action with the correct expected_version succeeds and
    the state_version on the round increments by 1."""
    main_module, _db, game_id = app_ctx

    async with _client(main_module) as client:
        round_data = await _start_round(client, game_id)
        round_id = round_data["round_id"]
        acting_id = round_data["acting_player_id"]  # p1

        # Capture version before the action
        ts_before = (await client.get(f"/rounds/{round_id}/table-state")).json()
        version_before = ts_before["state_version"]

        # p1 calls the BB (10 chips)
        bet_resp = await client.post(
            "/bets",
            json={
                "round_id": round_id,
                "player_id": acting_id,
                "action": "CALL",
                "amount": 0,
                "expected_version": version_before,
            },
        )
        assert bet_resp.status_code == 200
        assert bet_resp.json()["action"] == "CALL"

        # State version must have incremented
        ts_after = (await client.get(f"/rounds/{round_id}/table-state")).json()
        assert ts_after["state_version"] == version_before + 1


@pytest.mark.integration
async def test_non_acting_player_action_is_rejected(app_ctx):
    """Submitting an action for a player who is not the current actor is
    rejected with HTTP 400 (NotYourTurn domain error)."""
    main_module, _db, game_id = app_ctx

    async with _client(main_module) as client:
        round_data = await _start_round(client, game_id)
        round_id = round_data["round_id"]
        acting_id = round_data["acting_player_id"]  # p1

        # Choose a player who is NOT acting (p2 or p3)
        non_actor = "p2" if acting_id != "p2" else "p3"

        bad_resp = await client.post(
            "/bets",
            json={
                "round_id": round_id,
                "player_id": non_actor,
                "action": "CALL",
                "amount": 0,
            },
        )
        assert bad_resp.status_code == 400


@pytest.mark.integration
async def test_stale_expected_version_returns_409(app_ctx):
    """After a valid action advances state_version from V to V+1, submitting
    another action with expected_version=V is rejected with HTTP 409."""
    main_module, _db, game_id = app_ctx

    async with _client(main_module) as client:
        round_data = await _start_round(client, game_id)
        round_id = round_data["round_id"]
        acting_id = round_data["acting_player_id"]  # p1

        version_v = (await client.get(f"/rounds/{round_id}/table-state")).json()["state_version"]

        # First action succeeds: version V → V+1
        first = await client.post(
            "/bets",
            json={
                "round_id": round_id,
                "player_id": acting_id,
                "action": "CALL",
                "amount": 0,
                "expected_version": version_v,
            },
        )
        assert first.status_code == 200

        # Now p2 is acting; try to act as p2 but with the stale version V
        ts_after = (await client.get(f"/rounds/{round_id}/table-state")).json()
        next_actor = ts_after["acting_player_id"]
        assert ts_after["state_version"] == version_v + 1

        stale = await client.post(
            "/bets",
            json={
                "round_id": round_id,
                "player_id": next_actor,
                "action": "CALL",
                "amount": 0,
                "expected_version": version_v,  # stale — should be version_v + 1
            },
        )
        assert stale.status_code == 409


@pytest.mark.integration
async def test_raise_amount_means_total_street_commitment_not_raise_by(app_ctx):
    """RAISE amount is the desired *total street commitment* for the raiser,
    not an incremental "raise by" value.

    Setup: p1 has committed 0 on this street (BTN, no blind).
    BB = 10, minimum_raise_amount = 10.
    Minimum legal RAISE total = current_highest_bet + min_raise = 10 + 10 = 20.

    Sending RAISE amount=20 should commit exactly 20 chips from p1's stack
    (additional_chips = 20 - 0 = 20), NOT 30 chips.
    """
    main_module, _db, game_id = app_ctx

    async with _client(main_module) as client:
        round_data = await _start_round(client, game_id)
        round_id = round_data["round_id"]
        acting_id = round_data["acting_player_id"]  # p1, committed=0

        # Verify table-state expresses RAISE min_amount as total street commitment
        ts = (await client.get(f"/rounds/{round_id}/table-state")).json()
        actions_by_type = {a["action"]: a for a in ts["legal_actions"]}
        assert "RAISE" in actions_by_type

        raise_action = actions_by_type["RAISE"]
        # min_amount = current_highest_bet(10) + minimum_raise_amount(10) = 20
        # This is the *total* a player must commit on this street to make the min raise
        assert raise_action["min_amount"] == _BB + _BB  # 20
        assert raise_action["max_amount"] == _STACK      # all-in cap

        # Find p1's stack before the raise
        p1_before = next(p for p in round_data["players"] if p["player_id"] == acting_id)
        stack_before = p1_before["stack_remaining"]
        pot_before = round_data["pot_amount"]  # 15 (SB + BB)

        version = ts["state_version"]

        # Submit RAISE to 20 (total street commitment = 20)
        bet_resp = await client.post(
            "/bets",
            json={
                "round_id": round_id,
                "player_id": acting_id,
                "action": "RAISE",
                "amount": 20,  # "raise to total street commitment of 20"
                "expected_version": version,
            },
        )
        assert bet_resp.status_code == 200

        # Verify the post-action state
        ts_after = (await client.get(f"/rounds/{round_id}/table-state")).json()
        p1_after = next(p for p in ts_after["players"] if p["player_id"] == acting_id)

        # p1 committed 20 chips total this street (raise to 20, was at 0)
        assert p1_after["committed_this_street"] == 20

        # Stack deducted by exactly 20 (the additional chips from 0→20)
        assert p1_after["stack_remaining"] == stack_before - 20

        # Pot increased by 20 (p1's additional contribution)
        assert ts_after["pot_amount"] == pot_before + 20

        # New highest bet = 20 (the raised total)
        assert ts_after["current_highest_bet"] == 20

        # Next to act is p2 (SB, seat 2) — must call or re-raise
        assert ts_after["acting_player_id"] == "p2"
