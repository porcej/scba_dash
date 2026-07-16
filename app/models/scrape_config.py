from app import db
from datetime import datetime
from cryptography.fernet import Fernet
import base64
import os
import re


class ScrapeConfig(db.Model):
    """Configuration for pstrax scraping"""
    id = db.Column(db.Integer, primary_key=True)
    pstrax_base_url = db.Column(db.String(255), default='https://pstrax.com', nullable=False)
    pstrax_username = db.Column(db.String(255), nullable=True)
    pstrax_password_encrypted = db.Column(db.Text, nullable=True)
    last_scrape = db.Column(db.DateTime, nullable=True)
    scrape_interval = db.Column(db.Integer, default=15)  # minutes (alerts scraper)
    equipment_scrape_interval_hours = db.Column(db.Integer, default=24, nullable=False)
    last_equipment_scrape = db.Column(db.DateTime, nullable=True)
    default_alert_color = db.Column(db.String(20), default='danger', nullable=False)
    alerts_font_size = db.Column(db.Integer, default=16, nullable=False)  # pixels
    gear_list_type_ids = db.Column(db.String(255), default='11', nullable=False)
    gear_list_statuses = db.Column(db.String(255), default='Active', nullable=False)
    app_timezone = db.Column(db.String(64), default='America/New_York', nullable=False)
    allow_out_of_hydro_fills = db.Column(db.Boolean, default=False, nullable=False)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    @staticmethod
    def _get_encryption_key():
        """Get or generate encryption key"""
        from app.config import Config
        key = os.environ.get('ENCRYPTION_KEY')
        if not key:
            # Generate a key from SECRET_KEY if no encryption key is set
            key = Config.SECRET_KEY.encode()
            # Use first 32 bytes for Fernet key
            key = base64.urlsafe_b64encode(key[:32].ljust(32, b'0'))
        else:
            key = key.encode()
            if len(key) != 44:  # Fernet key should be 44 bytes when base64 encoded
                key = base64.urlsafe_b64encode(key[:32].ljust(32, b'0'))
        return key
    
    def set_password(self, password):
        """Encrypt and store password"""
        if not password:
            self.pstrax_password_encrypted = None
            return
        f = Fernet(self._get_encryption_key())
        self.pstrax_password_encrypted = f.encrypt(password.encode()).decode()
    
    def get_password(self):
        """Decrypt and return password"""
        if not self.pstrax_password_encrypted:
            return None
        try:
            f = Fernet(self._get_encryption_key())
            return f.decrypt(self.pstrax_password_encrypted.encode()).decode()
        except Exception:
            return None
    
    def __repr__(self):
        return f'<ScrapeConfig {self.id}>'

    def get_default_alert_color(self):
        return (self.default_alert_color or 'danger').lower()

    def get_alert_font_size(self):
        try:
            return int(self.alerts_font_size or 16)
        except (TypeError, ValueError):
            return 16

    def get_app_timezone(self):
        from app.timezone_utils import normalize_timezone_name

        return normalize_timezone_name(self.app_timezone or 'America/New_York')

    def get_allow_out_of_hydro_fills(self):
        return bool(self.allow_out_of_hydro_fills)

    def get_gear_list_type_ids(self):
        """Return configured gear type IDs as a normalized int list."""
        raw = (self.gear_list_type_ids or "").strip()
        if not raw:
            return [11]

        parts = re.split(r"[\s,]+", raw)
        values = []
        for part in parts:
            if not part:
                continue
            try:
                values.append(int(part))
            except (TypeError, ValueError):
                continue

        return values or [11]

    def set_gear_list_type_ids(self, value):
        """Normalize and persist gear type IDs as a comma-separated string."""
        if value is None:
            self.gear_list_type_ids = "11"
            return

        if isinstance(value, (list, tuple, set)):
            parts = [str(v).strip() for v in value if str(v).strip()]
        else:
            parts = re.split(r"[\s,]+", str(value).strip())

        normalized = []
        seen = set()
        for part in parts:
            try:
                parsed = int(part)
            except (TypeError, ValueError):
                continue
            if parsed in seen:
                continue
            seen.add(parsed)
            normalized.append(str(parsed))

        self.gear_list_type_ids = ",".join(normalized) if normalized else "11"

    def get_gear_list_statuses(self):
        """Return configured gear statuses as a normalized list."""
        raw = (self.gear_list_statuses or "").strip()
        if not raw:
            return ["Active"]

        parts = re.split(r"[\n,]+", raw)
        normalized = []
        seen = set()
        for part in parts:
            label = str(part).strip()
            if not label:
                continue
            key = label.lower()
            if key in seen:
                continue
            seen.add(key)
            normalized.append(label)
        return normalized or ["Active"]

    def set_gear_list_statuses(self, value):
        """Normalize and persist gear statuses as a comma-separated string."""
        if value is None:
            self.gear_list_statuses = "Active"
            return

        if isinstance(value, (list, tuple, set)):
            parts = [str(v).strip() for v in value if str(v).strip()]
        else:
            parts = re.split(r"[\n,]+", str(value).strip())

        normalized = []
        seen = set()
        for part in parts:
            label = str(part).strip()
            if not label:
                continue
            key = label.lower()
            if key in seen:
                continue
            seen.add(key)
            normalized.append(label)

        self.gear_list_statuses = ",".join(normalized) if normalized else "Active"

