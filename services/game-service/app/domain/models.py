from sqlalchemy import Boolean, Column, Integer, String, DateTime, JSON
from sqlalchemy.sql import func

from .constants import GameStatus, RoundStatus, Street, TableName
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
    pot_amount = Column(Integer, nullable=False, default=0)

    # --- Hand-state fields ---
    street = Column(String, nullable=False, default=Street.PRE_FLOP)
    acting_player_id = Column(String, nullable=True)
    current_highest_bet = Column(Integer, nullable=False, default=0)
    minimum_raise_amount = Column(Integer, nullable=False, default=0)
    is_action_closed = Column(Boolean, nullable=False, default=False)

    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    completed_at = Column(DateTime(timezone=True), nullable=True)


class RoundPlayer(Base):
    __tablename__ = TableName.ROUND_PLAYERS

    id = Column(Integer, primary_key=True)
    round_id = Column(String, nullable=False, index=True)
    player_id = Column(String, nullable=False)
    seat_number = Column(Integer, nullable=False)
    stack_remaining = Column(Integer, nullable=False, default=0)
    committed_this_street = Column(Integer, nullable=False, default=0)
    committed_this_hand = Column(Integer, nullable=False, default=0)
    has_folded = Column(Boolean, nullable=False, default=False)
    is_all_in = Column(Boolean, nullable=False, default=False)
    is_active_in_hand = Column(Boolean, nullable=False, default=True)


class RoundPayout(Base):
    __tablename__ = TableName.ROUND_PAYOUTS

    id = Column(Integer, primary_key=True)
    round_id = Column(String, nullable=False, index=True)
    pot_index = Column(Integer, nullable=False, default=0)
    pot_type = Column(String, nullable=False, default="main")
    player_id = Column(String, nullable=False)
    amount = Column(Integer, nullable=False)

class Bet(Base):
    __tablename__ = TableName.BETS

    id = Column(Integer, primary_key=True)
    bet_id = Column(String, unique=True, nullable=False, index=True)
    round_id = Column(String, nullable=False, index=True)
    player_id = Column(String, nullable=False, index=True)
    action = Column(String, nullable=False)
    amount = Column(Integer, nullable=False, default=0)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

class HandLedgerEntry(Base):
    """Immutable, append-only audit log for every state-changing event
    within a hand — including dealer corrections.

    Rows are never updated or deleted.  Corrections are recorded as
    *new* entries that reference the ``original_entry_id`` they amend.
    """
    __tablename__ = TableName.HAND_LEDGER_ENTRIES

    id = Column(Integer, primary_key=True)
    entry_id = Column(String, unique=True, nullable=False, index=True)
    round_id = Column(String, nullable=False, index=True)
    entry_type = Column(String, nullable=False, index=True)
    player_id = Column(String, nullable=True)
    amount = Column(Integer, nullable=True)
    # Free-form detail — e.g. {"reason": "wrong player", "old_amount": 100}
    detail = Column(JSON, nullable=True)
    # Links a correction entry back to the original it amends
    original_entry_id = Column(String, nullable=True, index=True)
    # Dealer / operator who authored this entry
    dealer_id = Column(String, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

OutboxEvent = make_outbox_event_model(Base)