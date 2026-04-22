from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from ...application.commands.auth_user_command_service import AuthUserCommandService
from ...domain.schemas import AuthUserResponse, UpdateAuthUser
from ...infrastructure.db import SessionLocal
from shared.core.db.session import make_get_db

auth_user_command_router = APIRouter()
get_db = make_get_db(SessionLocal)

@auth_user_command_router.put("/auth-users/{user_id}", response_model=AuthUserResponse)
async def update_auth_user(
    user_id: int,
    data: UpdateAuthUser,
    db: AsyncSession = Depends(get_db),
):
    return await AuthUserCommandService(db).update_auth_user(user_id, data)

@auth_user_command_router.delete("/auth-users/{user_id}")
async def delete_auth_user(user_id: int, db: AsyncSession = Depends(get_db)):
    return await AuthUserCommandService(db).delete_auth_user(user_id)