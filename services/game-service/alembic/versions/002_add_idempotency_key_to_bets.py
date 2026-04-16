"""Add idempotency_key to bets table.

Revision ID: 002
Revises: 001
"""
from alembic import op
import sqlalchemy as sa

revision = "002"
down_revision = "001_hand_state"
branch_labels = None
depends_on = None

def upgrade() -> None:
    op.add_column("bets", sa.Column("idempotency_key", sa.String(), nullable=True))
    op.create_index("ix_bets_idempotency_key", "bets", ["idempotency_key"], unique=True)

def downgrade() -> None:
    op.drop_index("ix_bets_idempotency_key", table_name="bets")
    op.drop_column("bets", "idempotency_key")