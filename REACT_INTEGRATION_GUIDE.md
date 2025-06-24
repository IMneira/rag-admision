# React Integration Guide

This guide explains how to integrate the RAG Admission API with a React application.

## Quick Start

### 1. API Service

Create an API service file in your React app:

```javascript
// src/services/api.js
const API_BASE_URL = process.env.REACT_APP_API_URL || 'http://localhost:5001/api';

class AdmissionAPI {
  async checkHealth() {
    const response = await fetch(`${API_BASE_URL}/health`);
    return response.json();
  }

  async sendMessage(question, conversationId = null) {
    const response = await fetch(`${API_BASE_URL}/chat`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
      },
      body: JSON.stringify({
        question,
        conversation_id: conversationId
      })
    });
    
    if (!response.ok) {
      throw new Error('Failed to send message');
    }
    
    return response.json();
  }

  async getConversations() {
    const response = await fetch(`${API_BASE_URL}/conversations`);
    return response.json();
  }

  async getConversation(id) {
    const response = await fetch(`${API_BASE_URL}/conversations?id=${id}`);
    return response.json();
  }

  async deleteConversation(id) {
    const response = await fetch(`${API_BASE_URL}/conversations/${id}`, {
      method: 'DELETE'
    });
    return response.json();
  }

  async uploadPDF(file, sourceUrl = null) {
    const formData = new FormData();
    formData.append('file', file);
    if (sourceUrl) {
      formData.append('source_url', sourceUrl);
    }

    const response = await fetch(`${API_BASE_URL}/upload/pdf`, {
      method: 'POST',
      body: formData
    });

    if (!response.ok) {
      throw new Error('Failed to upload PDF');
    }

    return response.json();
  }
}

export default new AdmissionAPI();
```

### 2. Chat Component Example

```javascript
// src/components/Chat.js
import React, { useState, useEffect } from 'react';
import api from '../services/api';

function Chat() {
  const [messages, setMessages] = useState([]);
  const [input, setInput] = useState('');
  const [loading, setLoading] = useState(false);
  const [conversationId, setConversationId] = useState(null);

  const sendMessage = async (e) => {
    e.preventDefault();
    if (!input.trim()) return;

    setLoading(true);
    const userMessage = input;
    setInput('');

    // Add user message to UI
    setMessages(prev => [...prev, {
      type: 'user',
      content: userMessage,
      timestamp: new Date().toISOString()
    }]);

    try {
      const response = await api.sendMessage(userMessage, conversationId);
      
      if (response.success) {
        // Set conversation ID if this is the first message
        if (!conversationId) {
          setConversationId(response.data.conversation_id);
        }

        // Add bot response to UI
        setMessages(prev => [...prev, {
          type: 'bot',
          content: response.data.message.response,
          sources: response.data.message.sources,
          timestamp: response.data.message.timestamp
        }]);
      } else {
        // Handle error
        console.error('Error:', response.error);
      }
    } catch (error) {
      console.error('Failed to send message:', error);
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="chat-container">
      <div className="messages">
        {messages.map((msg, index) => (
          <div key={index} className={`message ${msg.type}`}>
            <div className="content">{msg.content}</div>
            {msg.sources && (
              <div className="sources">
                <strong>Fuentes:</strong>
                {msg.sources.map((source, i) => (
                  <a key={i} href={source} target="_blank" rel="noopener noreferrer">
                    {source}
                  </a>
                ))}
              </div>
            )}
          </div>
        ))}
        {loading && <div className="loading">Pensando...</div>}
      </div>
      
      <form onSubmit={sendMessage} className="input-form">
        <input
          type="text"
          value={input}
          onChange={(e) => setInput(e.target.value)}
          placeholder="Escribe tu pregunta aquí..."
          disabled={loading}
        />
        <button type="submit" disabled={loading || !input.trim()}>
          Enviar
        </button>
      </form>
    </div>
  );
}

export default Chat;
```

### 3. PDF Upload Component

```javascript
// src/components/PDFUpload.js
import React, { useState } from 'react';
import api from '../services/api';

function PDFUpload({ onUploadSuccess }) {
  const [file, setFile] = useState(null);
  const [sourceUrl, setSourceUrl] = useState('');
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);
  const [success, setSuccess] = useState(null);

  const handleFileChange = (e) => {
    const selectedFile = e.target.files[0];
    if (selectedFile && selectedFile.type === 'application/pdf') {
      setFile(selectedFile);
      setError(null);
    } else {
      setError('Please select a valid PDF file');
      setFile(null);
    }
  };

  const handleUpload = async (e) => {
    e.preventDefault();
    if (!file) {
      setError('Please select a file to upload');
      return;
    }

    setLoading(true);
    setError(null);
    setSuccess(null);

    try {
      const response = await api.uploadPDF(file, sourceUrl || null);
      
      if (response.success) {
        setSuccess(response.data.message);
        setFile(null);
        setSourceUrl('');
        
        // Reset file input
        const fileInput = document.getElementById('pdf-file-input');
        if (fileInput) fileInput.value = '';
        
        if (onUploadSuccess) {
          onUploadSuccess(response.data);
        }
      } else {
        setError(response.error);
      }
    } catch (err) {
      setError(err.message || 'Failed to upload PDF');
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="pdf-upload">
      <h3>Upload PDF Document</h3>
      <form onSubmit={handleUpload}>
        <div className="form-group">
          <label htmlFor="pdf-file-input">PDF File (max 10MB):</label>
          <input
            id="pdf-file-input"
            type="file"
            accept=".pdf"
            onChange={handleFileChange}
            disabled={loading}
          />
        </div>
        
        <div className="form-group">
          <label htmlFor="source-url">Source URL (optional):</label>
          <input
            id="source-url"
            type="url"
            value={sourceUrl}
            onChange={(e) => setSourceUrl(e.target.value)}
            placeholder="https://example.com/document.pdf"
            disabled={loading}
          />
        </div>
        
        <button type="submit" disabled={loading || !file}>
          {loading ? 'Uploading...' : 'Upload PDF'}
        </button>
      </form>
      
      {error && <div className="error">{error}</div>}
      {success && <div className="success">{success}</div>}
      
      <div className="upload-note">
        <p><strong>Note:</strong> After uploading, the document needs to be processed into the vector database.</p>
        <p>Run <code>python -m app.services.rag.populate --reset</code> to update the RAG system.</p>
      </div>
    </div>
  );
}

export default PDFUpload;
```

### 4. Conversation History Component

```javascript
// src/components/ConversationHistory.js
import React, { useState, useEffect } from 'react';
import api from '../services/api';

function ConversationHistory({ onSelectConversation }) {
  const [conversations, setConversations] = useState([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    loadConversations();
  }, []);

  const loadConversations = async () => {
    try {
      const response = await api.getConversations();
      if (response.success) {
        setConversations(response.data.conversations);
      }
    } catch (error) {
      console.error('Failed to load conversations:', error);
    } finally {
      setLoading(false);
    }
  };

  const deleteConversation = async (id) => {
    if (!window.confirm('¿Estás seguro de eliminar esta conversación?')) return;

    try {
      const response = await api.deleteConversation(id);
      if (response.success) {
        setConversations(prev => prev.filter(c => c.id !== id));
      }
    } catch (error) {
      console.error('Failed to delete conversation:', error);
    }
  };

  if (loading) return <div>Cargando conversaciones...</div>;

  return (
    <div className="conversation-history">
      <h3>Conversaciones anteriores</h3>
      {conversations.length === 0 ? (
        <p>No hay conversaciones guardadas</p>
      ) : (
        <ul>
          {conversations.map(conv => (
            <li key={conv.id}>
              <div onClick={() => onSelectConversation(conv.id)}>
                <span>Creada: {new Date(conv.created_at).toLocaleString()}</span>
                <span>Mensajes: {conv.message_count}</span>
              </div>
              <button onClick={() => deleteConversation(conv.id)}>
                Eliminar
              </button>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

export default ConversationHistory;
```

### 4. Environment Configuration

Create a `.env` file in your React app:

```bash
REACT_APP_API_URL=http://localhost:5001/api
```

### 5. Custom Hook for API State

```javascript
// src/hooks/useAdmissionChat.js
import { useState, useCallback } from 'react';
import api from '../services/api';

export function useAdmissionChat() {
  const [messages, setMessages] = useState([]);
  const [conversationId, setConversationId] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);

  const sendMessage = useCallback(async (question) => {
    setLoading(true);
    setError(null);

    try {
      const response = await api.sendMessage(question, conversationId);
      
      if (response.success) {
        if (!conversationId) {
          setConversationId(response.data.conversation_id);
        }
        
        setMessages(prev => [...prev, {
          question: response.data.message.question,
          response: response.data.message.response,
          sources: response.data.message.sources,
          timestamp: response.data.message.timestamp
        }]);
        
        return response.data.message;
      } else {
        throw new Error(response.error);
      }
    } catch (err) {
      setError(err.message);
      throw err;
    } finally {
      setLoading(false);
    }
  }, [conversationId]);

  const loadConversation = useCallback(async (id) => {
    setLoading(true);
    setError(null);

    try {
      const response = await api.getConversation(id);
      
      if (response.success) {
        setConversationId(id);
        setMessages(response.data.messages);
      } else {
        throw new Error(response.error);
      }
    } catch (err) {
      setError(err.message);
      throw err;
    } finally {
      setLoading(false);
    }
  }, []);

  const clearConversation = useCallback(() => {
    setMessages([]);
    setConversationId(null);
    setError(null);
  }, []);

  return {
    messages,
    conversationId,
    loading,
    error,
    sendMessage,
    loadConversation,
    clearConversation
  };
}
```

### 6. Error Handling

```javascript
// src/components/ErrorBoundary.js
import React from 'react';

class ErrorBoundary extends React.Component {
  constructor(props) {
    super(props);
    this.state = { hasError: false, error: null };
  }

  static getDerivedStateFromError(error) {
    return { hasError: true, error };
  }

  componentDidCatch(error, errorInfo) {
    console.error('Chat error:', error, errorInfo);
  }

  render() {
    if (this.state.hasError) {
      return (
        <div className="error-container">
          <h2>Algo salió mal</h2>
          <p>Por favor, recarga la página e intenta nuevamente.</p>
          <details>
            <summary>Detalles del error</summary>
            <pre>{this.state.error?.toString()}</pre>
          </details>
        </div>
      );
    }

    return this.props.children;
  }
}

export default ErrorBoundary;
```

### 7. TypeScript Support

If using TypeScript, here are the type definitions:

```typescript
// src/types/api.ts
export interface Message {
  id: string;
  question: string;
  response: string;
  sources: string[];
  timestamp: string;
}

export interface Conversation {
  id: string;
  created_at: string;
  messages: Message[];
}

export interface ConversationSummary {
  id: string;
  created_at: string;
  message_count: number;
  last_message: string | null;
}

export interface ApiResponse<T> {
  success: boolean;
  timestamp: string;
  data?: T;
  error?: string;
}

export interface ChatResponse {
  conversation_id: string;
  message: Message;
}

export interface UploadResponse {
  document_id: string;
  filename: string;
  text_length: number;
  source_url: string;
  is_new: boolean;
  message: string;
}
```

## Best Practices

1. **Error Handling**: Always handle API errors gracefully
2. **Loading States**: Show loading indicators during API calls
3. **Caching**: Consider implementing response caching for better performance
4. **Retry Logic**: Implement retry logic for failed requests
5. **Accessibility**: Ensure chat interface is accessible
6. **Mobile Responsive**: Design for mobile devices
7. **Real-time Updates**: Consider WebSockets for real-time features

## Example CSS

```css
/* src/styles/Chat.css */
.chat-container {
  display: flex;
  flex-direction: column;
  height: 600px;
  max-width: 800px;
  margin: 0 auto;
  border: 1px solid #ddd;
  border-radius: 8px;
}

.messages {
  flex: 1;
  overflow-y: auto;
  padding: 20px;
  background: #f5f5f5;
}

.message {
  margin-bottom: 15px;
  padding: 10px 15px;
  border-radius: 8px;
  max-width: 70%;
}

.message.user {
  background: #007bff;
  color: white;
  margin-left: auto;
}

.message.bot {
  background: white;
  border: 1px solid #ddd;
}

.sources {
  margin-top: 10px;
  font-size: 0.9em;
}

.sources a {
  display: block;
  color: #007bff;
  text-decoration: none;
  margin-top: 5px;
}

.input-form {
  display: flex;
  padding: 20px;
  background: white;
  border-top: 1px solid #ddd;
}

.input-form input {
  flex: 1;
  padding: 10px;
  border: 1px solid #ddd;
  border-radius: 4px;
  margin-right: 10px;
}

.input-form button {
  padding: 10px 20px;
  background: #007bff;
  color: white;
  border: none;
  border-radius: 4px;
  cursor: pointer;
}

.input-form button:disabled {
  opacity: 0.6;
  cursor: not-allowed;
}

.loading {
  text-align: center;
  color: #666;
  font-style: italic;
}
```

## Testing

```javascript
// src/services/api.test.js
import api from './api';

describe('AdmissionAPI', () => {
  test('health check returns success', async () => {
    const response = await api.checkHealth();
    expect(response.success).toBe(true);
    expect(response.data.status).toBe('healthy');
  });

  test('send message returns conversation id', async () => {
    const response = await api.sendMessage('Test question');
    expect(response.success).toBe(true);
    expect(response.data.conversation_id).toBeDefined();
    expect(response.data.message.question).toBe('Test question');
  });
});
```