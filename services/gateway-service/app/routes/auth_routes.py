from __future__ import annotations

from fastapi import APIRouter, Query

from ..clients.service_client import auth_client
from ..utils.proxy import forward_response
from shared.schemas.auth import (
    Register, RegisterResponse, Login, TokenPairResponse,
    RefreshRequest, LogoutRequest, AuthActionResponse,
    AuthUserResponse, UpdateAuthUser, DeleteAuthUserResponse,
    ForgotPasswordRequest, ResetPasswordRequest,
)

router = APIRouter(tags=["auth"])

@router.post("/register", response_model=RegisterResponse)
async def register(data: Register):
    resp = await auth_client.post("/register", json=data.model_dump())
    return forward_response(resp)

@router.post("/login", response_model=TokenPairResponse)
async def login(data: Login):
    resp = await auth_client.post("/login", json=data.model_dump())
    return forward_response(resp)

@router.post("/refresh", response_model=TokenPairResponse)
async def refresh_tokens(data: RefreshRequest):
    resp = await auth_client.post("/refresh", json=data.model_dump())
    return forward_response(resp)

@router.post("/logout", response_model=AuthActionResponse)
async def logout(data: LogoutRequest):
    resp = await auth_client.post("/logout", json=data.model_dump())
    return forward_response(resp)

@router.post("/forgot-password", response_model=AuthActionResponse)
async def forgot_password(data: ForgotPasswordRequest):
    resp = await auth_client.post("/forgot-password", json=data.model_dump())
    return forward_response(resp)

@router.post("/reset-password", response_model=AuthActionResponse)
async def reset_password(data: ResetPasswordRequest):
    resp = await auth_client.post("/reset-password", json=data.model_dump())
    return forward_response(resp)

@router.get("/auth-users", response_model=list[AuthUserResponse])
async def list_auth_users(
    limit: int = Query(50, ge=1, le=500),
    offset: int = Query(0, ge=0),
):
    resp = await auth_client.get("/auth-users", params={"limit": limit, "offset": offset})
    return forward_response(resp)

@router.get("/auth-users/{user_id}", response_model=AuthUserResponse)
async def get_auth_user(user_id: int):
    resp = await auth_client.get(f"/auth-users/{user_id}")
    return forward_response(resp)

@router.get("/auth-users/by-email/{email}", response_model=AuthUserResponse)
async def get_auth_user_by_email(email: str):
    resp = await auth_client.get(f"/auth-users/by-email/{email}")
    return forward_response(resp)

@router.put("/auth-users/{user_id}", response_model=AuthUserResponse)
async def update_auth_user(user_id: int, data: UpdateAuthUser):
    resp = await auth_client.put(f"/auth-users/{user_id}", json=data.model_dump(exclude_none=True))
    return forward_response(resp)

@router.delete("/auth-users/{user_id}", response_model=DeleteAuthUserResponse)
async def delete_auth_user(user_id: int):
    resp = await auth_client.delete(f"/auth-users/{user_id}")
    return forward_response(resp)
