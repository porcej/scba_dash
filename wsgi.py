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
    from sqlalchemy import inspect

    insp = inspect(db.engine)
    if insp.has_table("alembic_version") and not insp.has_table("user"):
        from flask_migrate import stamp

        db.create_all()
        stamp(revision="heads")
    else:
        try:
            from flask_migrate import upgrade

            upgrade()
        except Exception:
            db.create_all()
            try:
                from flask_migrate import stamp

                stamp(revision="heads")
            except Exception:
                pass
    start_background_tasks(app)

# Export the Flask app for Gunicorn
# Flask-SocketIO handles Socket.IO routes automatically when initialized
# The socketio.init_app() call registers Socket.IO endpoints on the Flask app
application = app

