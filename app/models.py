from app import db
from flask_login import UserMixin
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import datetime
import json
from cryptography.fernet import Fernet
import base64
import os


class User(UserMixin, db.Model):
    """User model for authentication"""
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False, index=True)
    password_hash = db.Column(db.String(255), nullable=False)
    is_admin = db.Column(db.Boolean, default=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    # Relationships
    tasks = db.relationship('Task', backref='user', lazy='dynamic', cascade='all, delete-orphan')
    alerts = db.relationship('Alert', backref='creator', lazy='dynamic', foreign_keys='Alert.created_by')
    
    def set_password(self, password):
        """Hash and set password"""
        self.password_hash = generate_password_hash(password)
    
    def check_password(self, password):
        """Verify password"""
        return check_password_hash(self.password_hash, password)
    
    def __repr__(self):
        return f'<User {self.username}>'


class Task(db.Model):
    """Task model for task list"""
    id = db.Column(db.Integer, primary_key=True)
    content = db.Column(db.Text, nullable=False)
    completed = db.Column(db.Boolean, default=False)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    def to_dict(self):
        """Convert task to dictionary for JSON serialization"""
        return {
            'id': self.id,
            'content': self.content,
            'completed': self.completed,
            'user_id': self.user_id,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'updated_at': self.updated_at.isoformat() if self.updated_at else None
        }
    
    def __repr__(self):
        return f'<Task {self.id}: {self.content[:50]}>'


class Alert(db.Model):
    """Alert model for scheduled messages"""
    id = db.Column(db.Integer, primary_key=True)
    message = db.Column(db.Text, nullable=False)
    start_time = db.Column(db.DateTime, nullable=True)
    end_time = db.Column(db.DateTime, nullable=False)
    is_active = db.Column(db.Boolean, default=False)
    created_by = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    def to_dict(self):
        """Convert alert to dictionary for JSON serialization"""
        return {
            'id': self.id,
            'message': self.message,
            'start_time': self.start_time.isoformat() if self.start_time else None,
            'end_time': self.end_time.isoformat() if self.end_time else None,
            'is_active': self.is_active,
            'created_by': self.created_by,
            'created_at': self.created_at.isoformat() if self.created_at else None
        }
    
    def __repr__(self):
        return f'<Alert {self.id}: {self.message[:50]}>'


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


class ScrapeData(db.Model):
    """Store scraped data from pstrax"""
    id = db.Column(db.Integer, primary_key=True)
    data = db.Column(db.Text, nullable=False)  # JSON string
    scraped_at = db.Column(db.DateTime, default=datetime.utcnow, index=True)
    
    def get_data(self):
        """Parse and return JSON data"""
        try:
            return json.loads(self.data)
        except json.JSONDecodeError:
            return {}
    
    def set_data(self, data_dict):
        """Store data as JSON string"""
        self.data = json.dumps(data_dict)
    
    def __repr__(self):
        return f'<ScrapeData {self.id}: {self.scraped_at}>'

