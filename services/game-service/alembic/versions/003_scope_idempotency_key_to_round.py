"""Scope idempotency_key unique constraint to (round_id, idempotency_key).

Revision ID: 003
Revises: 002
"""
from alembic import op

revision = "003"
down_revision = "002"
branch_labels = None
depends_on = None

def upgrade() -> None:
    op.drop_index("ix_bets_idempotency_key", table_name="bets")
    op.create_unique_constraint(
        "uq_bets_round_idempotency", "bets", ["round_id", "idempotency_key"],
    )
    op.create_index(
        "ix_bets_idempotency_key", "bets", ["idempotency_key"],
    )

def downgrade() -> None:
    op.drop_index("ix_bets_idempotency_key", table_name="bets")
    op.drop_constraint("uq_bets_round_idempotency", "bets", type_="unique")
    op.create_index(
        "ix_bets_idempotency_key", "bets", ["idempotency_key"], unique=True,
    )