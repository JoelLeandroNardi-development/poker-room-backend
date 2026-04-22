from __future__ import annotations

import logging
from typing import Any, Protocol

from .table_state_ws import TableStateConnectionManager, table_state_connections
from ..clients.service_client import game_client

logger = logging.getLogger(__name__)

class GameServiceClient(Protocol):
    async def get(self, path: str, **kwargs):
        ...

def extract_round_id(event: dict[str, Any]) -> str | None:
    data = event.get("data")
    if not isinstance(data, dict):
        return None

    round_id = data.get("round_id")
    return str(round_id) if round_id else None

class TableStateEventFanout:
    def __init__(
        self,
        *,
        manager: TableStateConnectionManager = table_state_connections,
        client: GameServiceClient = game_client,
    ) -> None:
        self.manager = manager
        self.client = client

    async def handle_event(self, event: dict[str, Any]) -> None:
        round_id = extract_round_id(event)
        if not round_id or not await self.manager.has_subscribers(round_id):
            return

        await self.broadcast_table_state(
            round_id,
            trigger_event=event.get("event_type"),
        )

    async def broadcast_table_state(
        self,
        round_id: str,
        *,
        trigger_event: str | None = None,
    ) -> int:
        resp = await self.client.get(f"/rounds/{round_id}/table-state")
        if resp.status_code >= 400:
            return await self.manager.broadcast_json(
                round_id,
                {
                    "type": "error",
                    "round_id": round_id,
                    "trigger": trigger_event,
                    "status_code": resp.status_code,
                    "detail": resp.text,
                },
            )

        sent = await self.manager.broadcast_json(
            round_id,
            {
                "type": "table_state",
                "round_id": round_id,
                "trigger": trigger_event,
                "data": resp.json(),
            },
        )

        logger.debug(
            "broadcast table state round_id=%s trigger=%s subscribers=%s",
            round_id,
            trigger_event,
            sent,
        )
        return sent

table_state_fanout = TableStateEventFanout()