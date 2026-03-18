import os
from gevent import monkey
monkey.patch_all()

from app import create_app, db, socketio

app = create_app()

# Initialize database and start background tasks
with app.app_context():
    from sqlalchemy import inspect

    insp = inspect(db.engine)
    if insp.has_table("alembic_version") and not insp.has_table("user"):
        print(
            "Repairing database: Alembic version recorded but schema missing; "
            "creating tables from models and stamping head."
        )
        from flask_migrate import stamp

        db.create_all()
        stamp(revision="heads")
    else:
        try:
            from flask_migrate import upgrade

            print("Running database migrations...")
            upgrade()
            print("Database migrations completed.")
        except Exception as e:
            print(f"Warning: Migration failed ({e}), falling back to db.create_all()")
            db.create_all()
            try:
                from flask_migrate import stamp

                stamp(revision="heads")
                print("Database stamped at head after create_all fallback.")
            except Exception as se:
                print(f"Warning: Could not stamp database: {se}")

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

