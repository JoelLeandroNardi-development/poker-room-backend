from sqlalchemy import Column, Integer, String, DateTime
from sqlalchemy.sql import func

from .constants import TableName
from ..infrastructure.db import Base
from shared.core.outbox.model import make_outbox_event_model


class User(Base):
    __tablename__ = TableName.USERS

    id = Column(Integer, primary_key=True)
    email = Column(String, unique=True, index=True, nullable=False)

    display_name = Column(String, nullable=True)
    first_name = Column(String, nullable=True)
    last_name = Column(String, nullable=True)

    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)


OutboxEvent = make_outbox_event_model(Base)
