from pydantic import BaseModel, Field
from typing import Optional
from datetime import datetime

class CreateRoom(BaseModel):
    name: Optional[str] = None
    max_players: int = Field(..., ge=2, le=10)
    starting_chips: int = Field(..., gt=0)
    antes_enabled: bool = False
    created_by: str = Field(..., min_length=1)

class BlindLevelInput(BaseModel):
    level: int = Field(..., ge=1)
    small_blind: int = Field(..., gt=0)
    big_blind: int = Field(..., gt=0)
    ante: int = Field(0, ge=0)
    duration_minutes: int = Field(..., gt=0)

class SetBlindStructure(BaseModel):
    levels: list[BlindLevelInput] = Field(..., min_length=1)
    starting_dealer_seat: int = Field(1, ge=1)

class JoinRoom(BaseModel):
    player_name: str = Field(..., min_length=1)

class RoomResponse(BaseModel):
    room_id: str
    code: str
    name: Optional[str] = None
    status: str
    max_players: int
    starting_chips: int
    antes_enabled: bool
    created_by: str
    created_at: Optional[datetime] = None

class RoomPlayerResponse(BaseModel):
    player_id: str
    room_id: str
    player_name: str
    seat_number: int
    chip_count: int
    is_active: bool
    is_eliminated: bool
    joined_at: Optional[datetime] = None

class BlindLevelResponse(BaseModel):
    level: int
    small_blind: int
    big_blind: int
    ante: int
    duration_minutes: int

class RoomDetailResponse(BaseModel):
    room: RoomResponse
    players: list[RoomPlayerResponse]
    blind_levels: list[BlindLevelResponse]
    starting_dealer_seat: int

class UpdateChips(BaseModel):
    chip_count: int = Field(..., ge=0)

class DeleteRoomResponse(BaseModel):
    message: str
    room_id: str