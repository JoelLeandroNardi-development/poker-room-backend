from sqlalchemy import Column, Integer, String, DateTime
from sqlalchemy.sql import func

from .constants import GameStatus, RoundStatus, TableName
from ..infrastructure.db import Base
from shared.core.outbox.model import make_outbox_event_model


class Game(Base):
    __tablename__ = TableName.GAMES

    id = Column(Integer, primary_key=True)
    game_id = Column(String, unique=True, nullable=False, index=True)
    room_id = Column(String, nullable=False, index=True)
    status = Column(String, nullable=False, default=GameStatus.WAITING)
    current_blind_level = Column(Integer, nullable=False, default=1)
    level_started_at = Column(DateTime(timezone=True), nullable=True)
    current_dealer_seat = Column(Integer, nullable=False, default=1)
    current_small_blind_seat = Column(Integer, nullable=False, default=2)
    current_big_blind_seat = Column(Integer, nullable=False, default=3)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)


class Round(Base):
    __tablename__ = TableName.ROUNDS

    id = Column(Integer, primary_key=True)
    round_id = Column(String, unique=True, nullable=False, index=True)
    game_id = Column(String, nullable=False, index=True)
    round_number = Column(Integer, nullable=False)
    dealer_seat = Column(Integer, nullable=False)
    small_blind_seat = Column(Integer, nullable=False)
    big_blind_seat = Column(Integer, nullable=False)
    small_blind_amount = Column(Integer, nullable=False)
    big_blind_amount = Column(Integer, nullable=False)
    ante_amount = Column(Integer, nullable=False, default=0)
    status = Column(String, nullable=False, default=RoundStatus.ACTIVE)
    winner_player_id = Column(String, nullable=True)
    pot_amount = Column(Integer, nullable=False, default=0)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    completed_at = Column(DateTime(timezone=True), nullable=True)


OutboxEvent = make_outbox_event_model(Base)
