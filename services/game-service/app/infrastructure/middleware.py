from __future__ import annotations

import time
import uuid

from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import Response

from .logging import correlation_id_ctx, get_logger

logger = get_logger("game-service.middleware")

CORRELATION_HEADER = "X-Correlation-ID"

class CorrelationIdMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        cid = request.headers.get(CORRELATION_HEADER) or str(uuid.uuid4())
        token = correlation_id_ctx.set(cid)

        start = time.perf_counter()
        try:
            response = await call_next(request)
        finally:
            elapsed_ms = (time.perf_counter() - start) * 1000
            logger.info(
                f"{request.method} {request.url.path} -> {response.status_code if 'response' in dir() else 500}",
                method=request.method,
                path=str(request.url.path),
                status=getattr(response, "status_code", 500) if "response" in dir() else 500,
                duration_ms=round(elapsed_ms, 2),
            )
            correlation_id_ctx.reset(token)

        response.headers[CORRELATION_HEADER] = cid
        return response