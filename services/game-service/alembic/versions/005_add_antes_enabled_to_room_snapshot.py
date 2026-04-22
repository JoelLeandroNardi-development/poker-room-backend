"""Add antes_enabled to room snapshots.

Revision ID: 005
Revises: 004
Create Date: 2026-04-22
"""

from alembic import op
import sqlalchemy as sa

revision = "005"
down_revision = "004"
branch_labels = None
depends_on = None

def upgrade() -> None:
    op.add_column(
        "room_snapshots",
        sa.Column("antes_enabled", sa.Boolean(), nullable=False, server_default=sa.text("false")),
    )

def downgrade() -> None:
    op.drop_column("room_snapshots", "antes_enabled")