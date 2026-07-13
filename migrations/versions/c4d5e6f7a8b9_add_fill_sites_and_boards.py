"""add fill sites and fill boards

Revision ID: c4d5e6f7a8b9
Revises: b1c2d3e4f5a6
Create Date: 2026-07-13 06:50:00.000000
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.engine.reflection import Inspector


revision = "c4d5e6f7a8b9"
down_revision = "b1c2d3e4f5a6"
branch_labels = None
depends_on = None


def upgrade():
    bind = op.get_bind()
    inspector = Inspector.from_engine(bind)
    tables = set(inspector.get_table_names())

    if "fill_site" not in tables:
        op.create_table(
            "fill_site",
            sa.Column("id", sa.Integer(), nullable=False),
            sa.Column("name", sa.String(length=128), nullable=False),
            sa.Column("created_at", sa.DateTime(), nullable=False),
            sa.Column("updated_at", sa.DateTime(), nullable=False),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint("name"),
        )

    if "fill_board" not in tables:
        op.create_table(
            "fill_board",
            sa.Column("id", sa.Integer(), nullable=False),
            sa.Column("name", sa.String(length=128), nullable=False),
            sa.Column("fill_site_id", sa.Integer(), nullable=False),
            sa.Column("key", sa.String(length=256), nullable=False),
            sa.Column("created_at", sa.DateTime(), nullable=False),
            sa.Column("updated_at", sa.DateTime(), nullable=False),
            sa.ForeignKeyConstraint(["fill_site_id"], ["fill_site.id"]),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint("key"),
        )
        op.create_index("ix_fill_board_fill_site_id", "fill_board", ["fill_site_id"])
        op.create_index("ix_fill_board_key", "fill_board", ["key"])

    if "cylinder_fill_log" in tables:
        cols = {c["name"] for c in inspector.get_columns("cylinder_fill_log")}
        if "fill_site_id" not in cols:
            op.add_column(
                "cylinder_fill_log",
                sa.Column("fill_site_id", sa.Integer(), nullable=True),
            )
            op.create_index(
                "ix_cylinder_fill_log_fill_site_id",
                "cylinder_fill_log",
                ["fill_site_id"],
            )
            op.create_foreign_key(
                "fk_cylinder_fill_log_fill_site_id",
                "cylinder_fill_log",
                "fill_site",
                ["fill_site_id"],
                ["id"],
            )
        if "fill_board_id" not in cols:
            op.add_column(
                "cylinder_fill_log",
                sa.Column("fill_board_id", sa.Integer(), nullable=True),
            )
            op.create_index(
                "ix_cylinder_fill_log_fill_board_id",
                "cylinder_fill_log",
                ["fill_board_id"],
            )
            op.create_foreign_key(
                "fk_cylinder_fill_log_fill_board_id",
                "cylinder_fill_log",
                "fill_board",
                ["fill_board_id"],
                ["id"],
            )
        if "fill_site_name" not in cols:
            op.add_column(
                "cylinder_fill_log",
                sa.Column("fill_site_name", sa.String(length=128), nullable=True),
            )


def downgrade():
    bind = op.get_bind()
    inspector = Inspector.from_engine(bind)
    tables = set(inspector.get_table_names())

    if "cylinder_fill_log" in tables:
        cols = {c["name"] for c in inspector.get_columns("cylinder_fill_log")}
        if "fill_site_name" in cols:
            op.drop_column("cylinder_fill_log", "fill_site_name")
        if "fill_board_id" in cols:
            try:
                op.drop_constraint(
                    "fk_cylinder_fill_log_fill_board_id",
                    "cylinder_fill_log",
                    type_="foreignkey",
                )
            except Exception:
                pass
            try:
                op.drop_index(
                    "ix_cylinder_fill_log_fill_board_id", table_name="cylinder_fill_log"
                )
            except Exception:
                pass
            op.drop_column("cylinder_fill_log", "fill_board_id")
        if "fill_site_id" in cols:
            try:
                op.drop_constraint(
                    "fk_cylinder_fill_log_fill_site_id",
                    "cylinder_fill_log",
                    type_="foreignkey",
                )
            except Exception:
                pass
            try:
                op.drop_index(
                    "ix_cylinder_fill_log_fill_site_id", table_name="cylinder_fill_log"
                )
            except Exception:
                pass
            op.drop_column("cylinder_fill_log", "fill_site_id")

    if "fill_board" in tables:
        try:
            op.drop_index("ix_fill_board_key", table_name="fill_board")
        except Exception:
            pass
        try:
            op.drop_index("ix_fill_board_fill_site_id", table_name="fill_board")
        except Exception:
            pass
        op.drop_table("fill_board")

    if "fill_site" in tables:
        op.drop_table("fill_site")
