from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from ..application.commands.game_command_service import GameCommandService
from ..application.commands.correction_command_service import CorrectionCommandService
from ..application.commands.bet_command_service import BetCommandService
from ..application.queries.game_query_service import GameQueryService
from ..application.queries.bet_query_service import BetQueryService
from ..application.mappers import ledger_entry_to_response, hand_state_to_response
from ..domain.schemas import (
    StartGame, GameResponse, RoundResponse,
    DeclareWinner, DeclareWinnerResponse,
    ResolveHandRequest, ResolveHandResponse,
    AdvanceBlindsResponse, AdvanceStreetResponse, EndGameResponse,
    ReverseActionRequest, AdjustStackRequest, ReopenHandRequest,
    CorrectPayoutRequest, LedgerEntryResponse, HandStateResponse,
)
from shared.schemas.bets import PlaceBet, BetResponse, PotResponse, PlayerBetSummary
from ..infrastructure.db import SessionLocal
from shared.core.db.session import make_get_db

router = APIRouter()
get_db = make_get_db(SessionLocal)

@router.post("/games", response_model=GameResponse)
async def start_game(data: StartGame, db: AsyncSession = Depends(get_db)):
    return await GameCommandService(db).start_game(data)

@router.get("/games/{game_id}", response_model=GameResponse)
async def get_game(game_id: str, db: AsyncSession = Depends(get_db)):
    return await GameQueryService(db).get_game(game_id)

@router.get("/games/room/{room_id}", response_model=GameResponse | None)
async def get_game_for_room(room_id: str, db: AsyncSession = Depends(get_db)):
    return await GameQueryService(db).get_game_for_room(room_id)

@router.post("/games/{game_id}/rounds", response_model=RoundResponse)
async def start_round(game_id: str, db: AsyncSession = Depends(get_db)):
    return await GameCommandService(db).start_round(game_id)

@router.get("/games/{game_id}/rounds", response_model=list[RoundResponse])
async def list_rounds(game_id: str, db: AsyncSession = Depends(get_db)):
    return await GameQueryService(db).list_rounds(game_id)

@router.get("/games/{game_id}/rounds/active", response_model=RoundResponse | None)
async def get_active_round(game_id: str, db: AsyncSession = Depends(get_db)):
    return await GameQueryService(db).get_active_round(game_id)

@router.get("/rounds/{round_id}", response_model=RoundResponse)
async def get_round(round_id: str, db: AsyncSession = Depends(get_db)):
    return await GameQueryService(db).get_round(round_id)

@router.post("/rounds/{round_id}/resolve", response_model=ResolveHandResponse)
async def resolve_hand(round_id: str, data: ResolveHandRequest, db: AsyncSession = Depends(get_db)):
    return await GameCommandService(db).resolve_hand(round_id, data)

@router.post("/rounds/{round_id}/advance-street", response_model=AdvanceStreetResponse)
async def advance_street(round_id: str, db: AsyncSession = Depends(get_db)):
    return await GameCommandService(db).advance_street(round_id)

@router.post("/rounds/{round_id}/winner", response_model=DeclareWinnerResponse)
async def declare_winner(round_id: str, data: DeclareWinner, db: AsyncSession = Depends(get_db)):
    return await GameCommandService(db).declare_winner(round_id, data)

@router.post("/games/{game_id}/advance-blinds", response_model=AdvanceBlindsResponse)
async def advance_blinds(game_id: str, db: AsyncSession = Depends(get_db)):
    return await GameCommandService(db).advance_blinds(game_id)

@router.post("/games/{game_id}/end", response_model=EndGameResponse)
async def end_game(game_id: str, db: AsyncSession = Depends(get_db)):
    return await GameCommandService(db).end_game(game_id)


# ── Dealer correction endpoints ──────────────────────────────────────

@router.get("/rounds/{round_id}/ledger", response_model=list[LedgerEntryResponse])
async def get_ledger(round_id: str, db: AsyncSession = Depends(get_db)):
    svc = CorrectionCommandService(db)
    entries = await svc.get_ledger(round_id)
    return [ledger_entry_to_response(e) for e in entries]

@router.get("/rounds/{round_id}/hand-state", response_model=HandStateResponse)
async def get_hand_state(round_id: str, db: AsyncSession = Depends(get_db)):
    svc = CorrectionCommandService(db)
    state = await svc.get_hand_state(round_id)
    return hand_state_to_response(round_id, state)

@router.post("/rounds/{round_id}/corrections/reverse-action", response_model=LedgerEntryResponse)
async def reverse_action(round_id: str, data: ReverseActionRequest, db: AsyncSession = Depends(get_db)):
    svc = CorrectionCommandService(db)
    entry = await svc.reverse_action(
        round_id, data.original_entry_id,
        dealer_id=data.dealer_id, reason=data.reason,
    )
    return ledger_entry_to_response(entry)

@router.post("/rounds/{round_id}/corrections/adjust-stack", response_model=LedgerEntryResponse)
async def adjust_stack(round_id: str, data: AdjustStackRequest, db: AsyncSession = Depends(get_db)):
    svc = CorrectionCommandService(db)
    entry = await svc.adjust_stack(
        round_id, data.player_id, data.amount,
        dealer_id=data.dealer_id, reason=data.reason,
    )
    return ledger_entry_to_response(entry)

@router.post("/rounds/{round_id}/corrections/reopen-hand", response_model=LedgerEntryResponse)
async def reopen_hand(round_id: str, data: ReopenHandRequest, db: AsyncSession = Depends(get_db)):
    svc = CorrectionCommandService(db)
    entry = await svc.reopen_hand(
        round_id, dealer_id=data.dealer_id, reason=data.reason,
    )
    return ledger_entry_to_response(entry)

@router.post("/rounds/{round_id}/corrections/correct-payout", response_model=LedgerEntryResponse)
async def correct_payout(round_id: str, data: CorrectPayoutRequest, db: AsyncSession = Depends(get_db)):
    svc = CorrectionCommandService(db)
    entry = await svc.correct_payout(
        round_id,
        old_player_id=data.old_player_id, old_amount=data.old_amount,
        new_player_id=data.new_player_id, new_amount=data.new_amount,
        dealer_id=data.dealer_id, reason=data.reason,
    )
    return ledger_entry_to_response(entry)


# ── Betting endpoints (consolidated from betting-service) ────────

@router.post("/bets", response_model=BetResponse)
async def place_bet(data: PlaceBet, db: AsyncSession = Depends(get_db)):
    return await BetCommandService(db).place_bet(data)

@router.get("/bets/round/{round_id}", response_model=list[BetResponse])
async def get_bets_for_round(round_id: str, db: AsyncSession = Depends(get_db)):
    return await BetQueryService(db).get_bets_for_round(round_id)

@router.get("/bets/round/{round_id}/pot", response_model=PotResponse)
async def get_pot(round_id: str, db: AsyncSession = Depends(get_db)):
    return await BetQueryService(db).get_pot(round_id)

@router.get("/bets/round/{round_id}/players", response_model=list[PlayerBetSummary])
async def get_player_summaries(round_id: str, db: AsyncSession = Depends(get_db)):
    return await BetQueryService(db).get_player_summaries(round_id)