#!/usr/bin/env python
"""
Initialize database and create default admin user
"""
import sys
import os

# Add the parent directory to the path to ensure imports work
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app import create_app
from app import db
from app.models import User

flask_app = create_app()

with flask_app.app_context():
    # Create all tables
    db.create_all()
    
    # Check if any users exist
    if User.query.first() is None:
        print("No users found. Creating admin user...")
        username = input("Enter username: ").strip()
        password = input("Enter password: ").strip()
        
        if username and password:
            admin_user = User(username=username, is_admin=True)
            admin_user.set_password(password)
            db.session.add(admin_user)
            db.session.commit()
            print(f"Admin user '{username}' created successfully!")
        else:
            print("Username and password are required.")
    else:
        print("Database already initialized. Users exist.")

