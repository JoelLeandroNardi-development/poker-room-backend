from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from ...application.commands.table_runtime_command_service import TableRuntimeCommandService
from ...domain.schemas import SessionStatusResponse
from ...infrastructure.db import SessionLocal
from shared.core.db.session import make_get_db

table_runtime_command_router = APIRouter()
get_db = make_get_db(SessionLocal)

@table_runtime_command_router.post("/games/{game_id}/pause")
async def pause_table(game_id: str, db: AsyncSession = Depends(get_db)):
    return await TableRuntimeCommandService(db).pause_table(game_id)

@table_runtime_command_router.post("/games/{game_id}/resume")
async def resume_table(game_id: str, db: AsyncSession = Depends(get_db)):
    return await TableRuntimeCommandService(db).resume_table(game_id)

@table_runtime_command_router.post("/games/{game_id}/record-hand-completed")
async def record_hand_completed(game_id: str, db: AsyncSession = Depends(get_db)):
    return await TableRuntimeCommandService(db).record_hand_completed(game_id)

@table_runtime_command_router.get("/games/{game_id}/session-status", response_model=SessionStatusResponse)
async def get_session_status(game_id: str, db: AsyncSession = Depends(get_db)):
    return await TableRuntimeCommandService(db).get_session_status(game_id)