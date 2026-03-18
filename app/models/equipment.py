"""Structured PSTrax equipment (cylinder) rows."""

from __future__ import annotations

import json
from datetime import datetime
from app import db
from app.pstrax_equipment_map import equipment_kwargs_from_pstrax


class Equipment(db.Model):
    """PSTrax cylinder gear (structured columns; key dates as mm/dd/yyyy)."""

    __tablename__ = "equipment"

    gearid = db.Column(db.Integer, primary_key=True)
    dt_row_id = db.Column(db.String(64), nullable=True, index=True)
    geartypeid = db.Column(db.Integer, nullable=True, index=True)
    geartype = db.Column(db.String(128), nullable=True)
    internalid = db.Column(db.String(64), nullable=True, index=True)
    serial = db.Column(db.String(128), nullable=True, index=True)
    mfr = db.Column(db.String(128), nullable=True)
    model = db.Column(db.String(255), nullable=True)
    size = db.Column(db.String(64), nullable=True)
    cost = db.Column(db.String(64), nullable=True)
    status = db.Column(db.String(64), nullable=True, index=True)
    currentuserid = db.Column(db.Integer, nullable=True)
    currentuser = db.Column(db.String(128), nullable=True)
    description = db.Column(db.String(512), nullable=True)
    custom1 = db.Column(db.String(512), nullable=True)
    custom2 = db.Column(db.String(512), nullable=True)
    custom3 = db.Column(db.String(512), nullable=True)
    condition = db.Column(db.String(64), nullable=True)
    mfrdate = db.Column(db.String(32), nullable=True)
    srvdate = db.Column(db.String(32), nullable=True)

    exp_date = db.Column(db.String(20), nullable=True)
    expdate_class = db.Column(db.String(128), nullable=True)
    expdate_display_raw = db.Column(db.Text, nullable=True)

    nexthydro_display = db.Column(db.Text, nullable=True)
    next_hydro = db.Column(db.String(20), nullable=True, index=True)
    nexthydro_class = db.Column(db.String(128), nullable=True)

    nextflow_display = db.Column(db.Text, nullable=True)
    next_flow = db.Column(db.String(20), nullable=True)
    nextflow_class = db.Column(db.String(128), nullable=True)

    lastloglocation_display = db.Column(db.Text, nullable=True)
    lastloglocation_logsort = db.Column(db.String(64), nullable=True)
    lastlogby_json = db.Column(db.Text, nullable=True)

    nextdue_display = db.Column(db.Text, nullable=True)
    next_due = db.Column(db.String(20), nullable=True, index=True)
    nextdue_class = db.Column(db.String(128), nullable=True)

    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    @classmethod
    def from_pstrax_row(cls, item: dict, updated_at: datetime) -> "Equipment":
        gid = item.get("gearid")
        if gid is None:
            raise ValueError("gearid required")
        kw = equipment_kwargs_from_pstrax(item)
        kw["updated_at"] = updated_at
        return cls(gearid=int(gid), **kw)

    def to_api_row(self) -> dict:
        """Shape expected by dashboard / PSTrax-style clients."""

        def exp_display():
            if self.expdate_display_raw:
                return self.expdate_display_raw
            return self.exp_date or ""

        def nh_display():
            if self.nexthydro_display:
                return self.nexthydro_display
            return self.next_hydro or ""

        def nf_display():
            if self.nextflow_display:
                return self.nextflow_display
            return self.next_flow or ""

        def nd_display():
            if self.nextdue_display:
                return self.nextdue_display
            return self.next_due or ""

        lastlogby = None
        if self.lastlogby_json:
            try:
                lastlogby = json.loads(self.lastlogby_json)
            except (json.JSONDecodeError, TypeError):
                lastlogby = self.lastlogby_json

        logsort = self.lastloglocation_logsort
        if logsort is not None and str(logsort).isdigit():
            try:
                logsort = int(logsort)
            except (TypeError, ValueError):
                pass

        return {
            "DT_RowId": self.dt_row_id or f"id_{self.gearid}",
            "gearid": self.gearid,
            "geartypeid": self.geartypeid,
            "geartype": self.geartype or "",
            "internalid": self.internalid or "",
            "serial": self.serial or "",
            "mfr": self.mfr or "",
            "model": self.model or "",
            "size": self.size or "",
            "cost": self.cost or "",
            "status": self.status or "",
            "currentuserid": self.currentuserid if self.currentuserid is not None else 0,
            "currentuser": self.currentuser or "",
            "description": self.description or "",
            "custom1": self.custom1 or "",
            "custom2": self.custom2 or "",
            "custom3": self.custom3 or "",
            "condition": self.condition or "",
            "mfrdate": self.mfrdate or "",
            "srvdate": self.srvdate or "",
            "expdate": {
                "display": exp_display(),
                "expsort": self.exp_date or "",
                "expclass": self.expdate_class or "",
            },
            "nexthydro": {
                "display": nh_display(),
                "hydrosort": self.next_hydro or "",
                "hydroclass": self.nexthydro_class or "",
            },
            "nextflow": {
                "display": nf_display(),
                "flowsort": self.next_flow or "",
                "flowclass": self.nextflow_class or "",
            },
            "lastloglocation": {
                "display": self.lastloglocation_display or "",
                "logsort": logsort,
            },
            "lastlogby": lastlogby,
            "nextdue": {
                "display": nd_display(),
                "nxtsort": self.next_due or "",
                "nxtclass": self.nextdue_class or "",
            },
        }
