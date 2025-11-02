import os
from datetime import timedelta


class Config:
    """Base configuration class"""
    SECRET_KEY = os.environ.get('SECRET_KEY') or 'dev-secret-key-change-in-production'
    SQLALCHEMY_DATABASE_URI = os.environ.get('DATABASE_URL') or 'sqlite:///scba_dash.db'
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    
    # SocketIO configuration
    # Use 'gevent' for production with Gunicorn + gevent (Python 3.13 compatible)
    # Use 'threading' for development
    SOCKETIO_ASYNC_MODE = os.environ.get('SOCKETIO_ASYNC_MODE', 'gevent')
    
    # Session configuration
    SESSION_COOKIE_SECURE = os.environ.get('SESSION_COOKIE_SECURE', 'False').lower() == 'true'
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = 'Lax'
    PERMANENT_SESSION_LIFETIME = timedelta(hours=24)
    
    # Scraping configuration
    SCRAPE_INTERVAL_MINUTES = int(os.environ.get('SCRAPE_INTERVAL_MINUTES', '15'))

