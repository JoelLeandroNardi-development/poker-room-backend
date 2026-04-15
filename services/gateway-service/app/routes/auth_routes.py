from __future__ import annotations

from fastapi import APIRouter, Request

from ..clients.service_client import auth_client
from ..utils.proxy import forward_response

router = APIRouter(tags=["auth"])

@router.post("/register")
async def register(request: Request):
    body = await request.json()
    resp = await auth_client.post("/register", json=body)
    return forward_response(resp)

@router.post("/login")
async def login(request: Request):
    body = await request.json()
    resp = await auth_client.post("/login", json=body)
    return forward_response(resp)

@router.post("/refresh")
async def refresh_tokens(request: Request):
    body = await request.json()
    resp = await auth_client.post("/refresh", json=body)
    return forward_response(resp)

@router.post("/logout")
async def logout(request: Request):
    body = await request.json()
    resp = await auth_client.post("/logout", json=body)
    return forward_response(resp)

@router.get("/auth-users")
async def list_auth_users(request: Request):
    resp = await auth_client.get("/auth-users", params=dict(request.query_params))
    return forward_response(resp)

@router.get("/auth-users/{user_id}")
async def get_auth_user(user_id: int):
    resp = await auth_client.get(f"/auth-users/{user_id}")
    return forward_response(resp)

@router.get("/auth-users/by-email/{email}")
async def get_auth_user_by_email(email: str):
    resp = await auth_client.get(f"/auth-users/by-email/{email}")
    return forward_response(resp)

@router.put("/auth-users/{user_id}")
async def update_auth_user(user_id: int, request: Request):
    body = await request.json()
    resp = await auth_client.put(f"/auth-users/{user_id}", json=body)
    return forward_response(resp)

@router.delete("/auth-users/{user_id}")
async def delete_auth_user(user_id: int):
    resp = await auth_client.delete(f"/auth-users/{user_id}")
    return forward_response(resp)