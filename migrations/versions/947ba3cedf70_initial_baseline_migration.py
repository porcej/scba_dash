"""Initial baseline migration

Revision ID: 947ba3cedf70
Revises:
Create Date: 2025-11-03 14:56:15.933235

On a brand-new database (e.g. Docker), create core tables so later
migrations (ALTER TABLE, new columns) can apply. Existing deployments
that already have a ``user`` table are left unchanged.
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect


revision = "947ba3cedf70"
down_revision = None
branch_labels = None
depends_on = None


def upgrade():
    bind = op.get_bind()
    inspector = inspect(bind)
    if inspector.has_table("user"):
        return

    op.create_table(
        "user",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("username", sa.String(length=80), nullable=False),
        sa.Column("password_hash", sa.String(length=255), nullable=False),
        sa.Column("is_admin", sa.Boolean(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_user_username", "user", ["username"], unique=True)

    op.create_table(
        "task",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("completed", sa.Boolean(), nullable=True),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=True),
        sa.Column("updated_at", sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(["user_id"], ["user.id"]),
        sa.PrimaryKeyConstraint("id"),
    )

    op.create_table(
        "alert",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("message", sa.Text(), nullable=False),
        sa.Column("start_time", sa.DateTime(), nullable=True),
        sa.Column("end_time", sa.DateTime(), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=True),
        sa.Column("created_by", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(["created_by"], ["user.id"]),
        sa.PrimaryKeyConstraint("id"),
    )

    op.create_table(
        "scrape_config",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("pstrax_base_url", sa.String(length=255), nullable=False),
        sa.Column("pstrax_username", sa.String(length=255), nullable=True),
        sa.Column("pstrax_password_encrypted", sa.Text(), nullable=True),
        sa.Column("last_scrape", sa.DateTime(), nullable=True),
        sa.Column("scrape_interval", sa.Integer(), nullable=True),
        sa.Column("updated_at", sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )

    op.create_table(
        "scrape_data",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("data", sa.Text(), nullable=False),
        sa.Column("scraped_at", sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_scrape_data_scraped_at", "scrape_data", ["scraped_at"], unique=False)


def downgrade():
    pass
