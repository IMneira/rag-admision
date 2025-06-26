"""
Conversational Memory System for Enhanced RAG
Maintains conversation context across multiple turns and provides intelligent memory management.
"""

import logging
import time
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass
from enum import Enum

from app.services.rag.llm import get_llm_flash, get_llm_flash_lite
from langchain.schema.document import Document

from config import Config


class MemoryType(Enum):
    RECENT = "recent"           # Recent turns kept in full detail
    SUMMARIZED = "summarized"   # Older turns that have been summarized
    ARCHIVED = "archived"       # Very old turns kept for reference only


@dataclass
class ConversationTurn:
    """Represents a single question-answer turn in a conversation"""
    question: str
    answer: str
    sources: List[str]
    timestamp: datetime
    context_used: str = ""
    memory_type: MemoryType = MemoryType.RECENT
    turn_index: int = 0


@dataclass
class ConversationContext:
    """Complete conversation context for RAG queries"""
    conversation_id: str
    recent_turns: List[ConversationTurn]
    summary: str
    total_turns: int
    last_updated: datetime
    context_tokens: int = 0


class ConversationSummarizer:
    """Handles summarization of conversation history"""
    
    def __init__(self):
        self.llm = get_llm_flash()  # Use Gemini Flash for summarization
    
    def summarize_turns(self, turns: List[ConversationTurn], 
                       existing_summary: str = "") -> str:
        """
        Summarize a list of conversation turns into a concise summary
        
        Args:
            turns: List of conversation turns to summarize
            existing_summary: Previous summary to build upon
            
        Returns:
            Concise summary of the conversation topics and key information
        """
        if not turns:
            return existing_summary
        
        # Build turn history for summarization
        turn_history = []
        for turn in turns:
            turn_history.append(f"Usuario: {turn.question}")
            turn_history.append(f"Asistente: {turn.answer[:500]}...")  # Truncate long answers
        
        conversation_text = "\n".join(turn_history)
        
        prompt = f"""
Eres un resumidor especializado en conversaciones sobre admisiones universitarias.

TAREA: Crear un resumen conciso de la conversación que capture:
1. Los temas principales consultados
2. Información clave proporcionada
3. Contexto relevante para futuras preguntas

RESUMEN PREVIO: {existing_summary if existing_summary else "Ninguno"}

NUEVAS INTERACCIONES:
{conversation_text}

INSTRUCCIONES:
- Máximo 200 palabras
- Enfócate en temas y información de admisión universitaria
- Mantén los detalles importantes (fechas, requisitos, procesos)
- Si hay resumen previo, integra la nueva información coherentemente
- Usa lenguaje claro y estructurado

RESUMEN ACTUALIZADO:
"""
        
        try:
            response = self.llm.complete(prompt)
            summary = response.content if hasattr(response, 'content') else str(response)
            return summary.strip()
        except Exception as e:
            logging.error(f"Error generating conversation summary: {e}")
            # Fallback: simple concatenation
            topics = []
            for turn in turns:
                if "requisitos" in turn.question.lower():
                    topics.append("requisitos de admisión")
                elif "proceso" in turn.question.lower() or "postul" in turn.question.lower():
                    topics.append("proceso de postulación")
                elif "fecha" in turn.question.lower():
                    topics.append("fechas importantes")
            
            return f"Conversación sobre: {', '.join(set(topics))}"


class ContextBuilder:
    """Builds conversation context for RAG queries"""
    
    def __init__(self, max_context_tokens: int = 2000):
        self.max_context_tokens = max_context_tokens
    
    def build_context_string(self, context: ConversationContext, 
                           current_query: str) -> str:
        """
        Build a context string for the current query based on conversation history
        
        Args:
            context: Conversation context
            current_query: Current user query
            
        Returns:
            Formatted context string for RAG prompting
        """
        context_parts = []
        
        # Add conversation summary if available
        if context.summary:
            context_parts.append(f"RESUMEN DE CONVERSACIÓN PREVIA:\n{context.summary}\n")
        
        # Add recent turns
        if context.recent_turns:
            context_parts.append("INTERCAMBIOS RECIENTES:")
            for turn in context.recent_turns[-3:]:  # Last 3 turns
                context_parts.append(f"Usuario: {turn.question}")
                context_parts.append(f"Asistente: {turn.answer[:300]}...\n")
        
        # Add current query
        context_parts.append(f"CONSULTA ACTUAL: {current_query}")
        
        context_string = "\n".join(context_parts)
        
        # Estimate tokens (rough approximation: 1 token ≈ 4 characters for Spanish)
        estimated_tokens = len(context_string) // 4
        
        # Truncate if too long
        if estimated_tokens > self.max_context_tokens:
            # Keep summary and current query, reduce recent turns
            if context.summary and context.recent_turns:
                context_parts = [
                    f"RESUMEN DE CONVERSACIÓN PREVIA:\n{context.summary}\n",
                    "ÚLTIMO INTERCAMBIO:",
                    f"Usuario: {context.recent_turns[-1].question}",
                    f"Asistente: {context.recent_turns[-1].answer[:200]}...\n",
                    f"CONSULTA ACTUAL: {current_query}"
                ]
                context_string = "\n".join(context_parts)
        
        return context_string
    
    def extract_references(self, query: str, context: ConversationContext) -> Dict[str, str]:
        """
        Extract pronoun and demonstrative references that might refer to conversation history
        
        Args:
            query: Current user query
            context: Conversation context
            
        Returns:
            Dictionary mapping references to their likely meanings
        """
        references = {}
        query_lower = query.lower()
        
        # Common reference patterns in Spanish
        reference_patterns = {
            "esto": "this",
            "eso": "that", 
            "aquello": "that (distant)",
            "el anterior": "the previous one",
            "la anterior": "the previous one",
            "lo anterior": "the previous thing",
            "lo mismo": "the same thing",
            "lo que mencionaste": "what you mentioned",
            "como dijiste": "as you said"
        }
        
        for pattern, meaning in reference_patterns.items():
            if pattern in query_lower and context.recent_turns:
                # Try to resolve reference from recent context
                last_turn = context.recent_turns[-1]
                if "requisitos" in last_turn.question.lower():
                    references[pattern] = "los requisitos de admisión mencionados anteriormente"
                elif "proceso" in last_turn.question.lower():
                    references[pattern] = "el proceso de postulación mencionado anteriormente"
                else:
                    references[pattern] = f"lo mencionado en la pregunta anterior sobre: {last_turn.question[:50]}..."
        
        return references


class MemoryManager:
    """Main conversation memory management system"""
    
    def __init__(self, max_recent_turns: int = 5, 
                 summarization_threshold: int = 10,
                 max_context_tokens: int = 2000):
        self.max_recent_turns = max_recent_turns
        self.summarization_threshold = summarization_threshold
        self.max_context_tokens = max_context_tokens
        
        self.summarizer = ConversationSummarizer()
        self.context_builder = ContextBuilder(max_context_tokens)
        
        # In-memory cache for conversation contexts
        self._context_cache: Dict[str, ConversationContext] = {}
        self._cache_timeout = timedelta(minutes=30)
    
    def load_conversation_context(self, conversation_id: str) -> ConversationContext:
        """
        Load conversation context from database or cache
        
        Args:
            conversation_id: ID of the conversation
            
        Returns:
            ConversationContext object with current conversation state
        """
        # Check cache first
        if conversation_id in self._context_cache:
            cached_context = self._context_cache[conversation_id]
            if datetime.now() - cached_context.last_updated < self._cache_timeout:
                return cached_context
        
        # Load from database
        try:
            from app.models import Conversation, Message
            
            conversation = Conversation.get_by_id(conversation_id)
            if not conversation:
                # Return empty context for new conversation
                return ConversationContext(
                    conversation_id=conversation_id,
                    recent_turns=[],
                    summary="",
                    total_turns=0,
                    last_updated=datetime.now()
                )
            
            # Load messages
            messages = Message.get_by_conversation(conversation_id)
            
            # Convert messages to conversation turns
            turns = []
            for i, message in enumerate(messages):
                turn = ConversationTurn(
                    question=message.question,
                    answer=message.response,
                    sources=message.get_sources(),
                    timestamp=message.timestamp,
                    turn_index=i
                )
                turns.append(turn)
            
            # Build context
            context = self._build_context_from_turns(conversation_id, turns)
            
            # Cache the context
            self._context_cache[conversation_id] = context
            
            return context
            
        except Exception as e:
            logging.error(f"Error loading conversation context: {e}")
            # Return empty context as fallback
            return ConversationContext(
                conversation_id=conversation_id,
                recent_turns=[],
                summary="",
                total_turns=0,
                last_updated=datetime.now()
            )
    
    def _build_context_from_turns(self, conversation_id: str, 
                                turns: List[ConversationTurn]) -> ConversationContext:
        """Build conversation context from a list of turns"""
        total_turns = len(turns)
        
        if total_turns == 0:
            return ConversationContext(
                conversation_id=conversation_id,
                recent_turns=[],
                summary="",
                total_turns=0,
                last_updated=datetime.now()
            )
        
        # Separate recent turns from older ones
        recent_turns = turns[-self.max_recent_turns:]
        older_turns = turns[:-self.max_recent_turns] if total_turns > self.max_recent_turns else []
        
        # Generate or load summary
        summary = ""
        if older_turns:
            # In a real implementation, this could be cached in the database
            summary = self.summarizer.summarize_turns(older_turns)
        
        return ConversationContext(
            conversation_id=conversation_id,
            recent_turns=recent_turns,
            summary=summary,
            total_turns=total_turns,
            last_updated=datetime.now()
        )
    
    def add_turn_to_context(self, conversation_id: str, question: str, 
                          answer: str, sources: List[str]) -> ConversationContext:
        """
        Add a new turn to the conversation context
        
        Args:
            conversation_id: ID of the conversation
            question: User question
            answer: Assistant answer
            sources: Source documents used
            
        Returns:
            Updated conversation context
        """
        # Load current context
        context = self.load_conversation_context(conversation_id)
        
        # Create new turn
        new_turn = ConversationTurn(
            question=question,
            answer=answer,
            sources=sources,
            timestamp=datetime.now(),
            turn_index=context.total_turns
        )
        
        # Add to recent turns
        context.recent_turns.append(new_turn)
        context.total_turns += 1
        context.last_updated = datetime.now()
        
        # Check if we need to summarize and manage memory
        if len(context.recent_turns) > self.max_recent_turns:
            # Move oldest recent turn to summary
            oldest_turn = context.recent_turns.pop(0)
            if context.summary:
                context.summary = self.summarizer.summarize_turns([oldest_turn], context.summary)
            else:
                context.summary = self.summarizer.summarize_turns([oldest_turn])
        
        # Update cache
        self._context_cache[conversation_id] = context
        
        return context
    
    def get_conversation_context_for_query(self, conversation_id: str, 
                                         current_query: str) -> str:
        """
        Get formatted conversation context for a RAG query
        
        Args:
            conversation_id: ID of the conversation
            current_query: Current user query
            
        Returns:
            Formatted context string for RAG prompting
        """
        if not conversation_id:
            return ""
        
        context = self.load_conversation_context(conversation_id)
        if context.total_turns == 0:
            return ""
        
        return self.context_builder.build_context_string(context, current_query)
    
    def detect_follow_up_question(self, query: str, context: ConversationContext) -> bool:
        """
        Detect if the current query is a follow-up question
        
        Args:
            query: Current user query
            context: Conversation context
            
        Returns:
            True if this appears to be a follow-up question
        """
        if not context.recent_turns:
            return False
        
        query_lower = query.lower()
        
        # Follow-up indicators in Spanish
        follow_up_indicators = [
            "y ", "también", "además", "otra pregunta", "algo más",
            "qué más", "cuál es", "cómo es", "dónde es", "cuándo es",
            "esto", "eso", "lo anterior", "lo mismo", "como dijiste",
            "mencionaste", "explicaste", "cuéntame más", "más detalles"
        ]
        
        for indicator in follow_up_indicators:
            if indicator in query_lower:
                return True
        
        # Check for pronouns and references
        references = self.context_builder.extract_references(query, context)
        if references:
            return True
        
        return False
    
    def clear_conversation_cache(self, conversation_id: str = None):
        """Clear conversation cache for specific ID or all"""
        if conversation_id:
            self._context_cache.pop(conversation_id, None)
        else:
            self._context_cache.clear()
    
    def get_memory_stats(self) -> Dict:
        """Get memory usage statistics"""
        return {
            'cached_conversations': len(self._context_cache),
            'max_recent_turns': self.max_recent_turns,
            'summarization_threshold': self.summarization_threshold,
            'max_context_tokens': self.max_context_tokens,
            'cache_timeout_minutes': self._cache_timeout.total_seconds() / 60
        }


def test_conversational_memory():
    """Test the conversational memory system"""
    print("Testing Conversational Memory System...")
    
    memory_manager = MemoryManager()
    
    # Test with a mock conversation
    conversation_id = "test_conv_001"
    
    # Simulate conversation turns
    turns = [
        ("¿Cuáles son los requisitos de admisión?", "Los requisitos incluyen PSU mínimo 450 puntos..."),
        ("¿Y cuándo es la postulación?", "La postulación se realiza entre diciembre y enero..."),
        ("¿Qué documentos necesito para esto?", "Para la postulación necesitas certificado de enseñanza media...")
    ]
    
    for question, answer in turns:
        context = memory_manager.add_turn_to_context(
            conversation_id, question, answer, ["doc1.md", "doc2.md"]
        )
        print(f"Added turn: {question[:50]}...")
        print(f"Total turns: {context.total_turns}")
    
    # Test context building
    current_query = "¿Hay algún otro requisito?"
    context_string = memory_manager.get_conversation_context_for_query(
        conversation_id, current_query
    )
    
    print("\n" + "="*60)
    print("CONVERSATION CONTEXT:")
    print(context_string)
    
    # Test follow-up detection
    is_followup = memory_manager.detect_follow_up_question(current_query, context)
    print(f"\nIs follow-up question: {is_followup}")
    
    # Test statistics
    stats = memory_manager.get_memory_stats()
    print("\nMemory Statistics:")
    for key, value in stats.items():
        print(f"{key}: {value}")


if __name__ == "__main__":
    test_conversational_memory()