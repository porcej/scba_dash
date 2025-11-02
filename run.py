import os
from gevent import monkey
monkey.patch_all()

from app import create_app, db, socketio

app = create_app()

# Initialize database and start background tasks
with app.app_context():
    db.create_all()
    from app.tasks import start_background_tasks
    start_background_tasks(app)

if __name__ == '__main__':
    # Use debug mode only if FLASK_ENV is not 'production'
    debug = os.environ.get('FLASK_ENV') != 'production'
    
    # When using gevent, disable reloader to avoid fork issues
    # The reloader uses fork() which doesn't work well with gevent monkey patching
    use_reloader = debug and os.environ.get('SOCKETIO_ASYNC_MODE') != 'gevent'
    
    # Allow unsafe Werkzeug in Docker/production when explicitly using run.py
    # For true production, use Gunicorn instead (see wsgi.py and start_gunicorn.sh)
    allow_unsafe = os.environ.get('FLASK_ENV') == 'production'
    
    socketio.run(
        app, 
        debug=debug, 
        host='0.0.0.0', 
        port=8000,
        use_reloader=use_reloader,
        allow_unsafe_werkzeug=allow_unsafe
    )

