from app import db
from datetime import datetime


class Task(db.Model):
    """Task model for task list"""
    id = db.Column(db.Integer, primary_key=True)
    content = db.Column(db.Text, nullable=False)
    completed = db.Column(db.Boolean, default=False)
    priority = db.Column(db.Integer, default=2, nullable=False)  # 1=High, 2=Medium, 3=Low
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    def to_dict(self):
        """Convert task to dictionary for JSON serialization"""
        return {
            'id': self.id,
            'content': self.content,
            'completed': self.completed,
            'priority': self.priority,
            'user_id': self.user_id,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'updated_at': self.updated_at.isoformat() if self.updated_at else None
        }
    
    def get_priority_label(self):
        """Get human-readable priority label"""
        priority_map = {1: 'High', 2: 'Medium', 3: 'Low'}
        return priority_map.get(self.priority, 'Medium')
    
    def __repr__(self):
        return f'<Task {self.id}: {self.content[:50]}>'

