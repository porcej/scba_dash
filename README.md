# SCBA Dashboard

A Flask-based dashboard application with real-time updates, task management, web scraping, and scheduled alerts.

## Features

- **Bootstrap 5 UI** with dark/light theme toggle
- **Real-time updates** using Flask-SocketIO
- **Task management** - authenticated users can create, update, and delete tasks
- **Web scraping** - automatically scrapes data from pstrax website
- **Scheduled alerts** - display messages at the bottom of the dashboard with start/end times
- **Settings** - manage pstrax credentials securely

## Requirements

- Python 3.8+
- pip

## Installation

1. Clone the repository:
```bash
cd scba_dash
```

2. Create a virtual environment:
```bash
python3 -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
```

3. Install dependencies:
```bash
pip install -r requirements.txt
```

4. Set up environment variables:
```bash
cp .env.example .env
# Edit .env and set SECRET_KEY (use a strong random string in production)
```

5. Initialize the database and create a default user:
```bash
python init_db.py
```

6. Run the application:
```bash
python run.py
```

The application will be available at `http://localhost:5000`

## Database Migrations

If you need to apply database migrations (for example, after pulling new changes that modify the database schema):

```bash
python migrate_db.py
```

Or using Flask-Migrate (if migrations are initialized):
```bash
flask --app run:app db upgrade
```

To create a new migration after modifying models:
```bash
flask --app run:app db migrate -m "Description of changes"
flask --app run:app db upgrade
```

## Adding Users

### Command Line Script

You can add users using the command-line script:

```bash
python add_user.py
```

The script will prompt you for:
- Username
- Password
- Whether the user should be an admin (y/n)

### Web Interface (Admin Only)

Admins can manage users through the web interface:
1. Log in as an admin user
2. Click "Users" in the navigation menu
3. Add, delete, or toggle admin status for users

**Note:** Admins cannot delete their own account or remove their own admin status.

## Initial Setup

Run `init_db.py` to create the database and an initial admin user. You'll be prompted to create a username and password.

## Configuration

### Environment Variables

- `SECRET_KEY`: Flask secret key for sessions (required)
- `DATABASE_URL`: Database connection string (defaults to SQLite)
- `ENCRYPTION_KEY`: Optional encryption key for sensitive data (uses SECRET_KEY if not set)
- `SCRAPE_INTERVAL_MINUTES`: Interval between automatic scrapes (default: 15)

### Pstrax Scraping

1. Log in to the dashboard
2. Navigate to Settings
3. Enter your pstrax username and password
4. Set the scrape interval (in minutes)
5. The scraper will automatically start fetching data at the configured interval

## Project Structure

```
scba_dash/
├── app/
│   ├── __init__.py          # Flask app factory
│   ├── models.py            # Database models
│   ├── routes.py            # Main routes
│   ├── auth.py              # Authentication routes
│   ├── forms.py             # WTForms forms
│   ├── scraper.py           # Web scraping logic
│   ├── tasks.py             # Background tasks
│   ├── socketio_events.py   # SocketIO event handlers
│   ├── config.py            # Configuration
│   ├── templates/           # Jinja2 templates
│   └── static/              # CSS, JS, images
├── instance/                # Instance-specific files
├── migrations/              # Database migrations
├── requirements.txt         # Python dependencies
├── run.py                   # Application entry point
└── init_db.py               # Database initialization script
```

## Customizing the Scraper

The pstrax scraper in `app/scraper.py` is a template that needs to be customized based on the actual pstrax website structure:

1. Update the `login()` method with the correct login URL and form field names
2. Update the `scrape_data()` method to extract the specific data you need from pstrax
3. Adjust selectors in BeautifulSoup queries based on the actual HTML structure

## Development

To run in development mode:

```bash
export FLASK_ENV=development
export FLASK_DEBUG=1
python run.py
```

## Production Deployment

1. Set a strong `SECRET_KEY` in your environment
2. Use a production-grade database (PostgreSQL recommended)
3. Use a production WSGI server (e.g., Gunicorn with eventlet for SocketIO)
4. Set up proper reverse proxy (nginx)
5. Enable HTTPS

## License

MIT License - see LICENSE file for details

