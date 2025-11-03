from app import db
from datetime import datetime
from cryptography.fernet import Fernet
import base64
import os


class ScrapeConfig(db.Model):
    """Configuration for pstrax scraping"""
    id = db.Column(db.Integer, primary_key=True)
    pstrax_base_url = db.Column(db.String(255), default='https://pstrax.com', nullable=False)
    pstrax_username = db.Column(db.String(255), nullable=True)
    pstrax_password_encrypted = db.Column(db.Text, nullable=True)
    last_scrape = db.Column(db.DateTime, nullable=True)
    scrape_interval = db.Column(db.Integer, default=15)  # minutes
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

