from __future__ import annotations

from datetime import datetime

from app import db


class CylinderFillLog(db.Model):
    """Pending SCBA cylinder fill log (staging queue until PSTrax sync succeeds)."""

    __tablename__ = "cylinder_fill_log"

    STATUS_PENDING = "pending"
    STATUS_SYNCING = "syncing"
    STATUS_FAILED = "failed"
    STATUS_SYNCED = "synced"
    STATUS_LOCAL_ONLY = "local_only"

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
    badge_number = db.Column(db.String(4), nullable=True)

    pstrax_status = db.Column(
        db.String(16), nullable=False, default=STATUS_PENDING, index=True
    )
    last_sync_error = db.Column(db.Text, nullable=True)
    last_sync_attempt_at = db.Column(db.DateTime, nullable=True)
    sync_attempts = db.Column(db.Integer, nullable=False, default=0)

    filled_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False, index=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
