"""create all game-service tables

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
        "games",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("game_id", sa.String(), unique=True, nullable=False, index=True),
        sa.Column("room_id", sa.String(), nullable=False, index=True),
        sa.Column("status", sa.String(), nullable=False, server_default="WAITING"),
        sa.Column("current_blind_level", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("level_started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("current_dealer_seat", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("current_small_blind_seat", sa.Integer(), nullable=False, server_default="2"),
        sa.Column("current_big_blind_seat", sa.Integer(), nullable=False, server_default="3"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint("current_blind_level >= 1", name="ck_games_blind_level_positive"),
        sa.CheckConstraint(
            "status IN ('WAITING', 'ACTIVE', 'PAUSED', 'FINISHED')",
            name="ck_games_status_enum",
        ),
    )

    op.create_table(
        "rounds",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("round_id", sa.String(), unique=True, nullable=False, index=True),
        sa.Column("game_id", sa.String(), sa.ForeignKey("games.game_id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("round_number", sa.Integer(), nullable=False),
        sa.Column("dealer_seat", sa.Integer(), nullable=False),
        sa.Column("small_blind_seat", sa.Integer(), nullable=False),
        sa.Column("big_blind_seat", sa.Integer(), nullable=False),
        sa.Column("small_blind_amount", sa.Integer(), nullable=False),
        sa.Column("big_blind_amount", sa.Integer(), nullable=False),
        sa.Column("ante_amount", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("status", sa.String(), nullable=False, server_default="ACTIVE"),
        sa.Column("pot_amount", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("street", sa.String(), nullable=False, server_default="PRE_FLOP"),
        sa.Column("acting_player_id", sa.String(), nullable=True),
        sa.Column("current_highest_bet", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("minimum_raise_amount", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("is_action_closed", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("last_aggressor_seat", sa.Integer(), nullable=True),
        sa.Column("engine_version", sa.String(), nullable=False, server_default="0.15.0"),
        sa.Column("state_version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.UniqueConstraint("game_id", "round_number", name="uq_rounds_game_round_number"),
        sa.CheckConstraint("pot_amount >= 0", name="ck_rounds_pot_non_negative"),
        sa.CheckConstraint("current_highest_bet >= 0", name="ck_rounds_highest_bet_non_negative"),
        sa.CheckConstraint("minimum_raise_amount >= 0", name="ck_rounds_min_raise_non_negative"),
        sa.CheckConstraint(
            "status IN ('ACTIVE', 'COMPLETED')",
            name="ck_rounds_status_enum",
        ),
        sa.CheckConstraint(
            "street IN ('PRE_FLOP', 'FLOP', 'TURN', 'RIVER', 'SHOWDOWN')",
            name="ck_rounds_street_enum",
        ),
        sa.CheckConstraint("state_version >= 1", name="ck_rounds_state_version_positive"),
    )

    op.create_table(
        "round_players",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("round_id", sa.String(), sa.ForeignKey("rounds.round_id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("player_id", sa.String(), nullable=False),
        sa.Column("seat_number", sa.Integer(), nullable=False),
        sa.Column("stack_remaining", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("committed_this_street", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("committed_this_hand", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("has_folded", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("is_all_in", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("is_active_in_hand", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.UniqueConstraint("round_id", "player_id", name="uq_round_players_round_player"),
        sa.UniqueConstraint("round_id", "seat_number", name="uq_round_players_round_seat"),
        sa.CheckConstraint("stack_remaining >= 0", name="ck_round_players_stack_non_negative"),
        sa.CheckConstraint("committed_this_street >= 0", name="ck_round_players_street_commit_non_negative"),
        sa.CheckConstraint("committed_this_hand >= 0", name="ck_round_players_hand_commit_non_negative"),
    )

    op.create_table(
        "round_payouts",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("round_id", sa.String(), sa.ForeignKey("rounds.round_id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("pot_index", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("pot_type", sa.String(), nullable=False, server_default="main"),
        sa.Column("player_id", sa.String(), nullable=False),
        sa.Column("amount", sa.Integer(), nullable=False),
        sa.CheckConstraint("amount >= 0", name="ck_round_payouts_amount_non_negative"),
    )

    op.create_table(
        "bets",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("bet_id", sa.String(), unique=True, nullable=False, index=True),
        sa.Column("round_id", sa.String(), sa.ForeignKey("rounds.round_id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("player_id", sa.String(), nullable=False, index=True),
        sa.Column("action", sa.String(), nullable=False),
        sa.Column("amount", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("idempotency_key", sa.String(), nullable=True, unique=True, index=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint("amount >= 0", name="ck_bets_amount_non_negative"),
        sa.CheckConstraint(
            "action IN ('FOLD', 'CHECK', 'CALL', 'BET', 'RAISE', 'ALL_IN')",
            name="ck_bets_action_enum",
        ),
    )
    op.create_index("ix_bets_round_created", "bets", ["round_id", "created_at"])

    op.create_table(
        "hand_ledger_entries",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("entry_id", sa.String(), unique=True, nullable=False, index=True),
        sa.Column("round_id", sa.String(), sa.ForeignKey("rounds.round_id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("entry_type", sa.String(), nullable=False, index=True),
        sa.Column("player_id", sa.String(), nullable=True),
        sa.Column("amount", sa.Integer(), nullable=True),
        sa.Column("detail", sa.JSON(), nullable=True),
        sa.Column("original_entry_id", sa.String(), nullable=True, index=True),
        sa.Column("dealer_id", sa.String(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint(
            "entry_type IN ('BLIND_POSTED', 'ANTE_POSTED', 'BET_PLACED', 'STREET_DEALT', "
            "'PAYOUT_AWARDED', 'ROUND_COMPLETED', 'ACTION_REVERSED', 'STACK_ADJUSTED', "
            "'HAND_REOPENED', 'PAYOUT_CORRECTED')",
            name="ck_ledger_entry_type_enum",
        ),
    )
    op.create_index("ix_ledger_round_created", "hand_ledger_entries", ["round_id", "created_at"])
    op.create_index("ix_ledger_round_original", "hand_ledger_entries", ["round_id", "original_entry_id"])

    op.create_table(
        "room_snapshots",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("game_id", sa.String(), sa.ForeignKey("games.game_id", ondelete="CASCADE"), unique=True, nullable=False, index=True),
        sa.Column("room_id", sa.String(), nullable=False),
        sa.Column("starting_dealer_seat", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )

    op.create_table(
        "room_snapshot_players",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("game_id", sa.String(), sa.ForeignKey("games.game_id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("player_id", sa.String(), nullable=False),
        sa.Column("seat_number", sa.Integer(), nullable=False),
        sa.Column("chip_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("is_eliminated", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.UniqueConstraint("game_id", "player_id", name="uq_room_snap_players_game_player"),
        sa.UniqueConstraint("game_id", "seat_number", name="uq_room_snap_players_game_seat"),
        sa.CheckConstraint("chip_count >= 0", name="ck_room_snap_players_chips_non_negative"),
    )

    op.create_table(
        "room_snapshot_blind_levels",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("game_id", sa.String(), sa.ForeignKey("games.game_id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("level", sa.Integer(), nullable=False),
        sa.Column("small_blind", sa.Integer(), nullable=False),
        sa.Column("big_blind", sa.Integer(), nullable=False),
        sa.Column("ante", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("duration_minutes", sa.Integer(), nullable=True),
        sa.UniqueConstraint("game_id", "level", name="uq_room_snap_blind_levels_game_level"),
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
    op.drop_table("room_snapshot_blind_levels")
    op.drop_table("room_snapshot_players")
    op.drop_table("room_snapshots")
    op.drop_table("hand_ledger_entries")
    op.drop_table("bets")
    op.drop_table("round_payouts")
    op.drop_table("round_players")
    op.drop_table("rounds")
    op.drop_table("games")
