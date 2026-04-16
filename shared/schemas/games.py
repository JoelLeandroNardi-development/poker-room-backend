from pydantic import BaseModel, Field
from typing import Optional
from datetime import datetime


class StartGame(BaseModel):
    room_id: str = Field(..., min_length=1)

class GameResponse(BaseModel):
    game_id: str
    room_id: str
    status: str
    current_blind_level: int
    level_started_at: Optional[datetime] = None
    current_dealer_seat: int
    current_small_blind_seat: int
    current_big_blind_seat: int
    hands_played: int = 0
    hands_at_current_level: int = 0
    created_at: Optional[datetime] = None

class StartRound(BaseModel):
    pass

class RoundPlayerResponse(BaseModel):
    player_id: str
    seat_number: int
    stack_remaining: int
    committed_this_street: int
    committed_this_hand: int
    has_folded: bool
    is_all_in: bool
    is_active_in_hand: bool


class WinnerShare(BaseModel):
    player_id: str = Field(..., min_length=1)
    amount: int = Field(..., ge=1)

class PotPayout(BaseModel):
    pot_index: int = Field(0, ge=0)
    pot_type: str = Field("main")
    amount: int = Field(..., ge=1)
    winners: list[WinnerShare] = Field(..., min_length=1)

class ResolveHandRequest(BaseModel):
    payouts: list[PotPayout] = Field(..., min_length=1)

class PayoutResponse(BaseModel):
    pot_index: int
    pot_type: str
    player_id: str
    amount: int

class ResolveHandResponse(BaseModel):
    round_id: str
    status: str
    pot_amount: int
    payouts: list[PayoutResponse]

class DeclareWinner(BaseModel):
    winner_player_id: str = Field(..., min_length=1)

class DeclareWinnerResponse(BaseModel):
    round_id: str
    winner_player_id: str
    pot_amount: int
    status: str


class RoundResponse(BaseModel):
    round_id: str
    game_id: str
    round_number: int
    dealer_seat: int
    small_blind_seat: int
    big_blind_seat: int
    small_blind_amount: int
    big_blind_amount: int
    ante_amount: int
    status: str
    pot_amount: int
    street: str
    acting_player_id: Optional[str] = None
    current_highest_bet: int
    minimum_raise_amount: int
    is_action_closed: bool
    players: list[RoundPlayerResponse] = Field(default_factory=list)
    payouts: list[PayoutResponse] = Field(default_factory=list)
    created_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None

class AdvanceBlinds(BaseModel):
    pass

class AdvanceBlindsResponse(BaseModel):
    game_id: str
    new_blind_level: int
    small_blind: int
    big_blind: int
    ante: int

class AdvanceStreetResponse(BaseModel):
    action: str
    round_id: str
    game_id: str
    street: str
    acting_player_id: Optional[str] = None
    current_highest_bet: int
    minimum_raise_amount: int
    is_action_closed: bool
    winning_player_id: Optional[str] = None
    players: list[RoundPlayerResponse] = Field(default_factory=list)

class EndGameResponse(BaseModel):
    game_id: str
    status: str


class ReverseActionRequest(BaseModel):
    original_entry_id: str = Field(..., min_length=1)
    dealer_id: Optional[str] = None
    reason: Optional[str] = None

class AdjustStackRequest(BaseModel):
    player_id: str = Field(..., min_length=1)
    amount: int
    dealer_id: Optional[str] = None
    reason: Optional[str] = None

class ReopenHandRequest(BaseModel):
    dealer_id: Optional[str] = None
    reason: Optional[str] = None

class CorrectPayoutRequest(BaseModel):
    old_player_id: str = Field(..., min_length=1)
    old_amount: int = Field(..., ge=0)
    new_player_id: str = Field(..., min_length=1)
    new_amount: int = Field(..., ge=0)
    dealer_id: Optional[str] = None
    reason: Optional[str] = None

class LedgerEntryResponse(BaseModel):
    entry_id: str
    round_id: str
    entry_type: str
    player_id: Optional[str] = None
    amount: Optional[int] = None
    detail: Optional[dict] = None
    original_entry_id: Optional[str] = None
    dealer_id: Optional[str] = None
    created_at: Optional[datetime] = None

class PlayerSnapshotResponse(BaseModel):
    player_id: str
    stack_adjustment: int
    total_committed: int
    total_won: int

class HandStateResponse(BaseModel):
    round_id: str
    pot_total: int
    is_completed: bool
    is_reopened: bool
    reversed_entry_ids: list[str]
    payout_corrections: list[dict]
    entry_count: int
    players: list[PlayerSnapshotResponse]


class ReplayStepResponse(BaseModel):
    step_number: int
    entry_id: str
    entry_type: str
    player_id: Optional[str] = None
    amount: Optional[int] = None
    pot_total: int
    players: list[PlayerSnapshotResponse]

class ReplayResponse(BaseModel):
    round_id: str
    entry_count: int
    is_consistent: bool
    steps: list[ReplayStepResponse]

class TimelineStreetResponse(BaseModel):
    name: str
    actions: list[dict]

class TimelineResponse(BaseModel):
    round_id: str
    streets: list[TimelineStreetResponse]
    payouts: list[dict]
    corrections: list[dict]

class PotExplanation(BaseModel):
    pot_index: int
    pot_type: str
    amount: int
    contributors: list[str]
    winners: list[dict]

class SettlementExplanationResponse(BaseModel):
    round_id: str
    pots: list[PotExplanation]
    narrative: list[str]

class ConsistencyCheckResponse(BaseModel):
    round_id: str
    is_consistent: bool
    discrepancies: list[str]


class LegalAction(BaseModel):
    action: str
    min_amount: Optional[int] = None
    max_amount: Optional[int] = None

class TableStateResponse(BaseModel):
    round_id: str
    game_id: str
    round_number: int
    street: str
    pot_amount: int
    acting_player_id: Optional[str] = None
    current_highest_bet: int
    minimum_raise_amount: int
    is_action_closed: bool
    state_version: int
    dealer_seat: int
    small_blind_seat: int
    big_blind_seat: int
    last_aggressor_seat: Optional[int] = None
    call_amount: Optional[int] = None
    is_showdown_ready: bool = False
    legal_actions: list[LegalAction] = Field(default_factory=list)
    players: list[RoundPlayerResponse] = Field(default_factory=list)


class SessionStatusResponse(BaseModel):
    game_id: str
    status: str
    hands_played: int
    current_blind_level: int
    hands_at_current_level: int
    hands_until_blind_advance: Optional[int] = None
    max_blind_level: int
    small_blind: Optional[int] = None
    big_blind: Optional[int] = None
    ante: int = 0
    dealer_seat: int
