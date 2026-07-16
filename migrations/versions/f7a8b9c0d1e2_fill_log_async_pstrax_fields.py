"""add async pstrax sync fields to cylinder fill log

Revision ID: f7a8b9c0d1e2
Revises: e6f7a8b9c0d1
Create Date: 2026-07-16 09:05:00.000000
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.engine.reflection import Inspector


revision = "f7a8b9c0d1e2"
down_revision = "e6f7a8b9c0d1"
branch_labels = None
depends_on = None


def upgrade():
    bind = op.get_bind()
    inspector = Inspector.from_engine(bind)
    if not inspector.has_table("cylinder_fill_log"):
        return

    cols = {c["name"] for c in inspector.get_columns("cylinder_fill_log")}

    if "badge_number" not in cols:
        op.add_column(
            "cylinder_fill_log",
            sa.Column("badge_number", sa.String(length=4), nullable=True),
        )
    if "pstrax_status" not in cols:
        op.add_column(
            "cylinder_fill_log",
            sa.Column(
                "pstrax_status",
                sa.String(length=16),
                nullable=False,
                server_default="pending",
            ),
        )
        op.create_index(
            "ix_cylinder_fill_log_pstrax_status",
            "cylinder_fill_log",
            ["pstrax_status"],
            unique=False,
        )
    if "last_sync_error" not in cols:
        op.add_column(
            "cylinder_fill_log",
            sa.Column("last_sync_error", sa.Text(), nullable=True),
        )
    if "last_sync_attempt_at" not in cols:
        op.add_column(
            "cylinder_fill_log",
            sa.Column("last_sync_attempt_at", sa.DateTime(), nullable=True),
        )
    if "sync_attempts" not in cols:
        op.add_column(
            "cylinder_fill_log",
            sa.Column(
                "sync_attempts",
                sa.Integer(),
                nullable=False,
                server_default="0",
            ),
        )

    # Existing rows without a fill site are local-only; others remain pending for sync.
    op.execute(
        "UPDATE cylinder_fill_log "
        "SET pstrax_status = 'local_only' "
        "WHERE fill_site_name IS NULL OR TRIM(fill_site_name) = ''"
    )


def downgrade():
    bind = op.get_bind()
    inspector = Inspector.from_engine(bind)
    if not inspector.has_table("cylinder_fill_log"):
        return

    cols = {c["name"] for c in inspector.get_columns("cylinder_fill_log")}
    indexes = {idx["name"] for idx in inspector.get_indexes("cylinder_fill_log")}

    if "ix_cylinder_fill_log_pstrax_status" in indexes:
        op.drop_index(
            "ix_cylinder_fill_log_pstrax_status", table_name="cylinder_fill_log"
        )
    if "sync_attempts" in cols:
        op.drop_column("cylinder_fill_log", "sync_attempts")
    if "last_sync_attempt_at" in cols:
        op.drop_column("cylinder_fill_log", "last_sync_attempt_at")
    if "last_sync_error" in cols:
        op.drop_column("cylinder_fill_log", "last_sync_error")
    if "pstrax_status" in cols:
        op.drop_column("cylinder_fill_log", "pstrax_status")
    if "badge_number" in cols:
        op.drop_column("cylinder_fill_log", "badge_number")
