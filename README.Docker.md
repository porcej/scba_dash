# Docker Deployment Guide

This guide explains how to run the SCBA Dashboard using Docker Compose.

## Quick Start

1. **Set environment variables** (create a `.env` file):

```bash
SECRET_KEY=your-strong-secret-key-here
DATABASE_URL=sqlite:///data/scba_dash.db
SOCKETIO_ASYNC_MODE=threading
SCRAPE_INTERVAL_MINUTES=15
```

Generate a secret key:
```bash
python -c "import secrets; print(secrets.token_hex(32))"
```

2. **Build and start the container**:

```bash
docker-compose up -d
```

3. **View logs**:

```bash
docker-compose logs -f
```

4. **Stop the container**:

```bash
docker-compose down
```

## Accessing the Application

Once started, the application will be available at:
- **Web Interface**: http://localhost:8000
- **Health Check**: http://localhost:8000/health

## Data Persistence

The database and application data are stored in the `./data` directory, which is mounted as a volume. This ensures data persists even when the container is restarted.

## Creating an Admin User

To create an admin user after the container is running:

```bash
docker-compose exec scba-dash python -c "
from app import create_app, db
from app.models import User
app = create_app()
with app.app_context():
    user = User(username='admin', is_admin=True)
    user.set_password('your-password')
    db.session.add(user)
    db.session.commit()
    print('Admin user created!')
"
```

## Environment Variables

Key environment variables you can set:

- `SECRET_KEY`: Flask secret key (required, should be strong)
- `DATABASE_URL`: Database connection string (default: SQLite in `/app/data`)
- `SOCKETIO_ASYNC_MODE`: Socket.IO async mode (`threading` for Docker, `gevent` for production)
- `SCRAPE_INTERVAL_MINUTES`: Interval between automatic scrapes
- `FLASK_ENV`: Set to `production` for production mode

## Docker Compose Commands

```bash
# Build the image
docker-compose build

# Start in detached mode
docker-compose up -d

# View logs
docker-compose logs -f scba-dash

# Stop containers
docker-compose stop

# Remove containers
docker-compose down

# Remove containers and volumes (WARNING: deletes data)
docker-compose down -v

# Rebuild and restart
docker-compose up -d --build
```

## Troubleshooting

### Container won't start
- Check logs: `docker-compose logs scba-dash`
- Verify environment variables are set correctly
- Ensure port 8000 is not already in use

### Database errors
- Check that the `./data` directory exists and has proper permissions
- For SQLite, ensure the directory is writable

### Socket.IO not working
- Ensure `SOCKETIO_ASYNC_MODE=threading` is set (default in docker-compose.yml)
- Check that the container is accessible from your browser
- Review application logs for Socket.IO connection errors

## Production Considerations

For production deployment:

1. **Use a production WSGI server**: Consider using Gunicorn instead of `run.py`:
   - Update Dockerfile CMD to: `CMD ["gunicorn", "--worker-class", "gevent", "--workers", "4", "--bind", "0.0.0.0:8000", "wsgi:application"]`
   - Update environment: `SOCKETIO_ASYNC_MODE=gevent`

2. **Use PostgreSQL**: Replace SQLite with PostgreSQL:
   ```yaml
   services:
     db:
       image: postgres:15
       environment:
         POSTGRES_DB: scba_dash
         POSTGRES_USER: scba_dash
         POSTGRES_PASSWORD: your-password
       volumes:
         - postgres_data:/var/lib/postgresql/data
   
     scba-dash:
       # ... existing config ...
       depends_on:
         - db
       environment:
         DATABASE_URL: postgresql://scba_dash:your-password@db/scba_dash
   ```

3. **Add reverse proxy**: Use Nginx in front of the application for SSL/TLS

4. **Set strong SECRET_KEY**: Always use a strong, random secret key in production

5. **Monitor logs**: Set up log aggregation and monitoring

