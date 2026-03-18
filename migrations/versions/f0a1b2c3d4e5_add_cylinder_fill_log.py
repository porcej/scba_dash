"""add cylinder fill log

Revision ID: f0a1b2c3d4e5
Revises: e1f2a3b4c5d6
Create Date: 2026-03-18 15:00:00.000000
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.engine.reflection import Inspector


revision = "f0a1b2c3d4e5"
down_revision = "e1f2a3b4c5d6"
branch_labels = None
depends_on = None


def upgrade():
    bind = op.get_bind()
    inspector = Inspector.from_engine(bind)
    if inspector.has_table("cylinder_fill_log"):
        return

    op.create_table(
        "cylinder_fill_log",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("batch_id", sa.String(length=36), nullable=False),
        sa.Column("gearid", sa.Integer(), nullable=True),
        sa.Column("internalid", sa.String(length=64), nullable=True),
        sa.Column("filled_at", sa.DateTime(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["gearid"], ["equipment.gearid"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_cylinder_fill_log_batch_id", "cylinder_fill_log", ["batch_id"], unique=False)
    op.create_index("ix_cylinder_fill_log_gearid", "cylinder_fill_log", ["gearid"], unique=False)
    op.create_index("ix_cylinder_fill_log_internalid", "cylinder_fill_log", ["internalid"], unique=False)
    op.create_index("ix_cylinder_fill_log_filled_at", "cylinder_fill_log", ["filled_at"], unique=False)


def downgrade():
    bind = op.get_bind()
    inspector = Inspector.from_engine(bind)
    if inspector.has_table("cylinder_fill_log"):
        try:
            op.drop_index("ix_cylinder_fill_log_filled_at", table_name="cylinder_fill_log")
            op.drop_index("ix_cylinder_fill_log_internalid", table_name="cylinder_fill_log")
            op.drop_index("ix_cylinder_fill_log_gearid", table_name="cylinder_fill_log")
            op.drop_index("ix_cylinder_fill_log_batch_id", table_name="cylinder_fill_log")
        except Exception:
            pass
        op.drop_table("cylinder_fill_log")

