"""add hand state fields, round_players, round_payouts, drop winner_player_id

Revision ID: 001_hand_state
Revises:
Create Date: 2026-04-15

"""
from alembic import op
import sqlalchemy as sa

revision = "001_hand_state"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    # New columns on the existing rounds table
    op.add_column("rounds", sa.Column("street", sa.String(), nullable=False, server_default="PRE_FLOP"))
    op.add_column("rounds", sa.Column("acting_player_id", sa.String(), nullable=True))
    op.add_column("rounds", sa.Column("current_highest_bet", sa.Integer(), nullable=False, server_default="0"))
    op.add_column("rounds", sa.Column("minimum_raise_amount", sa.Integer(), nullable=False, server_default="0"))
    op.add_column("rounds", sa.Column("is_action_closed", sa.Boolean(), nullable=False, server_default=sa.text("false")))

    # Drop legacy single-winner column
    op.drop_column("rounds", "winner_player_id")

    # New round_players table
    op.create_table(
        "round_players",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("round_id", sa.String(), nullable=False, index=True),
        sa.Column("player_id", sa.String(), nullable=False),
        sa.Column("seat_number", sa.Integer(), nullable=False),
        sa.Column("stack_remaining", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("committed_this_street", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("committed_this_hand", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("has_folded", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("is_all_in", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("is_active_in_hand", sa.Boolean(), nullable=False, server_default=sa.text("true")),
    )

    # New round_payouts table
    op.create_table(
        "round_payouts",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("round_id", sa.String(), nullable=False, index=True),
        sa.Column("pot_index", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("pot_type", sa.String(), nullable=False, server_default="main"),
        sa.Column("player_id", sa.String(), nullable=False),
        sa.Column("amount", sa.Integer(), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("round_payouts")
    op.drop_table("round_players")
    op.add_column("rounds", sa.Column("winner_player_id", sa.String(), nullable=True))
    op.drop_column("rounds", "is_action_closed")
    op.drop_column("rounds", "minimum_raise_amount")
    op.drop_column("rounds", "current_highest_bet")
    op.drop_column("rounds", "acting_player_id")
    op.drop_column("rounds", "street")
