"""add gear list type ids to scrape config

Revision ID: a9b7c6d5e4f3
Revises: f0a1b2c3d4e5
Create Date: 2026-05-05 06:58:00.000000
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.engine.reflection import Inspector


revision = "a9b7c6d5e4f3"
down_revision = "f0a1b2c3d4e5"
branch_labels = None
depends_on = None


def upgrade():
    bind = op.get_bind()
    inspector = Inspector.from_engine(bind)
    existing_columns = {col["name"] for col in inspector.get_columns("scrape_config")}

    if "gear_list_type_ids" not in existing_columns:
        op.add_column(
            "scrape_config",
            sa.Column(
                "gear_list_type_ids",
                sa.String(length=255),
                nullable=False,
                server_default="11",
            ),
        )

    op.execute(
        "UPDATE scrape_config SET gear_list_type_ids = '11' "
        "WHERE gear_list_type_ids IS NULL OR TRIM(gear_list_type_ids) = ''"
    )


def downgrade():
    bind = op.get_bind()
    inspector = Inspector.from_engine(bind)
    existing_columns = {col["name"] for col in inspector.get_columns("scrape_config")}

    if "gear_list_type_ids" in existing_columns:
        op.drop_column("scrape_config", "gear_list_type_ids")
