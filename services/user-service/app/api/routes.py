from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from ..application.commands.user_command_service import UserCommandService
from ..application.queries.user_query_service import UserQueryService
from ..domain.schemas import CreateUser, UpdateUser, UserResponse
from ..infrastructure.db import SessionLocal
from shared.core.db.session import make_get_db

router = APIRouter()
get_db = make_get_db(SessionLocal)

@router.get("/users", response_model=list[UserResponse])
async def list_users(
    limit: int = Query(50, ge=1, le=500),
    offset: int = Query(0, ge=0),
    db: AsyncSession = Depends(get_db),
):
    return await UserQueryService(db).list_users(limit, offset)

@router.get("/users/{email}", response_model=UserResponse)
async def get_user(email: str, db: AsyncSession = Depends(get_db)):
    return await UserQueryService(db).get_user(email)

@router.post("/users", response_model=UserResponse)
async def create_user(data: CreateUser, db: AsyncSession = Depends(get_db)):
    return await UserCommandService(db).create_user(data)

@router.put("/users/{email}", response_model=UserResponse)
async def update_user(email: str, data: UpdateUser, db: AsyncSession = Depends(get_db)):
    return await UserCommandService(db).update_user(email, data)

@router.delete("/users/{email}")
async def delete_user(email: str, db: AsyncSession = Depends(get_db)):
    return await UserCommandService(db).delete_user(email)