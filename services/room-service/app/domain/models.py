from sqlalchemy import Column, Integer, String, DateTime, Boolean
from sqlalchemy.sql import func

from .constants import RoomStatus, TableName
from ..infrastructure.db import Base
from shared.core.outbox.model import make_outbox_event_model

class Room(Base):
    __tablename__ = TableName.ROOMS

    id = Column(Integer, primary_key=True)
    room_id = Column(String, unique=True, nullable=False, index=True)
    code = Column(String(4), unique=True, nullable=False, index=True)
    name = Column(String, nullable=True)
    status = Column(String, nullable=False, default=RoomStatus.WAITING)
    max_players = Column(Integer, nullable=False)
    starting_chips = Column(Integer, nullable=False)
    antes_enabled = Column(Boolean, nullable=False, default=False)
    starting_dealer_seat = Column(Integer, nullable=False, default=1)
    created_by = Column(String, nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

class RoomPlayer(Base):
    __tablename__ = TableName.ROOM_PLAYERS

    id = Column(Integer, primary_key=True)
    room_id = Column(String, nullable=False, index=True)
    player_id = Column(String, unique=True, nullable=False, index=True)
    player_name = Column(String, nullable=False)
    seat_number = Column(Integer, nullable=False)
    chip_count = Column(Integer, nullable=False)
    is_active = Column(Boolean, nullable=False, default=True)
    is_eliminated = Column(Boolean, nullable=False, default=False)
    joined_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

class BlindLevel(Base):
    __tablename__ = TableName.BLIND_LEVELS

    id = Column(Integer, primary_key=True)
    room_id = Column(String, nullable=False, index=True)
    level = Column(Integer, nullable=False)
    small_blind = Column(Integer, nullable=False)
    big_blind = Column(Integer, nullable=False)
    ante = Column(Integer, nullable=False, default=0)
    duration_minutes = Column(Integer, nullable=False)

OutboxEvent = make_outbox_event_model(Base)
