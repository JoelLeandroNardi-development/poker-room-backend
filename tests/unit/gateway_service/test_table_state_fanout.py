from __future__ import annotations

import pytest

from tests.service_loader import load_service_app_module

class FakeWebSocket:
    def __init__(self) -> None:
        self.accepted = False
        self.messages = []

    async def accept(self) -> None:
        self.accepted = True

    async def send_json(self, payload: dict) -> None:
        self.messages.append(payload)

class FakeResponse:
    def __init__(self, *, status_code: int, payload: dict | None = None, text: str = "") -> None:
        self.status_code = status_code
        self._payload = payload or {}
        self.text = text

    def json(self) -> dict:
        return self._payload

class FakeGameClient:
    def __init__(self, response: FakeResponse) -> None:
        self.response = response
        self.paths = []

    async def get(self, path: str, **kwargs) -> FakeResponse:
        self.paths.append(path)
        return self.response

@pytest.fixture()
def gateway_fanout_module():
    return load_service_app_module(
        "gateway-service",
        "infrastructure/table_state_fanout",
        package_name="gateway_test_app",
        reload_modules=True,
    )

@pytest.fixture()
def gateway_ws_module(gateway_fanout_module):
    return load_service_app_module(
        "gateway-service",
        "infrastructure/table_state_ws",
        package_name="gateway_test_app",
    )

@pytest.mark.unit
def test_extract_round_id(gateway_fanout_module):
    assert gateway_fanout_module.extract_round_id({
        "event_type": "bet.placed",
        "data": {"round_id": "round-1"},
    }) == "round-1"
    assert gateway_fanout_module.extract_round_id({"data": {}}) is None
    assert gateway_fanout_module.extract_round_id({"data": None}) is None

@pytest.mark.unit
@pytest.mark.asyncio
async def test_handle_event_broadcasts_table_state(gateway_fanout_module, gateway_ws_module):
    manager = gateway_ws_module.TableStateConnectionManager()
    websocket = FakeWebSocket()
    await manager.connect("round-1", websocket)

    client = FakeGameClient(
        FakeResponse(
            status_code=200,
            payload={"round_id": "round-1", "state_version": 7},
        )
    )
    fanout = gateway_fanout_module.TableStateEventFanout(
        manager=manager,
        client=client,
    )

    await fanout.handle_event({
        "event_type": "bet.placed",
        "data": {"round_id": "round-1"},
    })

    assert client.paths == ["/rounds/round-1/table-state"]
    assert websocket.messages == [{
        "type": "table_state",
        "round_id": "round-1",
        "trigger": "bet.placed",
        "data": {"round_id": "round-1", "state_version": 7},
    }]

@pytest.mark.unit
@pytest.mark.asyncio
async def test_handle_event_ignores_unsubscribed_round(gateway_fanout_module, gateway_ws_module):
    manager = gateway_ws_module.TableStateConnectionManager()
    client = FakeGameClient(FakeResponse(status_code=200, payload={}))
    fanout = gateway_fanout_module.TableStateEventFanout(
        manager=manager,
        client=client,
    )

    await fanout.handle_event({
        "event_type": "bet.placed",
        "data": {"round_id": "round-1"},
    })

    assert client.paths == []

@pytest.mark.unit
@pytest.mark.asyncio
async def test_broadcast_table_state_sends_error(gateway_fanout_module, gateway_ws_module):
    manager = gateway_ws_module.TableStateConnectionManager()
    websocket = FakeWebSocket()
    await manager.connect("round-1", websocket)

    client = FakeGameClient(FakeResponse(status_code=404, text="missing"))
    fanout = gateway_fanout_module.TableStateEventFanout(
        manager=manager,
        client=client,
    )

    await fanout.broadcast_table_state("round-1", trigger_event="bet.placed")

    assert websocket.messages == [{
        "type": "error",
        "round_id": "round-1",
        "trigger": "bet.placed",
        "status_code": 404,
        "detail": "missing",
    }]