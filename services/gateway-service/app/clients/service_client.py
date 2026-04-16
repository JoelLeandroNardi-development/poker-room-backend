from __future__ import annotations

import httpx

from ..config import (
    AUTH_SERVICE_URL,
    USER_SERVICE_URL,
    ROOM_SERVICE_URL,
    GAME_SERVICE_URL,
)

DEFAULT_TIMEOUT = 10.0

class ServiceClient:
    """Thin async HTTP client wrapping a persistent httpx.AsyncClient."""

    CORRELATION_HEADER = "X-Correlation-ID"

    def __init__(self, base_url: str, timeout: float = DEFAULT_TIMEOUT):
        self.base_url = base_url
        self.timeout = timeout
        self._client: httpx.AsyncClient | None = None

    def _get_client(self) -> httpx.AsyncClient:
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(
                base_url=self.base_url, timeout=self.timeout,
            )
        return self._client

    async def close(self) -> None:
        if self._client and not self._client.is_closed:
            await self._client.aclose()
            self._client = None

    def _inject_correlation(self, kwargs: dict) -> dict:
        """Forward X-Correlation-ID if available from caller-supplied headers."""
        return kwargs

    async def get(self, path: str, **kwargs) -> httpx.Response:
        return await self._get_client().get(path, **self._inject_correlation(kwargs))

    async def post(self, path: str, **kwargs) -> httpx.Response:
        return await self._get_client().post(path, **self._inject_correlation(kwargs))

    async def put(self, path: str, **kwargs) -> httpx.Response:
        return await self._get_client().put(path, **self._inject_correlation(kwargs))

    async def delete(self, path: str, **kwargs) -> httpx.Response:
        return await self._get_client().delete(path, **self._inject_correlation(kwargs))

auth_client = ServiceClient(AUTH_SERVICE_URL)
user_client = ServiceClient(USER_SERVICE_URL)
room_client = ServiceClient(ROOM_SERVICE_URL)
game_client = ServiceClient(GAME_SERVICE_URL)