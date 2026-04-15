from __future__ import annotations

import json
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock

ENCODING_UTF8 = "utf-8"
CONTENT_TYPE_JSON = "application/json"
HEADER_RETRY_COUNT = "x-retry-count"

SAMPLE_DT = datetime(2026, 3, 17, 10, 0, 0, tzinfo=timezone.utc)

class MockMessage:
    def __init__(self, body: dict, headers: dict | None = None, retry_count: int = 0):
        self.body = json.dumps(body).encode(ENCODING_UTF8)
        self.headers = headers or {}
        self.headers[HEADER_RETRY_COUNT] = retry_count
        self.content_type = CONTENT_TYPE_JSON
        self.ack_called = False
        self.reject_called = False
        self.reject_requeue = False
        self.nack_called = False

    async def ack(self):
        self.ack_called = True

    async def reject(self, requeue: bool = False):
        self.reject_called = True
        self.reject_requeue = requeue

    async def nack(self, requeue: bool = False):
        self.nack_called = True