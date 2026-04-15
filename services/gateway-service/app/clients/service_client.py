from __future__ import annotations

import httpx

from ..config import (
    AUTH_SERVICE_URL,
    USER_SERVICE_URL,
    ROOM_SERVICE_URL,
    GAME_SERVICE_URL,
    BETTING_SERVICE_URL,
)

DEFAULT_TIMEOUT = 10.0

class ServiceClient:
    def __init__(self, base_url: str, timeout: float = DEFAULT_TIMEOUT):
        self.base_url = base_url
        self.timeout = timeout

    async def get(self, path: str, **kwargs) -> httpx.Response:
        async with httpx.AsyncClient(base_url=self.base_url, timeout=self.timeout) as client:
            return await client.get(path, **kwargs)

    async def post(self, path: str, **kwargs) -> httpx.Response:
        async with httpx.AsyncClient(base_url=self.base_url, timeout=self.timeout) as client:
            return await client.post(path, **kwargs)

    async def put(self, path: str, **kwargs) -> httpx.Response:
        async with httpx.AsyncClient(base_url=self.base_url, timeout=self.timeout) as client:
            return await client.put(path, **kwargs)

    async def delete(self, path: str, **kwargs) -> httpx.Response:
        async with httpx.AsyncClient(base_url=self.base_url, timeout=self.timeout) as client:
            return await client.delete(path, **kwargs)

auth_client = ServiceClient(AUTH_SERVICE_URL)
user_client = ServiceClient(USER_SERVICE_URL)
room_client = ServiceClient(ROOM_SERVICE_URL)
game_client = ServiceClient(GAME_SERVICE_URL)
betting_client = ServiceClient(BETTING_SERVICE_URL)