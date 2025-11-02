#!/usr/bin/env python
"""
Database migration script to add pstrax_base_url field
Run this script to apply the migration
"""
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# Set up environment to prevent background tasks from running
os.environ['FLASK_SKIP_BACKGROUND_TASKS'] = '1'

from app import create_app, db

flask_app = create_app()

with flask_app.app_context():
    # Initialize alembic_version table if it doesn't exist
    from sqlalchemy import inspect, text
    
    inspector = inspect(db.engine)
    tables = inspector.get_table_names()
    
    if 'alembic_version' not in tables:
        print("Initializing migrations table...")
        # Create alembic_version table
        with db.engine.connect() as conn:
            conn.execute(text("""
                CREATE TABLE IF NOT EXISTS alembic_version (
                    version_num VARCHAR(32) NOT NULL PRIMARY KEY
                )
            """))
            conn.commit()
        print("Migrations table created.")
    
    # Check current state
    if 'scrape_config' in tables:
        cols = [c['name'] for c in inspector.get_columns('scrape_config')]
        if 'pstrax_base_url' in cols:
            print("Column pstrax_base_url already exists. Migration not needed.")
            sys.exit(0)
    
    # Apply the migration manually
    print("Applying migration: Add pstrax_base_url to scrape_config...")
    
    try:
        with db.engine.connect() as conn:
            # Add the column
            conn.execute(text("""
                ALTER TABLE scrape_config 
                ADD COLUMN pstrax_base_url VARCHAR(255) NOT NULL DEFAULT 'https://pstrax.com'
            """))
            
            # Update any NULL values (shouldn't happen with NOT NULL, but just in case)
            conn.execute(text("""
                UPDATE scrape_config 
                SET pstrax_base_url = 'https://pstrax.com' 
                WHERE pstrax_base_url IS NULL
            """))
            
            # Record the migration
            conn.execute(text("""
                INSERT OR IGNORE INTO alembic_version (version_num) 
                VALUES ('20250101_000000')
            """))
            conn.commit()
        
        print("Migration applied successfully!")
        print("Column pstrax_base_url added to scrape_config table.")
        
    except Exception as e:
        if 'duplicate column name' in str(e).lower() or 'already exists' in str(e).lower():
            print("Column already exists. Migration already applied.")
        else:
            print(f"Error applying migration: {e}")
            raise

