"""
Query Logger for RAG System Debugging

This module provides comprehensive logging for the RAG query processing pipeline,
allowing developers to see the complete flow from user query to final LLM prompt.
Logging is only active in debug mode to avoid performance impact in production.
"""

import logging
import json
import time
import uuid
from typing import Dict, List, Any, Optional
from datetime import datetime
from config import Config

class QueryLogger:
    """Centralized logger for RAG query processing pipeline"""
    
    def __init__(self):
        self.logger = logging.getLogger('rag_query_debug')
        self.is_debug = getattr(Config, 'QUERY_DEBUG_LOGGING', getattr(Config, 'DEBUG', False))
        
        # Only set up detailed logging in debug mode
        if self.is_debug:
            self.logger.setLevel(logging.DEBUG)
            
            # Create formatter for detailed logging
            formatter = logging.Formatter(
                '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
            )
            
            # Add console handler if not already present
            if not self.logger.handlers:
                console_handler = logging.StreamHandler()
                console_handler.setFormatter(formatter)
                self.logger.addHandler(console_handler)
        else:
            # In production, set to WARNING level to minimize noise
            self.logger.setLevel(logging.WARNING)
    
    def start_query(self, query: str, query_type: str = "standard", user_id: str = None) -> str:
        """Start logging a new query session"""
        query_id = str(uuid.uuid4())[:8]
        
        if self.is_debug:
            self.logger.info(f"[{query_id}] === NEW QUERY SESSION ===")
            self.logger.info(f"[{query_id}] Query: {query}")
            self.logger.info(f"[{query_id}] Type: {query_type}")
            if user_id:
                self.logger.info(f"[{query_id}] User ID: {user_id}")
            self.logger.info(f"[{query_id}] Timestamp: {datetime.now().isoformat()}")
        
        return query_id
    
    def log_retrieval(self, query_id: str, retrieval_method: str, results_count: int, 
                      search_details: Dict = None):
        """Log document retrieval phase"""
        if self.is_debug:
            self.logger.info(f"[{query_id}] === DOCUMENT RETRIEVAL ===")
            self.logger.info(f"[{query_id}] Method: {retrieval_method}")
            self.logger.info(f"[{query_id}] Results count: {results_count}")
            
            if search_details:
                self.logger.debug(f"[{query_id}] Search details: {json.dumps(search_details, indent=2)}")
    
    def log_context_assembly(self, query_id: str, context_parts: List[Dict], 
                           total_context_length: int):
        """Log context assembly phase"""
        if self.is_debug:
            self.logger.info(f"[{query_id}] === CONTEXT ASSEMBLY ===")
            self.logger.info(f"[{query_id}] Context parts count: {len(context_parts)}")
            self.logger.info(f"[{query_id}] Total context length: {total_context_length} chars")
            
            # Log source summary
            sources = [part.get('source', 'unknown') for part in context_parts]
            self.logger.debug(f"[{query_id}] Sources: {sources}")
            
            # Log first few context parts for debugging
            for i, part in enumerate(context_parts[:3]):
                content_preview = part.get('content', '')[:100].replace('\n', ' ')
                self.logger.debug(f"[{query_id}] Context[{i}]: {content_preview}...")
    
    def log_prompt_construction(self, query_id: str, prompt_type: str, 
                               prompt_template: str = None, variables: Dict = None):
        """Log prompt construction phase"""
        if self.is_debug:
            self.logger.info(f"[{query_id}] === PROMPT CONSTRUCTION ===")
            self.logger.info(f"[{query_id}] Prompt type: {prompt_type}")
            
            if prompt_template:
                template_preview = prompt_template[:200].replace('\n', ' ')
                self.logger.debug(f"[{query_id}] Template preview: {template_preview}...")
            
            if variables:
                var_summary = {k: len(str(v)) if len(str(v)) > 100 else str(v) 
                              for k, v in variables.items()}
                self.logger.debug(f"[{query_id}] Template variables: {json.dumps(var_summary, indent=2)}")
    
    def log_final_prompt(self, query_id: str, final_prompt: str, context_summary: Dict = None):
        """Log the final prompt being sent to LLM (full content in debug mode)"""
        if self.is_debug:
            self.logger.info(f"[{query_id}] === FINAL LLM PROMPT ===")
            self.logger.info(f"[{query_id}] Prompt length: {len(final_prompt)} chars")
            
            # Log context summary if provided
            if context_summary:
                self.logger.info(f"[{query_id}] Context sources: {context_summary.get('source_count', 0)}")
                self.logger.info(f"[{query_id}] Context length: {context_summary.get('total_length', 0)} chars")
            
            # Log the complete prompt for debugging
            self.logger.debug(f"[{query_id}] === COMPLETE PROMPT ===")
            self.logger.debug(f"[{query_id}] {'-' * 80}")
            self.logger.debug(f"[{query_id}] {final_prompt}")
            self.logger.debug(f"[{query_id}] {'-' * 80}")
    
    def log_llm_response(self, query_id: str, response: str, processing_time: float = None):
        """Log LLM response details"""
        if self.is_debug:
            self.logger.info(f"[{query_id}] === LLM RESPONSE ===")
            self.logger.info(f"[{query_id}] Response length: {len(response)} chars")
            
            if processing_time:
                self.logger.info(f"[{query_id}] Processing time: {processing_time:.2f}s")
            
            # Log response preview
            response_preview = response[:200].replace('\n', ' ')
            self.logger.debug(f"[{query_id}] Response preview: {response_preview}...")
    
    def log_error(self, query_id: str, error: Exception, phase: str = "unknown"):
        """Log errors during query processing"""
        # Always log errors, regardless of debug mode
        self.logger.error(f"[{query_id}] ERROR in {phase}: {str(error)}")
        
        if self.is_debug:
            self.logger.debug(f"[{query_id}] Error details:", exc_info=True)
    
    def log_query_complete(self, query_id: str, total_time: float = None, 
                          final_response_length: int = None):
        """Mark query processing as complete"""
        if self.is_debug:
            self.logger.info(f"[{query_id}] === QUERY COMPLETE ===")
            
            if total_time:
                self.logger.info(f"[{query_id}] Total processing time: {total_time:.2f}s")
            
            if final_response_length:
                self.logger.info(f"[{query_id}] Final response length: {final_response_length} chars")
            
            self.logger.info(f"[{query_id}] {'=' * 50}")

# Global logger instance
query_logger = QueryLogger()

def get_query_logger() -> QueryLogger:
    """Get the global query logger instance"""
    return query_logger

def log_query_context(query_id: str, context: str, sources: List[str] = None):
    """Convenience function to log context with sources"""
    context_parts = []
    
    if sources:
        # Split context and associate with sources if available
        context_segments = context.split('\n\n')
        for i, segment in enumerate(context_segments):
            source = sources[i] if i < len(sources) else 'unknown'
            context_parts.append({
                'content': segment,
                'source': source
            })
    else:
        context_parts.append({
            'content': context,
            'source': 'combined'
        })
    
    query_logger.log_context_assembly(
        query_id, 
        context_parts, 
        len(context)
    )

def debug_query_flow(func):
    """Decorator to automatically log query processing functions"""
    def wrapper(*args, **kwargs):
        if query_logger.is_debug:
            func_name = func.__name__
            query_logger.logger.debug(f"Entering {func_name} with args: {len(args)}, kwargs: {list(kwargs.keys())}")
            
            start_time = time.time()
            try:
                result = func(*args, **kwargs)
                end_time = time.time()
                query_logger.logger.debug(f"Completed {func_name} in {end_time - start_time:.2f}s")
                return result
            except Exception as e:
                query_logger.logger.error(f"Error in {func_name}: {str(e)}")
                raise
        else:
            return func(*args, **kwargs)
    
    return wrapper