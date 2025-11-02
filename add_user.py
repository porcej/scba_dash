#!/usr/bin/env python
"""
Script to add users to the database
"""
import sys
import os

# Add the parent directory to the path to ensure imports work
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app import create_app, db
from app.models import User

flask_app = create_app()

with flask_app.app_context():
    print("Add User to SCBA Dashboard")
    print("=" * 40)
    
    username = input("Enter username: ").strip()
    if not username:
        print("Username is required.")
        sys.exit(1)
    
    # Check if user already exists
    existing_user = User.query.filter_by(username=username).first()
    if existing_user:
        print(f"Error: User '{username}' already exists!")
        sys.exit(1)
    
    password = input("Enter password: ").strip()
    if not password:
        print("Password is required.")
        sys.exit(1)
    
    is_admin_input = input("Is admin? (y/n) [n]: ").strip().lower()
    is_admin = is_admin_input in ('y', 'yes', 'true', '1')
    
    # Create user
    new_user = User(username=username, is_admin=is_admin)
    new_user.set_password(password)
    db.session.add(new_user)
    db.session.commit()
    
    admin_status = "Admin" if is_admin else "Regular user"
    print(f"\n✓ User '{username}' created successfully as {admin_status}!")

