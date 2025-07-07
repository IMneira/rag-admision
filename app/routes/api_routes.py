from flask import Blueprint, request, jsonify
from flask_login import current_user
from app.services.rag.enhanced_query_engine import EnhancedQueryEngine
from app.models import Conversation, Message, User
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
from langchain_chroma import Chroma
from app.services.rag.embedding import get_embedding
from app.services.rag.hybrid_search import BM25KeywordSearcher

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
        for hash_id in doc_hashes:
            url = url_index.get(hash_id)
            if url and url not in source_urls:
                source_urls.append(url)
        
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
        },
        {
            'path': '/api/database/health',
            'method': 'GET',
            'description': 'Get comprehensive database health check (admin only)'
        },
        {
            'path': '/api/database/pdf-count',
            'method': 'GET',
            'description': 'Get detailed PDF document count and statistics (admin only)'
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
                'Progressive conversation summarization',
                'Database health monitoring',
                'PDF document count and statistics'
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


def get_database_statistics():
    """Get comprehensive database statistics"""
    stats = {
        'sqlite': {'status': 'unknown', 'error': None},
        'vector_db': {'status': 'unknown', 'error': None},
        'bm25_index': {'status': 'unknown', 'error': None},
        'file_system': {'status': 'unknown', 'error': None}
    }
    
    # SQLite database stats
    try:
        conversation_count = Conversation.query.count()
        message_count = Message.query.count()
        user_count = User.query.count()
        admin_count = User.query.filter_by(role='admin').count()
        
        stats['sqlite'] = {
            'status': 'healthy',
            'conversations': conversation_count,
            'messages': message_count,
            'users': user_count,
            'admins': admin_count,
            'tables': ['conversations', 'messages', 'users'],
            'connection': 'active'
        }
    except Exception as e:
        stats['sqlite'] = {
            'status': 'error',
            'error': str(e)
        }
    
    # Vector database (Chroma) stats
    try:
        chroma_path = "chroma"
        if os.path.exists(chroma_path):
            db_conn = Chroma(
                persist_directory=chroma_path,
                embedding_function=get_embedding()
            )
            
            # Get all items to count
            all_items = db_conn.get(include=["metadatas"])
            total_chunks = len(all_items.get("ids", []))
            
            # Count unique documents
            unique_sources = set()
            pdf_count = 0
            uploaded_count = 0
            
            for metadata in all_items.get("metadatas", []):
                if metadata and "source" in metadata:
                    source = metadata["source"]
                    unique_sources.add(source)
                    
                    # Count PDFs (look for .pdf in source or "uploaded:" prefix)
                    if source.lower().endswith('.pdf') or 'uploaded:' in source.lower():
                        pdf_count += 1
                        if 'uploaded:' in source.lower():
                            uploaded_count += 1
            
            stats['vector_db'] = {
                'status': 'healthy',
                'total_chunks': total_chunks,
                'unique_documents': len(unique_sources),
                'pdf_documents': pdf_count,
                'uploaded_documents': uploaded_count,
                'database_path': chroma_path,
                'embedding_model': 'paraphrase-multilingual-mpnet-base-v2'
            }
        else:
            stats['vector_db'] = {
                'status': 'missing',
                'error': 'Chroma database directory not found'
            }
    except Exception as e:
        stats['vector_db'] = {
            'status': 'error',
            'error': str(e)
        }
    
    # BM25 index stats
    try:
        bm25_path = "bm25_index"
        index_file = os.path.join(bm25_path, "bm25_index.pkl")
        
        if os.path.exists(index_file):
            # Try to load BM25 searcher to get stats
            bm25_searcher = BM25KeywordSearcher(bm25_path)
            
            stats['bm25_index'] = {
                'status': 'healthy',
                'index_path': bm25_path,
                'index_file_exists': True,
                'file_size_mb': round(os.path.getsize(index_file) / (1024*1024), 2)
            }
        else:
            stats['bm25_index'] = {
                'status': 'missing',
                'error': 'BM25 index file not found'
            }
    except Exception as e:
        stats['bm25_index'] = {
            'status': 'error',
            'error': str(e)
        }
    
    # File system stats
    try:
        data_path = "data"
        if os.path.exists(data_path):
            data_files = os.listdir(data_path)
            md_files = [f for f in data_files if f.endswith('.md')]
            
            # Check URL index
            url_index_path = os.path.join(data_path, 'url_index.json')
            url_index_exists = os.path.exists(url_index_path)
            
            total_size = 0
            for file in data_files:
                file_path = os.path.join(data_path, file)
                if os.path.isfile(file_path):
                    total_size += os.path.getsize(file_path)
            
            stats['file_system'] = {
                'status': 'healthy',
                'data_directory': data_path,
                'total_files': len(data_files),
                'markdown_files': len(md_files),
                'url_index_exists': url_index_exists,
                'total_size_mb': round(total_size / (1024*1024), 2)
            }
        else:
            stats['file_system'] = {
                'status': 'missing',
                'error': 'Data directory not found'
            }
    except Exception as e:
        stats['file_system'] = {
            'status': 'error',
            'error': str(e)
        }
    
    return stats


def get_pdf_count_details():
    """Get detailed PDF document count and metadata"""
    pdf_stats = {
        'total_pdfs': 0,
        'uploaded_pdfs': 0,
        'scraped_pdfs': 0,
        'pdf_sources': [],
        'processing_status': {'success': 0, 'failed': 0},
        'recent_additions': {'last_24h': 0, 'last_week': 0}
    }
    
    try:
        chroma_path = "chroma"
        if not os.path.exists(chroma_path):
            return pdf_stats
            
        db_conn = Chroma(
            persist_directory=chroma_path,
            embedding_function=get_embedding()
        )
        
        # Get all items with metadata
        all_items = db_conn.get(include=["metadatas"])
        
        # Load URL index for source mapping
        url_index_path = os.path.join("data", "url_index.json")
        url_index = {}
        if os.path.exists(url_index_path):
            with open(url_index_path, 'r', encoding='utf-8') as f:
                url_index = json.load(f)
        
        # Track unique PDF sources
        pdf_sources = set()
        
        for metadata in all_items.get("metadatas", []):
            if not metadata or "source" not in metadata:
                continue
                
            source = metadata["source"]
            
            # Check if this is a PDF document
            is_pdf = False
            source_type = "unknown"
            
            # Extract document hash from source
            if '/' in source:
                doc_hash = source.split('/')[1].split('.')[0]
            else:
                doc_hash = source.split(':')[0] if ':' in source else source
            
            # Check URL index for original source
            original_url = url_index.get(doc_hash, source)
            
            if (source.lower().endswith('.pdf') or 
                'uploaded:' in source.lower() or 
                original_url.lower().endswith('.pdf')):
                is_pdf = True
                pdf_sources.add(doc_hash)
                
                if 'uploaded:' in source.lower():
                    source_type = "uploaded"
                    pdf_stats['uploaded_pdfs'] += 1
                else:
                    source_type = "scraped"
                    pdf_stats['scraped_pdfs'] += 1
        
        pdf_stats['total_pdfs'] = len(pdf_sources)
        
        # Get detailed source information
        for doc_hash in pdf_sources:
            original_url = url_index.get(doc_hash, doc_hash)
            pdf_stats['pdf_sources'].append({
                'document_hash': doc_hash,
                'original_source': original_url,
                'type': 'uploaded' if 'uploaded:' in original_url else 'scraped'
            })
        
        # Count successful processing (if document exists in vector DB, it was processed successfully)
        pdf_stats['processing_status']['success'] = len(pdf_sources)
        
        # Get recent additions (check file modification times in data directory)
        data_path = "data"
        if os.path.exists(data_path):
            now = datetime.utcnow()
            
            for doc_hash in pdf_sources:
                file_path = os.path.join(data_path, f"{doc_hash}.md")
                if os.path.exists(file_path):
                    file_mtime = datetime.fromtimestamp(os.path.getmtime(file_path))
                    time_diff = now - file_mtime
                    
                    if time_diff.days < 1:
                        pdf_stats['recent_additions']['last_24h'] += 1
                    if time_diff.days < 7:
                        pdf_stats['recent_additions']['last_week'] += 1
        
    except Exception as e:
        pdf_stats['error'] = str(e)
    
    return pdf_stats


@api_bp.route('/database/health', methods=['GET'])
@admin_required
def database_health():
    """Comprehensive database health check endpoint"""
    try:
        stats = get_database_statistics()
        
        # Determine overall health status
        overall_status = "healthy"
        error_count = 0
        
        for system, data in stats.items():
            if data.get('status') == 'error':
                overall_status = "error"
                error_count += 1
            elif data.get('status') == 'missing':
                overall_status = "warning" if overall_status == "healthy" else overall_status
        
        return format_response(
            success=True,
            data={
                'overall_status': overall_status,
                'error_count': error_count,
                'systems': stats,
                'summary': {
                    'sqlite_healthy': stats['sqlite']['status'] == 'healthy',
                    'vector_db_healthy': stats['vector_db']['status'] == 'healthy',
                    'bm25_healthy': stats['bm25_index']['status'] == 'healthy',
                    'file_system_healthy': stats['file_system']['status'] == 'healthy'
                }
            }
        )
        
    except Exception as e:
        return format_response(
            success=False,
            error=f'Failed to get database health: {str(e)}',
            status_code=500
        )


@api_bp.route('/database/pdf-count', methods=['GET'])
@admin_required
def pdf_count():
    """Get detailed PDF document count and statistics"""
    try:
        pdf_stats = get_pdf_count_details()
        
        return format_response(
            success=True,
            data={
                'pdf_statistics': pdf_stats,
                'summary': {
                    'total_pdfs': pdf_stats['total_pdfs'],
                    'uploaded_vs_scraped': {
                        'uploaded': pdf_stats['uploaded_pdfs'],
                        'scraped': pdf_stats['scraped_pdfs']
                    },
                    'recent_activity': pdf_stats['recent_additions']
                }
            }
        )
        
    except Exception as e:
        return format_response(
            success=False,
            error=f'Failed to get PDF count: {str(e)}',
            status_code=500
        )