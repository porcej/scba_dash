#!/bin/bash
# Start script for Gunicorn with gevent

# Prefer project venv at ~/.venv/scba_dash, then local ./venv
if [ -f "${HOME}/.venv/scba_dash/bin/activate" ]; then
    # shellcheck source=/dev/null
    source "${HOME}/.venv/scba_dash/bin/activate"
elif [ -d "venv" ]; then
    # shellcheck source=/dev/null
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

