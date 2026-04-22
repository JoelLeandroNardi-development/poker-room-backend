from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from ...application.commands.user_command_service import UserCommandService
from ...domain.schemas import CreateUser, UpdateUser, UserResponse
from ...infrastructure.db import SessionLocal
from shared.core.db.session import make_get_db

user_command_router = APIRouter()
get_db = make_get_db(SessionLocal)

@user_command_router.post("/users", response_model=UserResponse)
async def create_user(data: CreateUser, db: AsyncSession = Depends(get_db)):
    return await UserCommandService(db).create_user(data)

@user_command_router.put("/users/{email}", response_model=UserResponse)
async def update_user(email: str, data: UpdateUser, db: AsyncSession = Depends(get_db)):
    return await UserCommandService(db).update_user(email, data)

@user_command_router.delete("/users/{email}")
async def delete_user(email: str, db: AsyncSession = Depends(get_db)):
    return await UserCommandService(db).delete_user(email)