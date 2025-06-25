#!/usr/bin/env python3
"""
SQLite database initialization script for chat history.
Creates the database tables and ensures proper setup.
"""

import os
import sys

# Add the project root to Python path
project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, project_root)

from app import create_app
from app.db import flask_db as db
from app.models import Conversation, Message
from config import Config


def init_database():
    """Initialize the SQLite database with tables"""
    print("=" * 60)
    print("INITIALIZING SQLITE DATABASE")
    print("=" * 60)
    
    app = create_app()
    
    with app.app_context():
        # Get database file path
        db_uri = app.config['SQLALCHEMY_DATABASE_URI']
        if db_uri.startswith('sqlite:///'):
            db_path = db_uri.replace('sqlite:///', '')
            print(f"Database path: {db_path}")
        else:
            print(f"Database URI: {db_uri}")
        
        try:
            # Create all tables
            print("\n📋 Creating database tables...")
            db.create_all()
            
            # Verify tables were created
            inspector = db.inspect(db.engine)
            tables = inspector.get_table_names()
            
            print(f"✅ Successfully created {len(tables)} tables:")
            for table in tables:
                print(f"   - {table}")
                
                # Show column info for each table
                columns = inspector.get_columns(table)
                print(f"     Columns: {', '.join([col['name'] for col in columns])}")
            
            print(f"\n🎉 Database initialization complete!")
            print(f"📊 Database ready for storing conversations and messages")
            
            return True
            
        except Exception as e:
            print(f"❌ Error initializing database: {e}")
            return False


def reset_database():
    """Reset the database by dropping and recreating all tables"""
    print("=" * 60)
    print("RESETTING SQLITE DATABASE")
    print("=" * 60)
    print("⚠️  WARNING: This will delete all existing conversations and messages!")
    
    app = create_app()
    
    with app.app_context():
        try:
            # Drop all tables
            print("\n🗑️  Dropping all tables...")
            db.drop_all()
            
            # Recreate all tables
            print("📋 Recreating tables...")
            db.create_all()
            
            print("✅ Database reset complete!")
            return True
            
        except Exception as e:
            print(f"❌ Error resetting database: {e}")
            return False


def check_database():
    """Check database status and show statistics"""
    print("=" * 60)
    print("DATABASE STATUS CHECK")
    print("=" * 60)
    
    app = create_app()
    
    with app.app_context():
        try:
            # Check if tables exist
            inspector = db.inspect(db.engine)
            tables = inspector.get_table_names()
            
            if not tables:
                print("❌ No tables found. Run initialization first.")
                return False
            
            print(f"✅ Found {len(tables)} tables: {', '.join(tables)}")
            
            # Check data
            conversation_count = Conversation.query.count()
            message_count = Message.query.count()
            
            print(f"\n📊 Database Statistics:")
            print(f"   - Conversations: {conversation_count}")
            print(f"   - Messages: {message_count}")
            
            if conversation_count > 0:
                # Show recent conversations
                recent_conversations = Conversation.query.order_by(Conversation.updated_at.desc()).limit(5).all()
                print(f"\n🕒 Recent Conversations:")
                for conv in recent_conversations:
                    print(f"   - {conv.id}: {len(conv.messages)} messages (updated: {conv.updated_at})")
            
            return True
            
        except Exception as e:
            print(f"❌ Error checking database: {e}")
            return False


def main():
    """Main function to handle command line arguments"""
    import argparse
    
    parser = argparse.ArgumentParser(description='SQLite Database Management for Chat History')
    parser.add_argument('action', choices=['init', 'reset', 'check'], 
                       help='Action to perform: init (create tables), reset (drop and recreate), check (status)')
    
    args = parser.parse_args()
    
    if args.action == 'init':
        success = init_database()
    elif args.action == 'reset':
        success = reset_database()
    elif args.action == 'check':
        success = check_database()
    
    if success:
        print(f"\n✅ {args.action.capitalize()} operation completed successfully!")
    else:
        print(f"\n❌ {args.action.capitalize()} operation failed!")
        sys.exit(1)


if __name__ == "__main__":
    main()