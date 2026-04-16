from __future__ import annotations

from sqlalchemy import Column, Integer, String, DateTime, JSON
from sqlalchemy.sql import func

def make_outbox_event_model(Base):
    class OutboxEvent(Base):
        __tablename__ = "outbox_events"

        id = Column(Integer, primary_key=True)
        event_id = Column(String, unique=True, nullable=False, index=True)
        event_type = Column(String, nullable=False, index=True)
        routing_key = Column(String, nullable=False, index=True)
        payload = Column(JSON, nullable=False)
        status = Column(String, nullable=False, default="PENDING")
        attempts = Column(Integer, nullable=False, default=0)
        last_error = Column(String, nullable=True)
        created_at = Column(
            DateTime(timezone=True),
            server_default=func.now(), nullable=False
        )
        published_at = Column(DateTime(timezone=True), nullable=True)

    return OutboxEvent
