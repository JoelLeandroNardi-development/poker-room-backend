"""Add session runtime fields to games table.

Revision ID: 004
Revises: 003
Create Date: 2026-04-16

Persists hands_played and hands_at_current_level so that table-runtime
counters survive across requests and blind-clock progression is durable.
"""

revision = "004"
down_revision = "003"

from alembic import op
import sqlalchemy as sa

def upgrade() -> None:
    op.add_column(
        "games",
        sa.Column("hands_played", sa.Integer(), nullable=False, server_default="0"),
    )
    op.add_column(
        "games",
        sa.Column("hands_at_current_level", sa.Integer(), nullable=False, server_default="0"),
    )
    op.create_check_constraint(
        "ck_games_hands_played_non_negative", "games", "hands_played >= 0"
    )
    op.create_check_constraint(
        "ck_games_hands_at_level_non_negative", "games", "hands_at_current_level >= 0"
    )

def downgrade() -> None:
    op.drop_constraint("ck_games_hands_at_level_non_negative", "games", type_="check")
    op.drop_constraint("ck_games_hands_played_non_negative", "games", type_="check")
    op.drop_column("games", "hands_at_current_level")
    op.drop_column("games", "hands_played")