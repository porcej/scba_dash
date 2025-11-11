"""add alert settings to scrape config

Revision ID: b6f951e4c9ad
Revises: f8bf385e5756
Create Date: 2025-11-11 08:00:00.000000
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.engine.reflection import Inspector


# revision identifiers, used by Alembic.
revision = 'b6f951e4c9ad'
down_revision = 'f8bf385e5756'
branch_labels = None
depends_on = None


def upgrade():
    bind = op.get_bind()
    inspector = Inspector.from_engine(bind)
    existing_columns = {col['name'] for col in inspector.get_columns('scrape_config')}

    if 'default_alert_color' not in existing_columns:
        op.add_column('scrape_config', sa.Column('default_alert_color', sa.String(length=20), nullable=False, server_default='danger'))
    if 'alerts_font_size' not in existing_columns:
        op.add_column('scrape_config', sa.Column('alerts_font_size', sa.Integer(), nullable=False, server_default='16'))

    # Normalize existing data
    op.execute("UPDATE alert SET color_theme = 'danger' WHERE color_theme IS NULL OR color_theme = ''")
    op.execute("UPDATE scrape_config SET default_alert_color = LOWER(default_alert_color)")

    # Remove server defaults now that existing rows have values
    if 'default_alert_color' not in existing_columns:
        op.alter_column('scrape_config', 'default_alert_color', server_default=None)
    if 'alerts_font_size' not in existing_columns:
        op.alter_column('scrape_config', 'alerts_font_size', server_default=None)


def downgrade():
    bind = op.get_bind()
    inspector = Inspector.from_engine(bind)
    existing_columns = {col['name'] for col in inspector.get_columns('scrape_config')}

    if 'alerts_font_size' in existing_columns:
        op.drop_column('scrape_config', 'alerts_font_size')
    if 'default_alert_color' in existing_columns:
        op.drop_column('scrape_config', 'default_alert_color')

