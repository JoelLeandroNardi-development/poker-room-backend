from __future__ import annotations

from fastapi import APIRouter, Query

from ..clients.service_client import user_client
from ..utils.proxy import forward_response
from shared.schemas.users import CreateUser, UpdateUser, UserResponse, DeleteUserResponse

router = APIRouter(tags=["users"])

@router.get("/users", response_model=list[UserResponse])
async def list_users(
    limit: int = Query(50, ge=1, le=500),
    offset: int = Query(0, ge=0),
):
    resp = await user_client.get("/users", params={"limit": limit, "offset": offset})
    return forward_response(resp)

@router.get("/users/{email}", response_model=UserResponse)
async def get_user(email: str):
    resp = await user_client.get(f"/users/{email}")
    return forward_response(resp)

@router.post("/users", response_model=UserResponse)
async def create_user(data: CreateUser):
    resp = await user_client.post("/users", json=data.model_dump())
    return forward_response(resp)

@router.put("/users/{email}", response_model=UserResponse)
async def update_user(email: str, data: UpdateUser):
    resp = await user_client.put(f"/users/{email}", json=data.model_dump(exclude_none=True))
    return forward_response(resp)

@router.delete("/users/{email}", response_model=DeleteUserResponse)
async def delete_user(email: str):
    resp = await user_client.delete(f"/users/{email}")
    return forward_response(resp)