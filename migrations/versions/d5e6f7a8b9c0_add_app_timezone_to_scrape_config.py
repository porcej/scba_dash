"""add app_timezone to scrape config

Revision ID: d5e6f7a8b9c0
Revises: c4d5e6f7a8b9
Create Date: 2026-07-16 06:20:00.000000
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.engine.reflection import Inspector


revision = "d5e6f7a8b9c0"
down_revision = "c4d5e6f7a8b9"
branch_labels = None
depends_on = None


def upgrade():
    bind = op.get_bind()
    inspector = Inspector.from_engine(bind)
    existing_columns = {col["name"] for col in inspector.get_columns("scrape_config")}

    if "app_timezone" not in existing_columns:
        op.add_column(
            "scrape_config",
            sa.Column(
                "app_timezone",
                sa.String(length=64),
                nullable=False,
                server_default="America/New_York",
            ),
        )

    op.execute(
        "UPDATE scrape_config SET app_timezone = 'America/New_York' "
        "WHERE app_timezone IS NULL OR TRIM(app_timezone) = ''"
    )


def downgrade():
    bind = op.get_bind()
    inspector = Inspector.from_engine(bind)
    existing_columns = {col["name"] for col in inspector.get_columns("scrape_config")}

    if "app_timezone" in existing_columns:
        op.drop_column("scrape_config", "app_timezone")
