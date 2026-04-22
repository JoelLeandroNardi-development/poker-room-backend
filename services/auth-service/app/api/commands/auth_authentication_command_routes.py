from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from ...application.commands.auth_authentication_command_service import AuthAuthenticationCommandService
from ...domain.schemas import Register, Login, TokenPairResponse, RefreshRequest, LogoutRequest
from ...infrastructure.db import SessionLocal
from shared.core.db.session import make_get_db

auth_authentication_command_router = APIRouter()
get_db = make_get_db(SessionLocal)

@auth_authentication_command_router.post("/register")
async def register(data: Register, db: AsyncSession = Depends(get_db)):
    return await AuthAuthenticationCommandService(db).register(data)

@auth_authentication_command_router.post("/login", response_model=TokenPairResponse)
async def login(data: Login, db: AsyncSession = Depends(get_db)):
    return await AuthAuthenticationCommandService(db).login(data)

@auth_authentication_command_router.post("/refresh", response_model=TokenPairResponse)
async def refresh_tokens(payload: RefreshRequest, db: AsyncSession = Depends(get_db)):
    return await AuthAuthenticationCommandService(db).refresh_tokens(payload)

@auth_authentication_command_router.post("/logout")
async def logout(payload: LogoutRequest, db: AsyncSession = Depends(get_db)):
    return await AuthAuthenticationCommandService(db).logout(payload)