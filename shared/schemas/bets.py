from pydantic import BaseModel, Field
from typing import Optional
from datetime import datetime

class PlaceBet(BaseModel):
    round_id: str = Field(..., min_length=1)
    player_id: str = Field(..., min_length=1)
    action: str = Field(..., min_length=1)
    amount: int = Field(0, ge=0)
    idempotency_key: Optional[str] = None
    expected_version: Optional[int] = None

class BetResponse(BaseModel):
    bet_id: str
    round_id: str
    player_id: str
    action: str
    amount: int
    created_at: Optional[datetime] = None

class PotResponse(BaseModel):
    round_id: str
    total_pot: int
    bets: list[BetResponse]

class PlayerBetSummary(BaseModel):
    player_id: str
    total_bet: int
    last_action: str
    is_folded: bool