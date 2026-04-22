from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from ...application.queries.auth_user_query_service import AuthUserQueryService
from ...domain.schemas import AuthUserResponse
from ...infrastructure.db import SessionLocal
from shared.core.db.session import make_get_db

auth_user_query_router = APIRouter()
get_db = make_get_db(SessionLocal)

@auth_user_query_router.get("/auth-users", response_model=list[AuthUserResponse])
async def list_auth_users(
    limit: int = Query(50, ge=1, le=500),
    offset: int = Query(0, ge=0),
    db: AsyncSession = Depends(get_db),
):
    return await AuthUserQueryService(db).list_users(limit, offset)

@auth_user_query_router.get("/auth-users/{user_id}", response_model=AuthUserResponse)
async def get_auth_user(user_id: int, db: AsyncSession = Depends(get_db)):
    return await AuthUserQueryService(db).get_by_id(user_id)

@auth_user_query_router.get("/auth-users/by-email/{email}", response_model=AuthUserResponse)
async def get_auth_user_by_email(email: str, db: AsyncSession = Depends(get_db)):
    return await AuthUserQueryService(db).get_auth_user_by_email(email)