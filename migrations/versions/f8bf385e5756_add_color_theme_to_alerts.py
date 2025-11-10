"""Add color_theme field to alerts

Revision ID: f8bf385e5756
Revises: 0b088bb68db2
Create Date: 2025-11-10 12:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'f8bf385e5756'
down_revision = '0b088bb68db2'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('alert', schema=None) as batch_op:
        batch_op.add_column(sa.Column('color_theme', sa.String(length=20), nullable=True, server_default='danger'))

    op.execute("UPDATE alert SET color_theme = 'danger' WHERE color_theme IS NULL OR color_theme = ''")

    with op.batch_alter_table('alert', schema=None) as batch_op:
        batch_op.alter_column('color_theme', existing_type=sa.String(length=20), nullable=False, server_default='danger')


def downgrade():
    with op.batch_alter_table('alert', schema=None) as batch_op:
        batch_op.drop_column('color_theme')

