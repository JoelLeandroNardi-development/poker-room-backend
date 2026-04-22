from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from ...application.queries.user_query_service import UserQueryService
from ...domain.schemas import UserResponse
from ...infrastructure.db import SessionLocal
from shared.core.db.session import make_get_db

user_query_router = APIRouter()
get_db = make_get_db(SessionLocal)

@user_query_router.get("/users", response_model=list[UserResponse])
async def list_users(
    limit: int = Query(50, ge=1, le=500),
    offset: int = Query(0, ge=0),
    db: AsyncSession = Depends(get_db),
):
    return await UserQueryService(db).list_users(limit, offset)

@user_query_router.get("/users/{email}", response_model=UserResponse)
async def get_user(email: str, db: AsyncSession = Depends(get_db)):
    return await UserQueryService(db).get_user(email)