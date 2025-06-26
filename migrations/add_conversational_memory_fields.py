"""
Database migration script to add conversational memory fields
Run this script to add the new fields to existing database tables.
"""

from app.db import flask_db as db
from sqlalchemy import text
import logging

logging.basicConfig(level=logging.INFO)

def add_conversational_memory_fields():
    """Add conversational memory fields to existing database"""
    
    try:
        # Add fields to conversations table
        logging.info("Adding conversational memory fields to conversations table...")
        
        # Check if fields already exist
        result = db.session.execute(text("PRAGMA table_info(conversations)"))
        columns = [row[1] for row in result.fetchall()]
        
        if 'summary' not in columns:
            db.session.execute(text("ALTER TABLE conversations ADD COLUMN summary TEXT"))
            logging.info("Added 'summary' column to conversations table")
        
        if 'total_turns' not in columns:
            db.session.execute(text("ALTER TABLE conversations ADD COLUMN total_turns INTEGER DEFAULT 0"))
            logging.info("Added 'total_turns' column to conversations table")
        
        # Add fields to messages table
        logging.info("Adding conversational memory fields to messages table...")
        
        result = db.session.execute(text("PRAGMA table_info(messages)"))
        columns = [row[1] for row in result.fetchall()]
        
        if 'context_used' not in columns:
            db.session.execute(text("ALTER TABLE messages ADD COLUMN context_used TEXT"))
            logging.info("Added 'context_used' column to messages table")
        
        if 'is_follow_up' not in columns:
            db.session.execute(text("ALTER TABLE messages ADD COLUMN is_follow_up BOOLEAN DEFAULT 0"))
            logging.info("Added 'is_follow_up' column to messages table")
        
        if 'query_type' not in columns:
            db.session.execute(text("ALTER TABLE messages ADD COLUMN query_type VARCHAR(50)"))
            logging.info("Added 'query_type' column to messages table")
        
        # Update existing conversations to have correct turn counts
        logging.info("Updating existing conversation turn counts...")
        update_query = text("""
            UPDATE conversations 
            SET total_turns = (
                SELECT COUNT(*) 
                FROM messages 
                WHERE messages.conversation_id = conversations.id
            )
            WHERE total_turns = 0 OR total_turns IS NULL
        """)
        result = db.session.execute(update_query)
        
        db.session.commit()
        logging.info(f"Updated {result.rowcount} conversations with turn counts")
        logging.info("Conversational memory fields added successfully!")
        
    except Exception as e:
        logging.error(f"Error adding conversational memory fields: {e}")
        db.session.rollback()
        raise

def add_conversational_memory_fields_postgresql():
    """Add conversational memory fields for PostgreSQL"""
    
    try:
        logging.info("Adding conversational memory fields for PostgreSQL...")
        
        # Check if columns exist and add them if they don't
        db.session.execute(text("""
            DO $$ 
            BEGIN
                -- Add summary column to conversations if it doesn't exist
                IF NOT EXISTS (SELECT 1 FROM information_schema.columns 
                              WHERE table_name='conversations' AND column_name='summary') THEN
                    ALTER TABLE conversations ADD COLUMN summary TEXT;
                END IF;
                
                -- Add total_turns column to conversations if it doesn't exist
                IF NOT EXISTS (SELECT 1 FROM information_schema.columns 
                              WHERE table_name='conversations' AND column_name='total_turns') THEN
                    ALTER TABLE conversations ADD COLUMN total_turns INTEGER DEFAULT 0;
                END IF;
                
                -- Add context_used column to messages if it doesn't exist
                IF NOT EXISTS (SELECT 1 FROM information_schema.columns 
                              WHERE table_name='messages' AND column_name='context_used') THEN
                    ALTER TABLE messages ADD COLUMN context_used TEXT;
                END IF;
                
                -- Add is_follow_up column to messages if it doesn't exist
                IF NOT EXISTS (SELECT 1 FROM information_schema.columns 
                              WHERE table_name='messages' AND column_name='is_follow_up') THEN
                    ALTER TABLE messages ADD COLUMN is_follow_up BOOLEAN DEFAULT FALSE;
                END IF;
                
                -- Add query_type column to messages if it doesn't exist
                IF NOT EXISTS (SELECT 1 FROM information_schema.columns 
                              WHERE table_name='messages' AND column_name='query_type') THEN
                    ALTER TABLE messages ADD COLUMN query_type VARCHAR(50);
                END IF;
            END $$;
        """))
        
        # Update existing conversations with turn counts
        update_query = text("""
            UPDATE conversations 
            SET total_turns = (
                SELECT COUNT(*) 
                FROM messages 
                WHERE messages.conversation_id = conversations.id
            )
            WHERE total_turns = 0 OR total_turns IS NULL
        """)
        result = db.session.execute(update_query)
        
        db.session.commit()
        logging.info(f"Updated {result.rowcount} conversations with turn counts")
        logging.info("PostgreSQL conversational memory fields added successfully!")
        
    except Exception as e:
        logging.error(f"Error adding PostgreSQL conversational memory fields: {e}")
        db.session.rollback()
        raise

def main():
    """Main migration function"""
    from config import Config
    
    try:
        # Detect database type
        database_uri = getattr(Config, 'DATABASE_URI', 'sqlite:///chat_history.db')
        
        if database_uri.startswith('postgresql'):
            add_conversational_memory_fields_postgresql()
        else:
            # Default to SQLite
            add_conversational_memory_fields()
            
        print("✅ Conversational memory fields migration completed successfully!")
        
    except Exception as e:
        print(f"❌ Migration failed: {e}")
        raise

if __name__ == "__main__":
    main()