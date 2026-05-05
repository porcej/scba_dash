"""add gear list statuses to scrape config

Revision ID: b1c2d3e4f5a6
Revises: a9b7c6d5e4f3
Create Date: 2026-05-05 09:05:00.000000
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.engine.reflection import Inspector


revision = "b1c2d3e4f5a6"
down_revision = "a9b7c6d5e4f3"
branch_labels = None
depends_on = None


def upgrade():
    bind = op.get_bind()
    inspector = Inspector.from_engine(bind)
    existing_columns = {col["name"] for col in inspector.get_columns("scrape_config")}

    if "gear_list_statuses" not in existing_columns:
        op.add_column(
            "scrape_config",
            sa.Column(
                "gear_list_statuses",
                sa.String(length=255),
                nullable=False,
                server_default="Active",
            ),
        )

    op.execute(
        "UPDATE scrape_config SET gear_list_statuses = 'Active' "
        "WHERE gear_list_statuses IS NULL OR TRIM(gear_list_statuses) = ''"
    )


def downgrade():
    bind = op.get_bind()
    inspector = Inspector.from_engine(bind)
    existing_columns = {col["name"] for col in inspector.get_columns("scrape_config")}

    if "gear_list_statuses" in existing_columns:
        op.drop_column("scrape_config", "gear_list_statuses")
