# RAG Admission API Documentation

## Overview

This API provides endpoints for interacting with the RAG (Retrieval Augmented Generation) chatbot system for university admission inquiries. The API is designed to be consumed by a React frontend application.

## Base URL

```
http://localhost:5001/api
```

Note: The default port is 5001 to avoid conflicts with AirPlay on macOS. You can change it by setting the PORT environment variable.

## Authentication

Currently, the API does not require authentication. In production, you should implement proper authentication mechanisms.

## Response Format

All API responses follow a consistent format:

```json
{
  "success": true|false,
  "timestamp": "2024-01-20T10:30:00.000Z",
  "data": {}, // Present when success=true
  "error": "Error message" // Present when success=false
}
```

## Endpoints

### 1. Health Check

Check if the API service is running and healthy.

**Endpoint:** `GET /api/health`

**Response:**
```json
{
  "success": true,
  "timestamp": "2024-01-20T10:30:00.000Z",
  "data": {
    "status": "healthy",
    "service": "rag-admission-api",
    "version": "1.0.0"
  }
}
```

### 2. Chat

Submit a question to the RAG system and receive a response with sources.

**Endpoint:** `POST /api/chat`

**Request Body:**
```json
{
  "question": "¿Cuáles son los requisitos de admisión?",
  "conversation_id": "optional-uuid" // Optional, will be generated if not provided
}
```

**Response:**
```json
{
  "success": true,
  "timestamp": "2024-01-20T10:30:00.000Z",
  "data": {
    "conversation_id": "550e8400-e29b-41d4-a716-446655440000",
    "message": {
      "id": "msg-uuid",
      "question": "¿Cuáles son los requisitos de admisión?",
      "response": "Los requisitos de admisión incluyen...",
      "sources": [
        "https://admision.uandes.cl/requisitos",
        "https://admision.uandes.cl/documentos"
      ],
      "timestamp": "2024-01-20T10:30:00.000Z"
    }
  }
}
```

**Error Responses:**
- 400 Bad Request: Missing or empty question
- 500 Internal Server Error: RAG system error

### 3. Get Conversations

Retrieve all conversations or a specific conversation by ID.

**Endpoint:** `GET /api/conversations`

**Query Parameters:**
- `id` (optional): Specific conversation ID to retrieve

**Response (all conversations):**
```json
{
  "success": true,
  "timestamp": "2024-01-20T10:30:00.000Z",
  "data": {
    "conversations": [
      {
        "id": "550e8400-e29b-41d4-a716-446655440000",
        "created_at": "2024-01-20T10:00:00.000Z",
        "message_count": 5,
        "last_message": "2024-01-20T10:30:00.000Z"
      }
    ]
  }
}
```

**Response (specific conversation):**
```json
{
  "success": true,
  "timestamp": "2024-01-20T10:30:00.000Z",
  "data": {
    "id": "550e8400-e29b-41d4-a716-446655440000",
    "created_at": "2024-01-20T10:00:00.000Z",
    "messages": [
      {
        "id": "msg-uuid",
        "question": "¿Cuáles son los requisitos de admisión?",
        "response": "Los requisitos de admisión incluyen...",
        "sources": ["https://admision.uandes.cl/requisitos"],
        "timestamp": "2024-01-20T10:30:00.000Z"
      }
    ]
  }
}
```

**Error Responses:**
- 404 Not Found: Conversation ID not found

### 4. Delete Conversation

Delete a specific conversation and all its messages.

**Endpoint:** `DELETE /api/conversations/{conversation_id}`

**Response:**
```json
{
  "success": true,
  "timestamp": "2024-01-20T10:30:00.000Z",
  "data": {
    "message": "Conversation deleted successfully"
  }
}
```

**Error Responses:**
- 404 Not Found: Conversation ID not found

### 5. Upload PDF

Upload a PDF file and extract its text content to the data directory for RAG processing.

**Endpoint:** `POST /api/upload/pdf`

**Request:**
- Method: `POST`
- Content-Type: `multipart/form-data`
- Body Parameters:
  - `file` (required): PDF file to upload (max 10MB)
  - `source_url` (optional): Source URL for document attribution

**Response:**
```json
{
  "success": true,
  "timestamp": "2024-01-20T10:30:00.000Z",
  "data": {
    "document_id": "a1b2c3d4e5f6...",
    "filename": "admission_guide.pdf",
    "text_length": 15420,
    "source_url": "uploaded:admission_guide.pdf",
    "is_new": true,
    "message": "PDF uploaded successfully"
  }
}
```

**Error Responses:**
- 400 Bad Request: No file provided, invalid file type, or file too large
- 500 Internal Server Error: PDF processing error

**Notes:**
- Maximum file size: 10MB
- Only PDF files are accepted
- Text is extracted and saved with MD5 hash as filename
- Duplicate documents are detected and not re-saved
- After uploading, run `python -m app.services.rag.populate --reset` to update the vector database

### 6. API Information

Get information about the API and available endpoints.

**Endpoint:** `GET /api/info`

**Response:**
```json
{
  "success": true,
  "timestamp": "2024-01-20T10:30:00.000Z",
  "data": {
    "name": "RAG Admission API",
    "version": "1.0.0",
    "description": "API for university admission RAG chatbot",
    "endpoints": [
      {
        "path": "/api/health",
        "method": "GET",
        "description": "Health check endpoint"
      },
      // ... other endpoints
    ]
  }
}
```

## Usage Examples

### React/JavaScript Example

```javascript
// Chat request
const askQuestion = async (question, conversationId = null) => {
  const response = await fetch('http://localhost:5000/api/chat', {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
    },
    body: JSON.stringify({
      question: question,
      conversation_id: conversationId
    })
  });
  
  const data = await response.json();
  return data;
};

// Get conversations
const getConversations = async () => {
  const response = await fetch('http://localhost:5000/api/conversations');
  const data = await response.json();
  return data;
};

// Delete conversation
const deleteConversation = async (conversationId) => {
  const response = await fetch(`http://localhost:5000/api/conversations/${conversationId}`, {
    method: 'DELETE'
  });
  const data = await response.json();
  return data;
};
```

### cURL Examples

```bash
# Health check
curl http://localhost:5001/api/health

# Ask a question
curl -X POST http://localhost:5001/api/chat \
  -H "Content-Type: application/json" \
  -d '{"question": "¿Cuáles son los requisitos de admisión?"}'

# Get all conversations
curl http://localhost:5001/api/conversations

# Get specific conversation
curl http://localhost:5001/api/conversations?id=550e8400-e29b-41d4-a716-446655440000

# Delete conversation
curl -X DELETE http://localhost:5001/api/conversations/550e8400-e29b-41d4-a716-446655440000

# Upload PDF
curl -X POST http://localhost:5001/api/upload/pdf \
  -F "file=@/path/to/document.pdf" \
  -F "source_url=https://example.com/document.pdf"
```

## CORS Configuration

The API is configured to accept requests from any origin (`*`) by default. For production, you should configure specific allowed origins in the environment variables:

```bash
CORS_ORIGINS=http://localhost:3000,https://yourdomain.com
```

## Error Handling

All errors follow the standard response format with `success: false` and an `error` message. HTTP status codes are used appropriately:

- 200: Success
- 400: Bad Request (invalid input)
- 404: Not Found
- 500: Internal Server Error

## Notes

1. **Conversation Storage**: Currently, conversations are stored in memory and will be lost when the server restarts. In production, implement persistent storage (database).

2. **Rate Limiting**: No rate limiting is currently implemented. Consider adding rate limiting for production use.

3. **Authentication**: No authentication is required. Implement proper authentication for production use.

4. **Validation**: Basic input validation is implemented, but additional validation may be needed for production use.