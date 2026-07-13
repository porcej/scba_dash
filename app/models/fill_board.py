from __future__ import annotations

import secrets
from datetime import datetime

from app import db


class FillBoard(db.Model):
    """Public fill board identified by a long random key."""

    __tablename__ = "fill_board"

    KEY_LENGTH = 256

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(128), nullable=False)
    fill_site_id = db.Column(
        db.Integer, db.ForeignKey("fill_site.id"), nullable=False, index=True
    )
    key = db.Column(db.String(KEY_LENGTH), nullable=False, unique=True, index=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    updated_at = db.Column(
        db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False
    )

    @staticmethod
    def generate_key() -> str:
        """Return a random key of exactly KEY_LENGTH characters."""
        # token_hex(n) returns 2*n characters; 128 bytes -> 256 hex chars.
        return secrets.token_hex(FillBoard.KEY_LENGTH // 2)

    def regenerate_key(self) -> str:
        self.key = self.generate_key()
        self.updated_at = datetime.utcnow()
        return self.key

    def __repr__(self):
        return f"<FillBoard {self.name}>"
