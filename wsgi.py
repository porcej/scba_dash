"""
WSGI entry point for Gunicorn
"""
from gevent import monkey
monkey.patch_all()

from app import create_app, db, socketio
from app.tasks import start_background_tasks

# Create the Flask application
app = create_app()

# Initialize database and start background tasks
with app.app_context():
    db.create_all()
    start_background_tasks(app)

# Export the Flask app for Gunicorn
# Flask-SocketIO handles Socket.IO routes automatically when initialized
# The socketio.init_app() call registers Socket.IO endpoints on the Flask app
application = app

