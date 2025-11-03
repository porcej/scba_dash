"""Initial baseline migration

Revision ID: 947ba3cedf70
Revises: 
Create Date: 2025-11-03 14:56:15.933235

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '947ba3cedf70'
down_revision = None
branch_labels = None
depends_on = None


def upgrade():
    """
    Baseline migration - tables already exist in the database.
    This migration is a no-op but establishes the baseline for future migrations.
    """
    # Tables already exist, so this is intentionally empty
    pass


def downgrade():
    """
    Baseline migration - no downgrade needed for baseline.
    """
    # Baseline migrations typically don't have downgrades
    pass
