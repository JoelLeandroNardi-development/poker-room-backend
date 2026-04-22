from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from ...application.commands.auth_password_command_service import AuthPasswordCommandService
from ...domain.schemas import ForgotPasswordRequest, ResetPasswordRequest, AuthActionResponse
from ...infrastructure.db import SessionLocal
from shared.core.db.session import make_get_db

auth_password_command_router = APIRouter()
get_db = make_get_db(SessionLocal)

@auth_password_command_router.post("/forgot-password", response_model=AuthActionResponse)
async def forgot_password(payload: ForgotPasswordRequest, db: AsyncSession = Depends(get_db)):
    return await AuthPasswordCommandService(db).forgot_password(payload)

@auth_password_command_router.post("/reset-password", response_model=AuthActionResponse)
async def reset_password(payload: ResetPasswordRequest, db: AsyncSession = Depends(get_db)):
    return await AuthPasswordCommandService(db).reset_password(payload)