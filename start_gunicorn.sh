#!/bin/bash
# Start script for Gunicorn with gevent

# Activate virtual environment if it exists
if [ -d "venv" ]; then
    source venv/bin/activate
fi

# Set environment variables (optional)
export SOCKETIO_ASYNC_MODE=gevent
export FLASK_ENV=production

# Run Gunicorn
gunicorn \
    --worker-class gevent \
    --workers 1 \
    --bind 0.0.0.0:8000 \
    --timeout 30 \
    --access-logfile - \
    --error-logfile - \
    --log-level info \
    wsgi:application

