# Production Deployment Guide

## Prerequisites

- Python 3.13 (or compatible version)
- Virtual environment (recommended)
- PostgreSQL (optional, but recommended for production instead of SQLite)

## Installation Steps

### 1. Install Dependencies

```bash
# Create and activate virtual environment
python3 -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate

# Install requirements
pip install -r requirements.txt
```

### 2. Set Environment Variables

Copy `.env.example` to `.env` and update the values:

```bash
cp .env.example .env
nano .env  # or use your preferred editor
```

**Important**: Change `SECRET_KEY` to a strong random string in production!

Generate a secret key:
```python
python -c "import secrets; print(secrets.token_hex(32))"
```

### 3. Initialize Database

```bash
# Create database tables
python -c "from app import create_app, db; app = create_app(); app.app_context().push(); db.create_all()"

# Or run migrations if using Flask-Migrate
flask db upgrade
```

### 4. Create Admin User (if needed)

```bash
python -c "from app import create_app, db; from app.models import User; app = create_app(); app.app_context().push(); user = User(username='admin', is_admin=True); user.set_password('your-password'); db.session.add(user); db.session.commit()"
```

## Running in Production

### Option 1: Using the Startup Script (Recommended for Testing)

```bash
./start_gunicorn.sh
```

### Option 2: Using Gunicorn Directly

```bash
gunicorn --worker-class gevent --workers 4 --bind 0.0.0.0:8000 --timeout 30 wsgi:application
```

### Option 3: Using Gunicorn Config File

```bash
gunicorn -c gunicorn_config.py wsgi:application
```

### Option 4: Systemd Service (Linux - Recommended for Production)

Create `/etc/systemd/system/scba-dash.service`:

```ini
[Unit]
Description=SCBA Dashboard Gunicorn Application Server
After=network.target

[Service]
User=www-data
Group=www-data
WorkingDirectory=/path/to/scba_dash
Environment="PATH=/path/to/scba_dash/venv/bin"
Environment="FLASK_ENV=production"
ExecStart=/path/to/scba_dash/venv/bin/gunicorn \
    --worker-class gevent \
    --workers 4 \
    --bind 0.0.0.0:8000 \
    --timeout 30 \
    --access-logfile /var/log/scba_dash/access.log \
    --error-logfile /var/log/scba_dash/error.log \
    --log-level info \
    wsgi:application

Restart=always
RestartSec=3

[Install]
WantedBy=multi-user.target
```

Then:

```bash
# Create log directory
sudo mkdir -p /var/log/scba_dash
sudo chown www-data:www-data /var/log/scba_dash

# Reload systemd
sudo systemctl daemon-reload

# Enable service
sudo systemctl enable scba-dash

# Start service
sudo systemctl start scba-dash

# Check status
sudo systemctl status scba-dash

# View logs
sudo journalctl -u scba-dash -f
```

### Option 5: Using Supervisor (Alternative to systemd)

Create `/etc/supervisor/conf.d/scba-dash.conf`:

```ini
[program:scba-dash]
command=/path/to/scba_dash/venv/bin/gunicorn --worker-class gevent --workers 4 --bind 0.0.0.0:8000 --timeout 30 wsgi:application
directory=/path/to/scba_dash
user=www-data
autostart=true
autorestart=true
redirect_stderr=true
stdout_logfile=/var/log/scba_dash/gunicorn.log
environment=FLASK_ENV=production
```

Then:

```bash
sudo supervisorctl reread
sudo supervisorctl update
sudo supervisorctl start scba-dash
```

## Reverse Proxy Setup (Nginx)

For production, use Nginx as a reverse proxy. Create `/etc/nginx/sites-available/scba-dash`:

```nginx
upstream scba_dash {
    server 127.0.0.1:8000;
}

server {
    listen 80;
    server_name your-domain.com;

    # Redirect HTTP to HTTPS (recommended)
    return 301 https://$server_name$request_uri;
}

server {
    listen 443 ssl http2;
    server_name your-domain.com;

    ssl_certificate /path/to/ssl/cert.pem;
    ssl_certificate_key /path/to/ssl/key.pem;

    # Security headers
    add_header X-Frame-Options "SAMEORIGIN" always;
    add_header X-Content-Type-Options "nosniff" always;
    add_header X-XSS-Protection "1; mode=block" always;

    # Logging
    access_log /var/log/nginx/scba_dash_access.log;
    error_log /var/log/nginx/scba_dash_error.log;

    # Static files (if serving directly from Nginx)
    location /static {
        alias /path/to/scba_dash/app/static;
        expires 30d;
        add_header Cache-Control "public, immutable";
    }

    # Socket.IO WebSocket support
    location /socket.io {
        proxy_pass http://scba_dash;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_read_timeout 86400;
    }

    # Main application
    location / {
        proxy_pass http://scba_dash;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
}
```

Enable the site:

```bash
sudo ln -s /etc/nginx/sites-available/scba-dash /etc/nginx/sites-enabled/
sudo nginx -t
sudo systemctl reload nginx
```

## Production Checklist

- [ ] Changed `SECRET_KEY` to a strong random value
- [ ] Set `FLASK_ENV=production`
- [ ] Configured database (PostgreSQL recommended for production)
- [ ] Set up SSL/TLS certificates
- [ ] Configured reverse proxy (Nginx)
- [ ] Set up log rotation
- [ ] Configured firewall rules
- [ ] Set up monitoring and alerts
- [ ] Created backup strategy for database
- [ ] Tested health endpoint: `curl http://localhost:8000/health`

## Monitoring

- **Health Check**: `GET /health` endpoint returns application status
- **Logs**: Check `/var/log/scba_dash/` or journalctl for errors
- **Process**: Monitor Gunicorn worker processes

## Troubleshooting

### Socket.IO Issues
- Ensure gevent worker class is used: `--worker-class gevent`
- Check that `SOCKETIO_ASYNC_MODE=gevent` is set
- Verify Nginx WebSocket configuration if using reverse proxy

### Database Issues
- Check database connection string in `.env`
- Ensure database user has proper permissions
- Run migrations: `flask db upgrade`

### Permission Issues
- Ensure app user has write access to database file (if using SQLite)
- Check log directory permissions
- Verify file ownership in app directory

## Environment Variables

Key environment variables:

- `SECRET_KEY`: Flask secret key (required)
- `DATABASE_URL`: Database connection string
- `SOCKETIO_ASYNC_MODE`: Socket.IO async mode (gevent for production)
- `SCRAPE_INTERVAL_MINUTES`: Scraping interval
- `FLASK_ENV`: Set to `production`

