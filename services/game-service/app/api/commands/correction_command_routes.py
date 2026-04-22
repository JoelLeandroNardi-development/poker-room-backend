from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from ...application.commands.correction_command_service import CorrectionCommandService
from ...application.mappers import ledger_entry_to_response, hand_state_to_response
from ...domain.schemas import (
    ReverseActionRequest, AdjustStackRequest, ReopenHandRequest,
    CorrectPayoutRequest, LedgerEntryResponse, HandStateResponse
)
from ...infrastructure.db import SessionLocal
from shared.core.db.session import make_get_db

correction_command_router = APIRouter()
get_db = make_get_db(SessionLocal)

@correction_command_router.get("/rounds/{round_id}/ledger", response_model=list[LedgerEntryResponse])
async def get_ledger(round_id: str, db: AsyncSession = Depends(get_db)):
    svc = CorrectionCommandService(db)
    entries = await svc.get_ledger(round_id)
    return [ledger_entry_to_response(e) for e in entries]

@correction_command_router.get("/rounds/{round_id}/hand-state", response_model=HandStateResponse)
async def get_hand_state(round_id: str, db: AsyncSession = Depends(get_db)):
    svc = CorrectionCommandService(db)
    state = await svc.get_hand_state(round_id)
    return hand_state_to_response(round_id, state)

@correction_command_router.post("/rounds/{round_id}/corrections/reverse-action", response_model=LedgerEntryResponse)
async def reverse_action(round_id: str, data: ReverseActionRequest, db: AsyncSession = Depends(get_db)):
    svc = CorrectionCommandService(db)
    entry = await svc.reverse_action(
        round_id, data.original_entry_id,
        dealer_id=data.dealer_id, reason=data.reason,
    )
    return ledger_entry_to_response(entry)

@correction_command_router.post("/rounds/{round_id}/corrections/adjust-stack", response_model=LedgerEntryResponse)
async def adjust_stack(round_id: str, data: AdjustStackRequest, db: AsyncSession = Depends(get_db)):
    svc = CorrectionCommandService(db)
    entry = await svc.adjust_stack(
        round_id, data.player_id, data.amount,
        dealer_id=data.dealer_id, reason=data.reason,
    )
    return ledger_entry_to_response(entry)

@correction_command_router.post("/rounds/{round_id}/corrections/reopen-hand", response_model=LedgerEntryResponse)
async def reopen_hand(round_id: str, data: ReopenHandRequest, db: AsyncSession = Depends(get_db)):
    svc = CorrectionCommandService(db)
    entry = await svc.reopen_hand(
        round_id, dealer_id=data.dealer_id, reason=data.reason,
    )
    return ledger_entry_to_response(entry)

@correction_command_router.post("/rounds/{round_id}/corrections/correct-payout", response_model=LedgerEntryResponse)
async def correct_payout(round_id: str, data: CorrectPayoutRequest, db: AsyncSession = Depends(get_db)):
    svc = CorrectionCommandService(db)
    entry = await svc.correct_payout(
        round_id,
        old_player_id=data.old_player_id, old_amount=data.old_amount,
        new_player_id=data.new_player_id, new_amount=data.new_amount,
        dealer_id=data.dealer_id, reason=data.reason,
    )
    return ledger_entry_to_response(entry)