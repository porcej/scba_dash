from app import db
from datetime import datetime
import json


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

