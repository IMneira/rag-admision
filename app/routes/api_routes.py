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
from urllib.parse import urlparse, urlunparse

# URL normalization function
def normalize_url(url):
    parsed = urlparse(url.strip())
    scheme = 'https'  # Fuerza a https
    netloc = parsed.netloc.replace('www.', '')  # Quita www
    path = parsed.path.rstrip('/')
    return urlunparse((scheme, netloc, path, '', '', ''))

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
        source_url = normalize_url(source_url)
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

def extract_title_from_md(md_path):
    with open(md_path, 'r', encoding='utf-8') as f:
        for line in f:
            if line.strip().startswith('# '):
                return line.strip('# ').strip()
    return "Sin título"

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
        
        # Query Enhanced RAG system with conversational memory
        rag_response = enhanced_rag.query(
            query_text=question, 
            conversation_id=conversation_id,
            enable_confidence_scoring=True
        )
        
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
        seen_urls = set()
        for hash_id in doc_hashes:
            raw_url = url_index.get(hash_id)
            if raw_url:
                normalized_url = normalize_url(raw_url)
                if normalized_url not in seen_urls:
                    md_path = os.path.join('data', f'{hash_id}.md')
                    title = extract_title_from_md(md_path) if os.path.exists(md_path) else 'Sin título'
                    source_urls.append(f"url: {normalized_url}, title: {title}")
                    seen_urls.add(normalized_url)
        
        # Create and save message to database with conversational context
        message = Message.create_message(
            conversation_id=conversation_id,
            question=question,
            response=str(rag_response.answer),
            sources=source_urls,
            context_used=rag_response.conversation_context,
            is_follow_up=rag_response.is_follow_up,
            query_type=rag_response.query_analysis.get('query_type', 'general')
        )
        
        # Prepare enhanced response data with conversational memory
        response_data = {
            'conversation_id': conversation_id,
            'message': message.to_dict(),
            'enhanced_info': {
                'query_type': rag_response.query_analysis.get('query_type', 'general'),
                'complexity_score': rag_response.query_analysis.get('complexity_score', 0.5),
                'processing_time': round(rag_response.processing_time, 3),
                'context_summary': rag_response.context_summary,
                'recommendations': rag_response.recommendations,
                'is_follow_up': rag_response.is_follow_up,
                'conversation_context': rag_response.conversation_context
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
        },
        {
            'path': '/api/conversations/<id>/memory',
            'method': 'GET',
            'description': 'Get conversation memory context and summary'
        },
        {
            'path': '/api/conversations/<id>/memory',
            'method': 'DELETE',
            'description': 'Clear conversation memory cache'
        },
        {
            'path': '/api/memory/stats',
            'method': 'GET',
            'description': 'Get conversation memory system statistics (admin only)'
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
                'Performance monitoring and analytics',
                'Hybrid search (semantic + keyword)',
                'Conversational memory and context',
                'Follow-up question detection',
                'Reference resolution for pronouns',
                'Progressive conversation summarization'
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


@api_bp.route('/conversations/<conversation_id>/memory', methods=['GET'])
@login_required
def get_conversation_memory(conversation_id):
    """Get conversation memory context for a specific conversation"""
    try:
        # Verify user owns this conversation
        conversation = Conversation.get_by_id_and_user(conversation_id, current_user.id)
        if not conversation:
            return format_response(
                success=False,
                error='Conversation not found or access denied',
                status_code=404
            )
        
        # Load conversation context from memory manager
        memory_context = enhanced_rag.memory_manager.load_conversation_context(conversation_id)
        
        # Prepare response data
        memory_data = {
            'conversation_id': conversation_id,
            'total_turns': memory_context.total_turns,
            'recent_turns': len(memory_context.recent_turns),
            'has_summary': bool(memory_context.summary),
            'summary': memory_context.summary if memory_context.summary else None,
            'last_updated': memory_context.last_updated.isoformat(),
            'recent_questions': [
                {
                    'question': turn.question,
                    'timestamp': turn.timestamp.isoformat(),
                    'turn_index': turn.turn_index
                }
                for turn in memory_context.recent_turns[-3:]  # Last 3 questions
            ]
        }
        
        return format_response(
            success=True,
            data=memory_data
        )
        
    except Exception as e:
        return format_response(
            success=False,
            error=f'Failed to get conversation memory: {str(e)}',
            status_code=500
        )


@api_bp.route('/conversations/<conversation_id>/memory', methods=['DELETE'])
@login_required
def clear_conversation_memory(conversation_id):
    """Clear conversation memory cache for a specific conversation"""
    try:
        # Verify user owns this conversation
        conversation = Conversation.get_by_id_and_user(conversation_id, current_user.id)
        if not conversation:
            return format_response(
                success=False,
                error='Conversation not found or access denied',
                status_code=404
            )
        
        # Clear memory cache
        enhanced_rag.memory_manager.clear_conversation_cache(conversation_id)
        
        return format_response(
            success=True,
            data={'message': 'Conversation memory cache cleared successfully'}
        )
        
    except Exception as e:
        return format_response(
            success=False,
            error=f'Failed to clear conversation memory: {str(e)}',
            status_code=500
        )


@api_bp.route('/memory/stats', methods=['GET'])
@admin_required
def get_memory_statistics():
    """Get conversation memory system statistics (admin only)"""
    try:
        memory_stats = enhanced_rag.memory_manager.get_memory_stats()
        
        return format_response(
            success=True,
            data={
                'memory_statistics': memory_stats,
                'description': 'Conversational memory system performance metrics'
            }
        )
        
    except Exception as e:
        return format_response(
            success=False,
            error=f'Failed to get memory statistics: {str(e)}',
            status_code=500
        )