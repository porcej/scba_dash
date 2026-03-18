"""equipment table and equipment scrape interval

Revision ID: c3a1e2b4d5f6
Revises: b6f951e4c9ad
Create Date: 2026-03-18 12:00:00.000000
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.engine.reflection import Inspector


revision = 'c3a1e2b4d5f6'
down_revision = 'b6f951e4c9ad'
branch_labels = None
depends_on = None


def upgrade():
    bind = op.get_bind()
    inspector = Inspector.from_engine(bind)
    cfg_cols = {c['name'] for c in inspector.get_columns('scrape_config')}

    if not inspector.has_table('equipment'):
        op.create_table(
            'equipment',
            sa.Column('gearid', sa.Integer(), nullable=False),
            sa.Column('payload_json', sa.Text(), nullable=False),
            sa.Column('updated_at', sa.DateTime(), nullable=True),
            sa.PrimaryKeyConstraint('gearid'),
        )

    if 'equipment_scrape_interval_hours' not in cfg_cols:
        op.add_column(
            'scrape_config',
            sa.Column(
                'equipment_scrape_interval_hours',
                sa.Integer(),
                nullable=False,
                server_default='24',
            ),
        )

    if 'last_equipment_scrape' not in cfg_cols:
        op.add_column(
            'scrape_config', sa.Column('last_equipment_scrape', sa.DateTime(), nullable=True)
        )


def downgrade():
    bind = op.get_bind()
    inspector = Inspector.from_engine(bind)
    if inspector.has_table('equipment'):
        op.drop_table('equipment')
    cfg_cols = {c['name'] for c in inspector.get_columns('scrape_config')}
    if 'last_equipment_scrape' in cfg_cols:
        op.drop_column('scrape_config', 'last_equipment_scrape')
    if 'equipment_scrape_interval_hours' in cfg_cols:
        op.drop_column('scrape_config', 'equipment_scrape_interval_hours')
