from flask import Blueprint, request, jsonify
from flask_login import current_user
from app.services.rag.enhanced_query_engine import EnhancedQueryEngine
from app.models import Conversation, Message
from app.db import flask_db as db
from app.auth.decorators import login_required, admin_required
from datetime import datetime
import json
import os
import uuid
import hashlib
from werkzeug.utils import secure_filename
from pypdf import PdfReader
import io

api_bp = Blueprint('api', __name__, url_prefix='/api')

# Initialize Enhanced RAG Query Engine
enhanced_rag = EnhancedQueryEngine()

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
    
    file_path = os.path.join(data_dir, f"{content_hash}.md")
    
    # Check if file already exists
    if os.path.exists(file_path):
        return content_hash, False, file_path  # File already exists
    
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
    
    return content_hash, True, file_path  # New file created

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
@login_required
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
        
        # Get or create conversation
        if conversation_id:
            # Check if user owns this conversation
            conversation = Conversation.get_by_id_and_user(conversation_id, current_user.id)
            if not conversation:
                return format_response(
                    success=False,
                    error='Conversation not found or access denied',
                    status_code=404
                )
        else:
            # Create new conversation for current user
            conversation = Conversation.create_conversation(user_id=current_user.id)
            conversation_id = conversation.id
        
        # Query Enhanced RAG system
        rag_response = enhanced_rag.query(question, enable_confidence_scoring=True)
        
        # Extract document hashes from source IDs and map to URLs
        doc_hashes = []
        for source_id in rag_response.sources:
            if '/' in source_id:
                hash_id = source_id.split('/')[1].split('.')[0]
            else:
                hash_id = source_id.split(':')[0] if ':' in source_id else source_id
            doc_hashes.append(hash_id)
        
        # Load URL index and map hashes to URLs
        url_index = load_url_index()
        source_urls = []
        for hash_id in doc_hashes:
            url = url_index.get(hash_id)
            if url and url not in source_urls:
                source_urls.append(url)
        
        # Create and save message to database
        message = Message.create_message(
            conversation_id=conversation_id,
            question=question,
            response=str(rag_response.answer),
            sources=source_urls
        )
        
        # Prepare enhanced response data
        response_data = {
            'conversation_id': conversation_id,
            'message': message.to_dict(),
            'enhanced_info': {
                'query_type': rag_response.query_analysis.get('query_type', 'general'),
                'complexity_score': rag_response.query_analysis.get('complexity_score', 0.5),
                'processing_time': round(rag_response.processing_time, 3),
                'context_summary': rag_response.context_summary,
                'recommendations': rag_response.recommendations
            }
        }
        
        # Add confidence information if available
        if rag_response.confidence:
            response_data['enhanced_info']['confidence'] = {
                'level': rag_response.confidence.level.value,
                'score': round(rag_response.confidence.overall_score, 3),
                'explanation': rag_response.confidence.explanation,
                'recommendations': rag_response.confidence.recommendations
            }
        
        return format_response(
            success=True,
            data=response_data
        )
        
    except Exception as e:
        db.session.rollback()
        return format_response(
            success=False,
            error=f'Internal server error: {str(e)}',
            status_code=500
        )

@api_bp.route('/conversations', methods=['GET'])
@login_required
def get_conversations():
    """Get all conversations or a specific conversation"""
    try:
        conversation_id = request.args.get('id')
        
        if conversation_id:
            # Get specific conversation with messages (user-scoped)
            conversation = Conversation.get_by_id_and_user(conversation_id, current_user.id)
            if not conversation:
                return format_response(
                    success=False,
                    error='Conversation not found or access denied',
                    status_code=404
                )
            return format_response(
                success=True,
                data=conversation.to_dict_with_messages()
            )
        else:
            # Get all conversations for current user (metadata only)
            conversations = Conversation.get_by_user(current_user.id)
            conversations_list = [conv.to_dict() for conv in conversations]
            
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
@login_required
def delete_conversation(conversation_id):
    """Delete a specific conversation"""
    try:
        conversation = Conversation.get_by_id_and_user(conversation_id, current_user.id)
        if not conversation:
            return format_response(
                success=False,
                error='Conversation not found or access denied',
                status_code=404
            )
        
        conversation.delete()
        
        return format_response(
            success=True,
            data={'message': 'Conversation deleted successfully'}
        )
        
    except Exception as e:
        db.session.rollback()
        return format_response(
            success=False,
            error=f'Internal server error: {str(e)}',
            status_code=500
        )

@api_bp.route('/upload/pdf', methods=['POST'])
@admin_required
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
        doc_hash, is_new, file_path = save_document_to_data_dir(pdf_text, source_url)
        
        # Process the document into the vector database if it's new
        processing_result = None
        if is_new:
            try:
                from app.services.rag.populate import process_single_document
                processing_result = process_single_document(file_path, source_url)
            except Exception as e:
                # Don't fail the upload if processing fails
                processing_result = {
                    'success': False,
                    'chunks_added': 0,
                    'header_generated': False,
                    'error': f'Processing failed: {str(e)}'
                }
        
        response_data = {
            'document_id': doc_hash,
            'filename': secure_filename(file.filename),
            'text_length': len(pdf_text),
            'source_url': source_url,
            'is_new': is_new,
            'message': 'PDF uploaded successfully' if is_new else 'Document already exists in database'
        }
        
        # Add processing information if document was processed
        if processing_result:
            response_data['processing'] = {
                'success': processing_result['success'],
                'chunks_added': processing_result['chunks_added'],
                'header_generated': processing_result['header_generated'],
                'ready_for_queries': processing_result['success']
            }
            if processing_result['error']:
                response_data['processing']['error'] = processing_result['error']
        
        return format_response(
            success=True,
            data=response_data
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
        },
        {
            'path': '/api/rag/stats',
            'method': 'GET',
            'description': 'Get RAG system performance statistics (admin only)'
        },
        {
            'path': '/api/rag/reset-stats',
            'method': 'POST',
            'description': 'Reset RAG system statistics (admin only)'
        }
    ]
    
    return format_response(
        success=True,
        data={
            'name': 'Enhanced RAG Admission API',
            'version': '2.0.0',
            'description': 'Advanced API for university admission RAG chatbot with enhanced features',
            'endpoints': endpoints,
            'new_features': [
                'Query enhancement and rewriting',
                'Dynamic prompting based on query types',
                'Context optimization and compression',
                'Confidence scoring for answers',
                'Performance monitoring and analytics'
            ]
        }
    )


@api_bp.route('/rag/stats', methods=['GET'])
@admin_required
def get_rag_statistics():
    """Get RAG system performance statistics (admin only)"""
    try:
        stats = enhanced_rag.get_statistics()
        
        return format_response(
            success=True,
            data={
                'rag_statistics': stats,
                'description': 'Enhanced RAG system performance metrics'
            }
        )
        
    except Exception as e:
        return format_response(
            success=False,
            error=f'Failed to get RAG statistics: {str(e)}',
            status_code=500
        )


@api_bp.route('/rag/reset-stats', methods=['POST'])
@admin_required
def reset_rag_statistics():
    """Reset RAG system statistics (admin only)"""
    try:
        enhanced_rag.reset_statistics()
        
        return format_response(
            success=True,
            data={'message': 'RAG statistics reset successfully'}
        )
        
    except Exception as e:
        return format_response(
            success=False,
            error=f'Failed to reset RAG statistics: {str(e)}',
            status_code=500
        )