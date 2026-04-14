from __future__ import annotations

from fastapi import HTTPException
from httpx import Response


def forward_response(resp: Response) -> dict:
    if resp.status_code >= 400:
        try:
            detail = resp.json().get("detail", resp.text)
        except Exception:
            detail = resp.text
        raise HTTPException(status_code=resp.status_code, detail=detail)
    return resp.json()
