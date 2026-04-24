"""Add idempotency_key to bets table.

Revision ID: 002
Revises: 001
"""
from alembic import op
import sqlalchemy as sa

revision = "002"
down_revision = "001"
branch_labels = None
depends_on = None

def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    column_names = {col["name"] for col in inspector.get_columns("bets")}
    index_names = {idx["name"] for idx in inspector.get_indexes("bets")}

    if "idempotency_key" not in column_names:
        op.add_column("bets", sa.Column("idempotency_key", sa.String(), nullable=True))

    if "ix_bets_idempotency_key" not in index_names:
        op.create_index("ix_bets_idempotency_key", "bets", ["idempotency_key"], unique=True)

def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    column_names = {col["name"] for col in inspector.get_columns("bets")}
    index_names = {idx["name"] for idx in inspector.get_indexes("bets")}

    if "ix_bets_idempotency_key" in index_names:
        op.drop_index("ix_bets_idempotency_key", table_name="bets")
    if "idempotency_key" in column_names:
        op.drop_column("bets", "idempotency_key")
