from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from ..application.commands.auth_command_service import AuthCommandService
from ..application.commands.auth_user_command_service import AuthUserCommandService
from ..application.queries.auth_user_query_service import AuthUserQueryService
from ..domain.schemas import (
    Register,
    Login,
    TokenPairResponse,
    RefreshRequest,
    LogoutRequest,
    AuthUserResponse,
    UpdateAuthUser,
)
from ..infrastructure.db import SessionLocal
from shared.core.db.session import make_get_db

router = APIRouter()
get_db = make_get_db(SessionLocal)


@router.post("/register")
async def register(data: Register, db: AsyncSession = Depends(get_db)):
    return await AuthCommandService(db).register(data)


@router.post("/login", response_model=TokenPairResponse)
async def login(data: Login, db: AsyncSession = Depends(get_db)):
    return await AuthCommandService(db).login(data)


@router.post("/refresh", response_model=TokenPairResponse)
async def refresh_tokens(payload: RefreshRequest, db: AsyncSession = Depends(get_db)):
    return await AuthCommandService(db).refresh_tokens(payload)


@router.post("/logout")
async def logout(payload: LogoutRequest, db: AsyncSession = Depends(get_db)):
    return await AuthCommandService(db).logout(payload)


@router.get("/auth-users", response_model=list[AuthUserResponse])
async def list_auth_users(
    limit: int = Query(50, ge=1, le=500),
    offset: int = Query(0, ge=0),
    db: AsyncSession = Depends(get_db),
):
    return await AuthUserQueryService(db).list_users(limit, offset)


@router.get("/auth-users/{user_id}", response_model=AuthUserResponse)
async def get_auth_user(user_id: int, db: AsyncSession = Depends(get_db)):
    return await AuthUserQueryService(db).get_by_id(user_id)


@router.get("/auth-users/by-email/{email}", response_model=AuthUserResponse)
async def get_auth_user_by_email(email: str, db: AsyncSession = Depends(get_db)):
    return await AuthUserQueryService(db).get_auth_user_by_email(email)


@router.put("/auth-users/{user_id}", response_model=AuthUserResponse)
async def update_auth_user(
    user_id: int,
    data: UpdateAuthUser,
    db: AsyncSession = Depends(get_db),
):
    return await AuthUserCommandService(db).update_auth_user(user_id, data)


@router.delete("/auth-users/{user_id}")
async def delete_auth_user(user_id: int, db: AsyncSession = Depends(get_db)):
    return await AuthUserCommandService(db).delete_auth_user(user_id)
