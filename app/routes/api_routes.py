from flask import Blueprint, request, jsonify
from app.services.rag.query_engine import query_rag
from datetime import datetime
import json
import os
import uuid
import hashlib
from werkzeug.utils import secure_filename
from pypdf import PdfReader
import io

api_bp = Blueprint('api', __name__, url_prefix='/api')

# In-memory storage for conversations (in production, use a database)
conversations = {}

# Upload configuration
ALLOWED_EXTENSIONS = {'pdf'}
MAX_FILE_SIZE = 10 * 1024 * 1024  # 10MB

def allowed_file(filename):
    """Check if file has allowed extension"""
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

def extract_text_from_pdf(file_stream):
    """Extract text content from PDF file"""
    try:
        pdf_reader = PdfReader(file_stream)
        text = ""
        for page_num, page in enumerate(pdf_reader.pages):
            page_text = page.extract_text()
            if page_text:
                text += f"\n--- Page {page_num + 1} ---\n{page_text}"
        return text.strip()
    except Exception as e:
        raise Exception(f"Failed to extract text from PDF: {str(e)}")

def save_document_to_data_dir(content, source_url=None):
    """Save document content to data directory with MD5 hash as filename"""
    # Generate MD5 hash of content
    content_hash = hashlib.md5(content.encode('utf-8')).hexdigest()
    
    # Save to data directory
    data_dir = 'data'
    if not os.path.exists(data_dir):
        os.makedirs(data_dir)
    
    file_path = os.path.join(data_dir, f"{content_hash}.txt")
    
    # Check if file already exists
    if os.path.exists(file_path):
        return content_hash, False  # File already exists
    
    # Save content
    with open(file_path, 'w', encoding='utf-8') as f:
        f.write(content)
    
    # Update URL index if source URL provided
    if source_url:
        url_index_path = os.path.join(data_dir, 'url_index.json')
        url_index = {}
        
        if os.path.exists(url_index_path):
            with open(url_index_path, 'r', encoding='utf-8') as f:
                url_index = json.load(f)
        
        url_index[content_hash] = source_url
        
        with open(url_index_path, 'w', encoding='utf-8') as f:
            json.dump(url_index, f, indent=2, ensure_ascii=False)
    
    return content_hash, True  # New file created

def load_url_index():
    """Load URL index from JSON file"""
    url_index_path = os.path.join('data', 'url_index.json')
    with open(url_index_path, 'r', encoding='utf-8') as f:
        return json.load(f)

def format_response(success=True, data=None, error=None, status_code=200):
    """Standardize API responses"""
    response = {
        'success': success,
        'timestamp': datetime.utcnow().isoformat() + 'Z'
    }
    
    if success and data is not None:
        response['data'] = data
    elif not success and error is not None:
        response['error'] = error
        
    return jsonify(response), status_code

@api_bp.route('/health', methods=['GET'])
def health_check():
    """Health check endpoint for monitoring"""
    return format_response(
        success=True,
        data={
            'status': 'healthy',
            'service': 'rag-admission-api',
            'version': '1.0.0'
        }
    )

@api_bp.route('/chat', methods=['POST'])
def chat():
    """Main chat endpoint for RAG queries"""
    try:
        # Validate request
        if not request.json:
            return format_response(
                success=False,
                error='Request must be JSON',
                status_code=400
            )
        
        data = request.json
        question = data.get('question', '').strip()
        conversation_id = data.get('conversation_id')
        
        if not question:
            return format_response(
                success=False,
                error='Question is required',
                status_code=400
            )
        
        # Generate conversation ID if not provided
        if not conversation_id:
            conversation_id = str(uuid.uuid4())
        
        # Query RAG system
        response_text, sources = query_rag(question)
        
        # Extract document hashes from file paths
        doc_hashes = [path.split('/')[1].split('.')[0] for path in sources]
        
        # Load URL index and map hashes to URLs
        url_index = load_url_index()
        source_urls = []
        for hash_id in doc_hashes:
            url = url_index.get(hash_id)
            if url and url not in source_urls:
                source_urls.append(url)
        
        # Create message object
        message = {
            'id': str(uuid.uuid4()),
            'question': question,
            'response': str(response_text),
            'sources': source_urls,
            'timestamp': datetime.utcnow().isoformat() + 'Z'
        }
        
        # Store in conversation history
        if conversation_id not in conversations:
            conversations[conversation_id] = {
                'id': conversation_id,
                'created_at': datetime.utcnow().isoformat() + 'Z',
                'messages': []
            }
        conversations[conversation_id]['messages'].append(message)
        
        return format_response(
            success=True,
            data={
                'conversation_id': conversation_id,
                'message': message
            }
        )
        
    except Exception as e:
        return format_response(
            success=False,
            error=f'Internal server error: {str(e)}',
            status_code=500
        )

@api_bp.route('/conversations', methods=['GET'])
def get_conversations():
    """Get all conversations or a specific conversation"""
    try:
        conversation_id = request.args.get('id')
        
        if conversation_id:
            # Get specific conversation
            if conversation_id not in conversations:
                return format_response(
                    success=False,
                    error='Conversation not found',
                    status_code=404
                )
            return format_response(
                success=True,
                data=conversations[conversation_id]
            )
        else:
            # Get all conversations (metadata only)
            conversations_list = []
            for conv_id, conv_data in conversations.items():
                conversations_list.append({
                    'id': conv_id,
                    'created_at': conv_data['created_at'],
                    'message_count': len(conv_data['messages']),
                    'last_message': conv_data['messages'][-1]['timestamp'] if conv_data['messages'] else None
                })
            
            return format_response(
                success=True,
                data={'conversations': conversations_list}
            )
            
    except Exception as e:
        return format_response(
            success=False,
            error=f'Internal server error: {str(e)}',
            status_code=500
        )

@api_bp.route('/conversations/<conversation_id>', methods=['DELETE'])
def delete_conversation(conversation_id):
    """Delete a specific conversation"""
    try:
        if conversation_id not in conversations:
            return format_response(
                success=False,
                error='Conversation not found',
                status_code=404
            )
        
        del conversations[conversation_id]
        
        return format_response(
            success=True,
            data={'message': 'Conversation deleted successfully'}
        )
        
    except Exception as e:
        return format_response(
            success=False,
            error=f'Internal server error: {str(e)}',
            status_code=500
        )

@api_bp.route('/upload/pdf', methods=['POST'])
def upload_pdf():
    """Upload PDF file and extract text to data directory"""
    try:
        # Check if file is in request
        if 'file' not in request.files:
            return format_response(
                success=False,
                error='No file provided',
                status_code=400
            )
        
        file = request.files['file']
        
        # Check if file is selected
        if file.filename == '':
            return format_response(
                success=False,
                error='No file selected',
                status_code=400
            )
        
        # Validate file extension
        if not allowed_file(file.filename):
            return format_response(
                success=False,
                error='Invalid file type. Only PDF files are allowed',
                status_code=400
            )
        
        # Check file size
        file.seek(0, os.SEEK_END)
        file_size = file.tell()
        file.seek(0)
        
        if file_size > MAX_FILE_SIZE:
            return format_response(
                success=False,
                error=f'File too large. Maximum size is {MAX_FILE_SIZE / 1024 / 1024}MB',
                status_code=400
            )
        
        # Get optional metadata
        source_url = request.form.get('source_url', f'uploaded:{secure_filename(file.filename)}')
        
        # Extract text from PDF
        pdf_text = extract_text_from_pdf(io.BytesIO(file.read()))
        
        if not pdf_text:
            return format_response(
                success=False,
                error='No text could be extracted from the PDF',
                status_code=400
            )
        
        # Save to data directory
        doc_hash, is_new = save_document_to_data_dir(pdf_text, source_url)
        
        return format_response(
            success=True,
            data={
                'document_id': doc_hash,
                'filename': secure_filename(file.filename),
                'text_length': len(pdf_text),
                'source_url': source_url,
                'is_new': is_new,
                'message': 'PDF uploaded successfully' if is_new else 'Document already exists in database'
            }
        )
        
    except Exception as e:
        return format_response(
            success=False,
            error=f'Failed to process PDF: {str(e)}',
            status_code=500
        )

@api_bp.route('/info', methods=['GET'])
def api_info():
    """Get API information and available endpoints"""
    endpoints = [
        {
            'path': '/api/health',
            'method': 'GET',
            'description': 'Health check endpoint'
        },
        {
            'path': '/api/chat',
            'method': 'POST',
            'description': 'Submit a question to the RAG system',
            'params': {
                'question': 'string (required)',
                'conversation_id': 'string (optional)'
            }
        },
        {
            'path': '/api/conversations',
            'method': 'GET',
            'description': 'Get all conversations or specific conversation',
            'params': {
                'id': 'string (optional) - conversation ID'
            }
        },
        {
            'path': '/api/conversations/<id>',
            'method': 'DELETE',
            'description': 'Delete a specific conversation'
        },
        {
            'path': '/api/upload/pdf',
            'method': 'POST',
            'description': 'Upload PDF file and extract text',
            'params': {
                'file': 'file (required) - PDF file to upload',
                'source_url': 'string (optional) - Source URL for the document'
            }
        },
        {
            'path': '/api/info',
            'method': 'GET',
            'description': 'Get API information'
        }
    ]
    
    return format_response(
        success=True,
        data={
            'name': 'RAG Admission API',
            'version': '1.0.0',
            'description': 'API for university admission RAG chatbot',
            'endpoints': endpoints
        }
    )