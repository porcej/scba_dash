"""structured equipment columns (replace payload_json)

Revision ID: e1f2a3b4c5d6
Revises: c3a1e2b4d5f6
Create Date: 2026-03-18 14:00:00.000000
"""

import json

import sqlalchemy as sa
from alembic import op
from sqlalchemy.engine.reflection import Inspector

revision = "e1f2a3b4c5d6"
down_revision = "c3a1e2b4d5f6"
branch_labels = None
depends_on = None


def _equipment_columns():
    return [
        sa.Column("gearid", sa.Integer(), nullable=False),
        sa.Column("dt_row_id", sa.String(length=64), nullable=True),
        sa.Column("geartypeid", sa.Integer(), nullable=True),
        sa.Column("geartype", sa.String(length=128), nullable=True),
        sa.Column("internalid", sa.String(length=64), nullable=True),
        sa.Column("serial", sa.String(length=128), nullable=True),
        sa.Column("mfr", sa.String(length=128), nullable=True),
        sa.Column("model", sa.String(length=255), nullable=True),
        sa.Column("size", sa.String(length=64), nullable=True),
        sa.Column("cost", sa.String(length=64), nullable=True),
        sa.Column("status", sa.String(length=64), nullable=True),
        sa.Column("currentuserid", sa.Integer(), nullable=True),
        sa.Column("currentuser", sa.String(length=128), nullable=True),
        sa.Column("description", sa.String(length=512), nullable=True),
        sa.Column("custom1", sa.String(length=512), nullable=True),
        sa.Column("custom2", sa.String(length=512), nullable=True),
        sa.Column("custom3", sa.String(length=512), nullable=True),
        sa.Column("condition", sa.String(length=64), nullable=True),
        sa.Column("mfrdate", sa.String(length=32), nullable=True),
        sa.Column("srvdate", sa.String(length=32), nullable=True),
        sa.Column("exp_date", sa.String(length=20), nullable=True),
        sa.Column("expdate_class", sa.String(length=128), nullable=True),
        sa.Column("expdate_display_raw", sa.Text(), nullable=True),
        sa.Column("nexthydro_display", sa.Text(), nullable=True),
        sa.Column("next_hydro", sa.String(length=20), nullable=True),
        sa.Column("nexthydro_class", sa.String(length=128), nullable=True),
        sa.Column("nextflow_display", sa.Text(), nullable=True),
        sa.Column("next_flow", sa.String(length=20), nullable=True),
        sa.Column("nextflow_class", sa.String(length=128), nullable=True),
        sa.Column("lastloglocation_display", sa.Text(), nullable=True),
        sa.Column("lastloglocation_logsort", sa.String(length=64), nullable=True),
        sa.Column("lastlogby_json", sa.Text(), nullable=True),
        sa.Column("nextdue_display", sa.Text(), nullable=True),
        sa.Column("next_due", sa.String(length=20), nullable=True),
        sa.Column("nextdue_class", sa.String(length=128), nullable=True),
        sa.Column("updated_at", sa.DateTime(), nullable=True),
    ]


def _create_structured_table():
    op.create_table(
        "equipment",
        *_equipment_columns(),
        sa.PrimaryKeyConstraint("gearid"),
    )
    for ix, cols in (
        ("ix_equipment_dt_row_id", ["dt_row_id"]),
        ("ix_equipment_geartypeid", ["geartypeid"]),
        ("ix_equipment_internalid", ["internalid"]),
        ("ix_equipment_serial", ["serial"]),
        ("ix_equipment_status", ["status"]),
        ("ix_equipment_next_hydro", ["next_hydro"]),
        ("ix_equipment_next_due", ["next_due"]),
    ):
        try:
            op.create_index(ix, "equipment", cols, unique=False)
        except Exception:
            pass


def upgrade():
    conn = op.get_bind()
    insp = Inspector.from_engine(conn)
    if not insp.has_table("equipment"):
        _create_structured_table()
        return

    cols = {c["name"] for c in insp.get_columns("equipment")}
    if "next_hydro" in cols and "payload_json" not in cols:
        return

    from app.pstrax_equipment_map import equipment_kwargs_from_pstrax

    legacy = []
    if "payload_json" in cols:
        for row in conn.execute(sa.text("SELECT gearid, payload_json, updated_at FROM equipment")):
            legacy.append((row[0], row[1], row[2]))

    op.drop_table("equipment")
    _create_structured_table()

    for gearid, payload_json, updated_at in legacy:
        try:
            item = json.loads(payload_json)
            kw = equipment_kwargs_from_pstrax(item)
            kw["gearid"] = int(item.get("gearid") or gearid)
            kw["updated_at"] = updated_at
            keys = list(kw.keys())
            placeholders = ", ".join(f":{k}" for k in keys)
            conn.execute(
                sa.text(
                    f"INSERT INTO equipment ({', '.join(keys)}) VALUES ({placeholders})"
                ),
                kw,
            )
        except Exception:
            continue


def _row_to_pstrax_payload(d):
    """Best-effort JSON for downgrade (round-trip)."""
    z = lambda x: (x or "") if x is not None else ""
    lb = d.get("lastlogby_json")
    if lb:
        try:
            lastlogby = json.loads(lb)
        except json.JSONDecodeError:
            lastlogby = lb
    else:
        lastlogby = None
    ls = d.get("lastloglocation_logsort")
    if ls is not None and str(ls).isdigit():
        try:
            ls = int(ls)
        except ValueError:
            pass
    item = {
        "DT_RowId": z(d.get("dt_row_id")),
        "gearid": d["gearid"],
        "geartypeid": d.get("geartypeid"),
        "geartype": z(d.get("geartype")),
        "internalid": z(d.get("internalid")),
        "serial": z(d.get("serial")),
        "mfr": z(d.get("mfr")),
        "model": z(d.get("model")),
        "size": z(d.get("size")),
        "cost": z(d.get("cost")),
        "status": z(d.get("status")),
        "currentuserid": d.get("currentuserid") if d.get("currentuserid") is not None else 0,
        "currentuser": z(d.get("currentuser")),
        "description": z(d.get("description")),
        "custom1": z(d.get("custom1")),
        "custom2": z(d.get("custom2")),
        "custom3": z(d.get("custom3")),
        "condition": z(d.get("condition")),
        "mfrdate": z(d.get("mfrdate")),
        "srvdate": z(d.get("srvdate")),
        "expdate": {
            "display": z(d.get("expdate_display_raw")) or z(d.get("exp_date")),
            "expsort": z(d.get("exp_date")),
            "expclass": z(d.get("expdate_class")),
        },
        "nexthydro": {
            "display": z(d.get("nexthydro_display")) or z(d.get("next_hydro")),
            "hydrosort": z(d.get("next_hydro")),
            "hydroclass": z(d.get("nexthydro_class")),
        },
        "nextflow": {
            "display": z(d.get("nextflow_display")) or z(d.get("next_flow")),
            "flowsort": z(d.get("next_flow")),
            "flowclass": z(d.get("nextflow_class")),
        },
        "lastloglocation": {
            "display": z(d.get("lastloglocation_display")),
            "logsort": ls,
        },
        "lastlogby": lastlogby,
        "nextdue": {
            "display": z(d.get("nextdue_display")) or z(d.get("next_due")),
            "nxtsort": z(d.get("next_due")),
            "nxtclass": z(d.get("nextdue_class")),
        },
    }
    return json.dumps(item)


def downgrade():
    conn = op.get_bind()
    insp = Inspector.from_engine(conn)
    if not insp.has_table("equipment"):
        op.create_table(
            "equipment",
            sa.Column("gearid", sa.Integer(), nullable=False),
            sa.Column("payload_json", sa.Text(), nullable=False),
            sa.Column("updated_at", sa.DateTime(), nullable=True),
            sa.PrimaryKeyConstraint("gearid"),
        )
        return

    rows = [dict(r._mapping) for r in conn.execute(sa.text("SELECT * FROM equipment"))]

    op.drop_table("equipment")
    op.create_table(
        "equipment",
        sa.Column("gearid", sa.Integer(), nullable=False),
        sa.Column("payload_json", sa.Text(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint("gearid"),
    )

    for d in rows:
        conn.execute(
            sa.text(
                "INSERT INTO equipment (gearid, payload_json, updated_at) VALUES (:g, :p, :u)"
            ),
            {
                "g": d["gearid"],
                "p": _row_to_pstrax_payload(d),
                "u": d.get("updated_at"),
            },
        )
