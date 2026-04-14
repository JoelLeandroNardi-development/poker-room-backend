from __future__ import annotations

from fastapi import APIRouter, Request

from ..clients.service_client import user_client
from ..utils.proxy import forward_response

router = APIRouter(tags=["users"])


@router.get("/users")
async def list_users(request: Request):
    resp = await user_client.get("/users", params=dict(request.query_params))
    return forward_response(resp)


@router.get("/users/{email}")
async def get_user(email: str):
    resp = await user_client.get(f"/users/{email}")
    return forward_response(resp)


@router.post("/users")
async def create_user(request: Request):
    body = await request.json()
    resp = await user_client.post("/users", json=body)
    return forward_response(resp)


@router.put("/users/{email}")
async def update_user(email: str, request: Request):
    body = await request.json()
    resp = await user_client.put(f"/users/{email}", json=body)
    return forward_response(resp)


@router.delete("/users/{email}")
async def delete_user(email: str):
    resp = await user_client.delete(f"/users/{email}")
    return forward_response(resp)
