from __future__ import annotations

from datetime import datetime

from app import db


class CylinderFillLog(db.Model):
    """Public SCBA cylinder fill log (one row per cylinder fill)."""

    __tablename__ = "cylinder_fill_log"

    id = db.Column(db.Integer, primary_key=True)
    batch_id = db.Column(db.String(36), nullable=False, index=True)

    gearid = db.Column(db.Integer, db.ForeignKey("equipment.gearid"), nullable=True, index=True)
    internalid = db.Column(db.String(64), nullable=True, index=True)

    fill_site_id = db.Column(
        db.Integer, db.ForeignKey("fill_site.id"), nullable=True, index=True
    )
    fill_board_id = db.Column(
        db.Integer, db.ForeignKey("fill_board.id"), nullable=True, index=True
    )
    fill_site_name = db.Column(db.String(128), nullable=True)

    filled_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False, index=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)

