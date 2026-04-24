from __future__ import annotations

import os

import httpx
import pytest
from fastapi import FastAPI

from tests.service_loader import load_service_app_module

os.environ["RABBIT_URL"] = ""

class FakeResponse:
    def __init__(self, *, status_code: int, payload: dict | None = None, text: str = "") -> None:
        self.status_code = status_code
        self._payload = payload or {}
        self.text = text

    def json(self) -> dict:
        return self._payload

class FakeGameClient:
    def __init__(self) -> None:
        self.calls: list[tuple[str, str]] = []
        self.json_payloads: list[tuple[str, dict | None]] = []

    async def get(self, path: str, **kwargs) -> FakeResponse:
        self.calls.append(("GET", path))
        if path.endswith("/session-status"):
            return FakeResponse(
                status_code=200,
                payload={
                    "game_id": "game-1",
                    "status": "ACTIVE",
                    "hands_played": 3,
                    "current_blind_level": 2,
                    "hands_at_current_level": 1,
                    "hands_until_blind_advance": 4,
                    "seconds_until_blind_advance": 120,
                    "max_blind_level": 10,
                    "small_blind": 10,
                    "big_blind": 20,
                    "ante": 2,
                    "dealer_seat": 4,
                },
            )
        raise AssertionError(f"Unexpected GET path: {path}")

    async def post(self, path: str, **kwargs) -> FakeResponse:
        self.calls.append(("POST", path))
        self.json_payloads.append((path, kwargs.get("json")))
        if path.endswith("/rounds"):
            return FakeResponse(
                status_code=200,
                payload={
                    "round_id": "round-1",
                    "game_id": "game-1",
                    "round_number": 2,
                    "dealer_seat": 4,
                    "small_blind_seat": 5,
                    "big_blind_seat": 6,
                    "small_blind_amount": 10,
                    "big_blind_amount": 20,
                    "ante_amount": 2,
                    "status": "ACTIVE",
                    "pot_amount": 30,
                    "street": "PRE_FLOP",
                    "acting_player_id": "p1",
                    "current_highest_bet": 20,
                    "minimum_raise_amount": 20,
                    "is_action_closed": False,
                    "players": [],
                    "payouts": [],
                    "created_at": None,
                    "completed_at": None,
                },
            )
        if path.endswith("/pause"):
            status = "PAUSED"
        elif path.endswith("/resume"):
            status = "ACTIVE"
        elif path.endswith("/record-hand-completed"):
            status = "ACTIVE"
        else:
            raise AssertionError(f"Unexpected POST path: {path}")

        return FakeResponse(
            status_code=200,
            payload={
                "game_id": "game-1",
                "room_id": "room-1",
                "status": status,
                "current_blind_level": 2,
                "level_started_at": None,
                "current_dealer_seat": 4,
                "current_small_blind_seat": 5,
                "current_big_blind_seat": 6,
                "hands_played": 3,
                "hands_at_current_level": 1,
                "created_at": None,
            },
        )

@pytest.fixture()
def gateway_game_routes_module():
    return load_service_app_module(
        "gateway-service",
        "routes/game_routes",
        package_name="gateway_game_routes_test_app",
        reload_modules=True,
    )

@pytest.mark.unit
@pytest.mark.asyncio
async def test_gateway_proxies_game_runtime_routes(gateway_game_routes_module, monkeypatch):
    fake_client = FakeGameClient()
    monkeypatch.setattr(gateway_game_routes_module, "game_client", fake_client)

    app = FastAPI()
    app.include_router(gateway_game_routes_module.router)

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://gateway.test",
    ) as client:
        session_status = await client.get("/games/game-1/session-status")
        assert session_status.status_code == 200
        assert session_status.json()["big_blind"] == 20

        started_round = await client.post(
            "/games/game-1/rounds",
            json={"started_by_player_id": "p4", "started_by_controller": False},
        )
        assert started_round.status_code == 200
        assert started_round.json()["round_id"] == "round-1"

        paused = await client.post("/games/game-1/pause")
        assert paused.status_code == 200
        assert paused.json()["status"] == "PAUSED"

        resumed = await client.post("/games/game-1/resume")
        assert resumed.status_code == 200
        assert resumed.json()["status"] == "ACTIVE"

        recorded = await client.post("/games/game-1/record-hand-completed")
        assert recorded.status_code == 200
        assert recorded.json()["game_id"] == "game-1"

    assert fake_client.calls == [
        ("GET", "/games/game-1/session-status"),
        ("POST", "/games/game-1/rounds"),
        ("POST", "/games/game-1/pause"),
        ("POST", "/games/game-1/resume"),
        ("POST", "/games/game-1/record-hand-completed"),
    ]
    assert fake_client.json_payloads[0] == (
        "/games/game-1/rounds",
        {"started_by_player_id": "p4", "started_by_controller": False},
    )