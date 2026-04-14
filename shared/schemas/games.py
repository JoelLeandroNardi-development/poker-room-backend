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
    created_at: Optional[datetime] = None

class StartRound(BaseModel):
    pass

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
    winner_player_id: Optional[str] = None
    pot_amount: int
    created_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None

class DeclareWinner(BaseModel):
    winner_player_id: str = Field(..., min_length=1)

class DeclareWinnerResponse(BaseModel):
    round_id: str
    winner_player_id: str
    pot_amount: int
    status: str

class AdvanceBlinds(BaseModel):
    pass

class AdvanceBlindsResponse(BaseModel):
    game_id: str
    new_blind_level: int
    small_blind: int
    big_blind: int
    ante: int

class EndGameResponse(BaseModel):
    game_id: str
    status: str