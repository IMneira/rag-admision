# Database Usage Guide

## Overview

The RAG Admission API now uses SQLite for persistent storage of chat conversations and messages. This replaces the previous in-memory storage and provides data persistence across server restarts.

## Database Schema

### Tables

#### `conversations`
- `id` (String, Primary Key): UUID for the conversation
- `created_at` (DateTime): When the conversation was created
- `updated_at` (DateTime): When the conversation was last updated
- `title` (String, Optional): Optional title for the conversation

#### `messages`
- `id` (String, Primary Key): UUID for the message
- `conversation_id` (String, Foreign Key): References conversations.id
- `question` (Text): The user's question
- `response` (Text): The AI's response
- `sources` (Text): JSON string of source URLs
- `timestamp` (DateTime): When the message was created

## Database Management Commands

### Initialize Database
```bash
python app/db/init_sqlite.py init
```
Creates the SQLite database and all required tables.

### Check Database Status
```bash
python app/db/init_sqlite.py check
```
Shows database statistics including number of conversations and messages.

### Reset Database
```bash
python app/db/init_sqlite.py reset
```
⚠️ **WARNING**: Deletes all conversations and messages, then recreates empty tables.

## Database Location

The SQLite database file is created at:
```
/path/to/project/chat_history.db
```

You can change this location by setting the `DATABASE_URI` environment variable:
```bash
export DATABASE_URI="sqlite:///custom/path/to/database.db"
```

## API Behavior Changes

### What Changed
- Conversations are now persistent across server restarts
- All conversation data is stored in SQLite instead of memory
- Conversation IDs remain consistent across sessions

### What Stayed the Same
- All API endpoints work exactly the same
- Response formats are identical
- No breaking changes for frontend applications

## Development Examples

### Creating a Conversation
```bash
curl -X POST http://localhost:5001/api/chat \
  -H "Content-Type: application/json" \
  -d '{"question": "¿Cuáles son los requisitos de admisión?"}'
```

### Listing Conversations
```bash
curl http://localhost:5001/api/conversations
```

### Getting a Specific Conversation
```bash
curl "http://localhost:5001/api/conversations?id=YOUR_CONVERSATION_ID"
```

### Deleting a Conversation
```bash
curl -X DELETE http://localhost:5001/api/conversations/YOUR_CONVERSATION_ID
```

## Database Models in Code

### Using the Models
```python
from app.models import Conversation, Message

# Create a new conversation
conv = Conversation.create_conversation(title="My Chat")

# Add a message
message = Message.create_message(
    conversation_id=conv.id,
    question="Hello",
    response="Hi there!",
    sources=["https://example.com"]
)

# Get all conversations
conversations = Conversation.get_all()

# Get a specific conversation
conv = Conversation.get_by_id("some-uuid")

# Delete a conversation
conv.delete()
```

## Backup and Migration

### Backup Database
```bash
cp chat_history.db chat_history_backup.db
```

### View Database Contents (SQLite CLI)
```bash
sqlite3 chat_history.db
.tables
.schema conversations
SELECT * FROM conversations;
```

## Troubleshooting

### Database File Not Found
If you get database errors, initialize the database:
```bash
python app/db/init_sqlite.py init
```

### Permission Errors
Ensure the application has write permissions to the database directory:
```bash
chmod 755 /path/to/project/
chmod 664 chat_history.db
```

### Database Corruption
If the database becomes corrupted, reset it:
```bash
python app/db/init_sqlite.py reset
```
⚠️ This will delete all conversation data.

## Production Considerations

For production deployments, consider:

1. **PostgreSQL**: Set `DATABASE_URI` to a PostgreSQL connection string
2. **Backups**: Regular database backups
3. **Monitoring**: Database size and performance monitoring
4. **Scaling**: Connection pooling for high-traffic scenarios

### Example PostgreSQL Setup
```bash
export DATABASE_URI="postgresql://user:password@localhost/chat_db"
```