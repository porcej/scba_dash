"""add allow_out_of_hydro_fills to scrape config

Revision ID: e6f7a8b9c0d1
Revises: d5e6f7a8b9c0
Create Date: 2026-07-16 08:55:00.000000
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.engine.reflection import Inspector


revision = "e6f7a8b9c0d1"
down_revision = "d5e6f7a8b9c0"
branch_labels = None
depends_on = None


def upgrade():
    bind = op.get_bind()
    inspector = Inspector.from_engine(bind)
    existing_columns = {col["name"] for col in inspector.get_columns("scrape_config")}

    if "allow_out_of_hydro_fills" not in existing_columns:
        op.add_column(
            "scrape_config",
            sa.Column(
                "allow_out_of_hydro_fills",
                sa.Boolean(),
                nullable=False,
                server_default=sa.false(),
            ),
        )


def downgrade():
    bind = op.get_bind()
    inspector = Inspector.from_engine(bind)
    existing_columns = {col["name"] for col in inspector.get_columns("scrape_config")}

    if "allow_out_of_hydro_fills" in existing_columns:
        op.drop_column("scrape_config", "allow_out_of_hydro_fills")
