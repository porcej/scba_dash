"""
Gunicorn configuration file
"""
import multiprocessing
import os

# Server socket
bind = os.environ.get('GUNICORN_BIND', '0.0.0.0:8000')
backlog = 2048

# Worker processes
workers = int(os.environ.get('GUNICORN_WORKERS', multiprocessing.cpu_count() * 2 + 1))
worker_class = 'gevent'
worker_connections = 1000
timeout = 30
keepalive = 2

# Logging
accesslog = os.environ.get('GUNICORN_ACCESS_LOG', '-')  # '-' means stdout
errorlog = os.environ.get('GUNICORN_ERROR_LOG', '-')   # '-' means stdout
loglevel = os.environ.get('GUNICORN_LOG_LEVEL', 'info')
access_log_format = '%(h)s %(l)s %(u)s %(t)s "%(r)s" %(s)s %(b)s "%(f)s" "%(a)s" %(D)s'

# Process naming
proc_name = 'scba_dash'

# Server mechanics
daemon = False
pidfile = os.environ.get('GUNICORN_PIDFILE', None)
umask = 0
user = os.environ.get('GUNICORN_USER', None)
group = os.environ.get('GUNICORN_GROUP', None)
tmp_upload_dir = None

# SSL (if needed)
# keyfile = None
# certfile = None

# Worker class settings for gevent
# Note: gevent monkey patching is done in wsgi.py

