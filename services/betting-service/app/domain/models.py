from sqlalchemy import Column, Integer, String, DateTime
from sqlalchemy.sql import func

from .constants import TableName
from ..infrastructure.db import Base
from shared.core.outbox.model import make_outbox_event_model

class Bet(Base):
    __tablename__ = TableName.BETS

    id = Column(Integer, primary_key=True)
    bet_id = Column(String, unique=True, nullable=False, index=True)
    round_id = Column(String, nullable=False, index=True)
    player_id = Column(String, nullable=False, index=True)
    action = Column(String, nullable=False)
    amount = Column(Integer, nullable=False, default=0)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

OutboxEvent = make_outbox_event_model(Base)