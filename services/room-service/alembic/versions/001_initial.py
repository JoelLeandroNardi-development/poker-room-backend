"""create all room-service tables

Revision ID: 001
Revises:
Create Date: 2026-04-15
"""
from alembic import op
import sqlalchemy as sa

revision = "001"
down_revision = None
branch_labels = None
depends_on = None

def upgrade() -> None:
    op.create_table(
        "rooms",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("room_id", sa.String(), unique=True, nullable=False, index=True),
        sa.Column("code", sa.String(4), unique=True, nullable=False, index=True),
        sa.Column("name", sa.String(), nullable=True),
        sa.Column("status", sa.String(), nullable=False, server_default="WAITING"),
        sa.Column("max_players", sa.Integer(), nullable=False),
        sa.Column("starting_chips", sa.Integer(), nullable=False),
        sa.Column("antes_enabled", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("starting_dealer_seat", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("created_by", sa.String(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )

    op.create_table(
        "room_players",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("room_id", sa.String(), nullable=False, index=True),
        sa.Column("player_id", sa.String(), unique=True, nullable=False, index=True),
        sa.Column("player_name", sa.String(), nullable=False),
        sa.Column("seat_number", sa.Integer(), nullable=False),
        sa.Column("chip_count", sa.Integer(), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("is_eliminated", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("joined_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )

    op.create_table(
        "blind_levels",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("room_id", sa.String(), nullable=False, index=True),
        sa.Column("level", sa.Integer(), nullable=False),
        sa.Column("small_blind", sa.Integer(), nullable=False),
        sa.Column("big_blind", sa.Integer(), nullable=False),
        sa.Column("ante", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("duration_minutes", sa.Integer(), nullable=False),
    )

    op.create_table(
        "outbox_events",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("event_id", sa.String(), unique=True, nullable=False, index=True),
        sa.Column("event_type", sa.String(), nullable=False, index=True),
        sa.Column("routing_key", sa.String(), nullable=False, index=True),
        sa.Column("payload", sa.JSON(), nullable=False),
        sa.Column("status", sa.String(), nullable=False, server_default="PENDING"),
        sa.Column("attempts", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("last_error", sa.String(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("published_at", sa.DateTime(timezone=True), nullable=True),
    )

def downgrade() -> None:
    op.drop_table("outbox_events")
    op.drop_table("blind_levels")
    op.drop_table("room_players")
    op.drop_table("rooms")