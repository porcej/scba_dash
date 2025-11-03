"""
Models package - contains all database models

This package maintains backward compatibility with the old models.py file.
All models are imported here and exported for use throughout the application.
"""

# Import all models to ensure they're registered with SQLAlchemy
from app.models.user import User
from app.models.task import Task
from app.models.alert import Alert
from app.models.scrape_config import ScrapeConfig
from app.models.scrape_data import ScrapeData

# Export all models for backward compatibility
__all__ = ['User', 'Task', 'Alert', 'ScrapeConfig', 'ScrapeData']

