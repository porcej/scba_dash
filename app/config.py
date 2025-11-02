import os
from datetime import timedelta


class Config:
    """Base configuration class"""
    SECRET_KEY = os.environ.get('SECRET_KEY') or 'dev-secret-key-change-in-production'
    SQLALCHEMY_DATABASE_URI = os.environ.get('DATABASE_URL') or 'sqlite:///scba_dash.db'
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    
    # SocketIO configuration
    SOCKETIO_ASYNC_MODE = 'threading'
    
    # Scraping configuration
    SCRAPE_INTERVAL_MINUTES = int(os.environ.get('SCRAPE_INTERVAL_MINUTES', '15'))
    
    # Session configuration
    PERMANENT_SESSION_LIFETIME = timedelta(hours=24)

