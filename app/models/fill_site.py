from __future__ import annotations

from datetime import datetime

from app import db


class FillSite(db.Model):
    """Named fill site used by public fill boards."""

    __tablename__ = "fill_site"

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(128), nullable=False, unique=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    updated_at = db.Column(
        db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False
    )

    boards = db.relationship(
        "FillBoard",
        backref="fill_site",
        lazy="dynamic",
        cascade="all, delete-orphan",
    )

    def __repr__(self):
        return f"<FillSite {self.name}>"
