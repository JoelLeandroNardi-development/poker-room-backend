from __future__ import annotations

import asyncio

from fastapi import WebSocket, WebSocketDisconnect

class TableStateConnectionManager:
    def __init__(self) -> None:
        self._connections: dict[str, dict[WebSocket, asyncio.Lock]] = {}
        self._lock = asyncio.Lock()

    async def connect(self, round_id: str, websocket: WebSocket) -> None:
        await websocket.accept()
        async with self._lock:
            self._connections.setdefault(round_id, {})[websocket] = asyncio.Lock()

    async def disconnect(self, round_id: str, websocket: WebSocket) -> None:
        async with self._lock:
            round_connections = self._connections.get(round_id)
            if not round_connections:
                return

            round_connections.pop(websocket, None)
            if not round_connections:
                self._connections.pop(round_id, None)

    async def has_subscribers(self, round_id: str) -> bool:
        async with self._lock:
            return bool(self._connections.get(round_id))

    async def subscriber_count(self, round_id: str) -> int:
        async with self._lock:
            return len(self._connections.get(round_id, {}))

    async def send_json(self, round_id: str, websocket: WebSocket, payload: dict) -> bool:
        lock = await self._connection_lock(round_id, websocket)
        if lock is None:
            return False

        try:
            async with lock:
                await websocket.send_json(payload)
            return True
        except WebSocketDisconnect:
            await self.disconnect(round_id, websocket)
            return False
        except RuntimeError:
            await self.disconnect(round_id, websocket)
            return False

    async def broadcast_json(self, round_id: str, payload: dict) -> int:
        async with self._lock:
            targets = list(self._connections.get(round_id, {}).keys())

        sent = 0
        for websocket in targets:
            if await self.send_json(round_id, websocket, payload):
                sent += 1
        return sent

    async def _connection_lock(
        self,
        round_id: str,
        websocket: WebSocket,
    ) -> asyncio.Lock | None:
        async with self._lock:
            return self._connections.get(round_id, {}).get(websocket)

table_state_connections = TableStateConnectionManager()