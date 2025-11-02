from flask import Flask
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager
from flask_socketio import SocketIO
from flask_migrate import Migrate
from flask_wtf.csrf import CSRFProtect
from app.config import Config

# Initialize extensions
db = SQLAlchemy()
login_manager = LoginManager()
socketio = SocketIO()
migrate = Migrate()
csrf = CSRFProtect()


@login_manager.user_loader
def load_user(user_id):
    """Load user for Flask-Login"""
    from app.models import User
    return User.query.get(int(user_id))


def create_app(config_class=Config):
    """Application factory pattern"""
    flask_app = Flask(__name__)
    flask_app.config.from_object(config_class)
    
    # Initialize extensions with flask_app
    db.init_app(flask_app)
    login_manager.init_app(flask_app)
    migrate.init_app(flask_app, db)
    
    # Initialize SocketIO BEFORE CSRF to ensure Socket.IO middleware processes requests first
    # This ensures /socket.io/ requests are handled before CSRF protection can interfere
    socketio.init_app(
        flask_app,
        async_mode=flask_app.config['SOCKETIO_ASYNC_MODE'],
        cors_allowed_origins="*",
        logger=True,
        engineio_logger=True
    )
    
    # Initialize CSRF after SocketIO so Socket.IO requests are handled first
    csrf.init_app(flask_app)
    
    # Note: Flask-SocketIO handles requests before CSRF can intercept them
    # The socketio.init_app() registers middleware that processes /socket.io/ requests first
    # If you still get CSRF errors, ensure socketio.init_app() is called before csrf.init_app()
    
    # Configure Flask-Login
    login_manager.login_view = 'auth.login'
    login_manager.login_message = 'Please log in to access this page.'
    login_manager.login_message_category = 'info'
    
    # Register blueprints
    from app.auth import bp as auth_bp
    flask_app.register_blueprint(auth_bp, url_prefix='/auth')
    
    from app.routes import bp as main_bp
    flask_app.register_blueprint(main_bp)
    
    # Import SocketIO event handlers
    import app.socketio_events  # noqa: F401
    
    # Create database tables (will be created when first accessed with app context)
    # Background tasks will be started in run.py
    
    return flask_app
