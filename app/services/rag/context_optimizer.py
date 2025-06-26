"""
Context Optimization Module for Advanced RAG
Provides context compression, ranking, and deduplication for better prompt efficiency.
"""

import re
import logging
from typing import List, Dict, Tuple, Set
from collections import Counter
from langchain.schema.document import Document
from langchain_google_genai import ChatGoogleGenerativeAI
from config import Config


class ContextOptimizer:
    def __init__(self):
        self.llm = ChatGoogleGenerativeAI(
            model="gemini-2.5-flash",
            google_api_key=Config.API_KEY,
            temperature=0.1
        )
        
        # Common redundant patterns in Spanish
        self.redundant_patterns = [
            r'Para más información.*',
            r'Si tiene dudas.*',
            r'Contacte con.*',
            r'Para mayor detalle.*',
            r'Según el reglamento.*',
            r'De acuerdo con.*',
            r'En el caso de que.*'
        ]
        
        # Header collapse patterns
        self.header_patterns = [
            r'§§DOC_HEADER§§\s*',
            r'===.*===',
            r'---.*---',
            r'#{1,6}\s*'
        ]

    def remove_redundancy(self, documents: List[Document]) -> List[Document]:
        """Remove redundant and duplicate content from documents"""
        seen_content = set()
        seen_sentences = set()
        optimized_docs = []
        
        for doc in documents:
            content = doc.page_content
            
            # Skip if we've seen this exact content
            content_hash = hash(content)
            if content_hash in seen_content:
                continue
            seen_content.add(content_hash)
            
            # Remove redundant patterns
            for pattern in self.redundant_patterns:
                content = re.sub(pattern, '', content, flags=re.IGNORECASE)
            
            # Sentence-level deduplication
            sentences = self._split_into_sentences(content)
            unique_sentences = []
            
            for sentence in sentences:
                sentence_clean = self._normalize_sentence(sentence)
                if sentence_clean and sentence_clean not in seen_sentences:
                    unique_sentences.append(sentence)
                    seen_sentences.add(sentence_clean)
            
            if unique_sentences:
                optimized_content = ' '.join(unique_sentences).strip()
                if optimized_content:
                    optimized_doc = Document(
                        page_content=optimized_content,
                        metadata=doc.metadata
                    )
                    optimized_docs.append(optimized_doc)
        
        return optimized_docs

    def rank_context_relevance(self, documents: List[Document], query: str, query_type: str) -> List[Tuple[Document, float]]:
        """Rank documents by relevance to the query"""
        ranked_docs = []
        
        for doc in documents:
            relevance_score = self._calculate_relevance_score(doc, query, query_type)
            ranked_docs.append((doc, relevance_score))
        
        # Sort by relevance score (descending)
        ranked_docs.sort(key=lambda x: x[1], reverse=True)
        return ranked_docs

    def compress_context(self, documents: List[Document], query: str, max_tokens: int = 3000) -> str:
        """Compress context while preserving most relevant information"""
        if not documents:
            return ""
        
        # Remove redundancy first
        optimized_docs = self.remove_redundancy(documents)
        
        # Rank by relevance
        ranked_docs = self.rank_context_relevance(optimized_docs, query, "general")
        
        # Build context within token limit
        context_parts = []
        current_tokens = 0
        
        for doc, relevance_score in ranked_docs:
            content = doc.page_content
            
            # Estimate tokens (rough approximation: 1 token ≈ 4 characters)
            content_tokens = len(content) // 4
            
            if current_tokens + content_tokens <= max_tokens:
                context_parts.append(content)
                current_tokens += content_tokens
            else:
                # Try to fit a compressed version
                remaining_tokens = max_tokens - current_tokens
                if remaining_tokens > 100:  # Only if we have reasonable space
                    compressed_content = self._compress_single_document(content, remaining_tokens * 4)
                    if compressed_content:
                        context_parts.append(compressed_content)
                break
        
        return self._format_compressed_context(context_parts)

    def _split_into_sentences(self, text: str) -> List[str]:
        """Split text into sentences"""
        # Simple sentence splitting for Spanish
        sentences = re.split(r'[.!?]+\s+', text)
        return [s.strip() for s in sentences if s.strip()]

    def _normalize_sentence(self, sentence: str) -> str:
        """Normalize sentence for comparison"""
        # Remove extra whitespace, punctuation, and convert to lowercase
        normalized = re.sub(r'\s+', ' ', sentence.lower())
        normalized = re.sub(r'[^\w\s]', '', normalized)
        return normalized.strip()

    def _calculate_relevance_score(self, doc: Document, query: str, query_type: str) -> float:
        """Calculate relevance score for a document"""
        content = doc.page_content.lower()
        query_lower = query.lower()
        
        score = 0.0
        
        # Exact phrase matching
        if query_lower in content:
            score += 2.0
        
        # Individual word matching
        query_words = query_lower.split()
        content_words = content.split()
        
        word_matches = sum(1 for word in query_words if word in content_words)
        score += (word_matches / len(query_words)) * 1.5
        
        # Document metadata boost
        source = doc.metadata.get('source', '').lower()
        if any(word in source for word in query_words):
            score += 0.5
        
        # Length penalty for very short docs
        if len(content) < 50:
            score *= 0.7
        
        # Boost for documents with structured content
        if any(pattern in content for pattern in ['1.', '2.', '•', '-', 'requisito', 'paso']):
            score += 0.3
        
        return score

    def _compress_single_document(self, content: str, max_chars: int) -> str:
        """Compress a single document to fit within character limit"""
        if len(content) <= max_chars:
            return content
        
        # Try to extract most important sentences
        sentences = self._split_into_sentences(content)
        if not sentences:
            return content[:max_chars] + "..."
        
        # Keep sentences that seem most important
        important_sentences = []
        current_chars = 0
        
        for sentence in sentences:
            # Prioritize sentences with key information
            importance_score = self._sentence_importance_score(sentence)
            sentence_chars = len(sentence)
            
            if importance_score > 0.5 and current_chars + sentence_chars <= max_chars:
                important_sentences.append(sentence)
                current_chars += sentence_chars
            elif current_chars == 0:  # Always include at least first sentence
                important_sentences.append(sentence[:max_chars-3] + "...")
                break
        
        return '. '.join(important_sentences) if important_sentences else content[:max_chars] + "..."

    def _sentence_importance_score(self, sentence: str) -> float:
        """Score sentence importance for compression"""
        sentence_lower = sentence.lower()
        
        # High importance keywords
        high_importance = ['requisito', 'fecha', 'plazo', 'documento', 'paso', 'proceso', 'admisión', 'postulación']
        medium_importance = ['universidad', 'estudiante', 'carrera', 'programa', 'nota', 'puntaje']
        
        score = 0.0
        
        for word in high_importance:
            if word in sentence_lower:
                score += 0.3
        
        for word in medium_importance:
            if word in sentence_lower:
                score += 0.1
        
        # Penalty for very short sentences
        if len(sentence) < 20:
            score *= 0.5
        
        # Boost for sentences with numbers/dates
        if re.search(r'\d+', sentence):
            score += 0.2
        
        return min(score, 1.0)

    def _format_compressed_context(self, context_parts: List[str]) -> str:
        """Format the compressed context with clear separations"""
        if not context_parts:
            return ""
        
        formatted_parts = []
        for i, part in enumerate(context_parts):
            # Clean up headers and redundant separators
            cleaned_part = self._clean_document_headers(part)
            if cleaned_part.strip():
                formatted_parts.append(cleaned_part.strip())
        
        return "\n\n---\n\n".join(formatted_parts)

    def _clean_document_headers(self, content: str) -> str:
        """Clean document headers and formatting artifacts"""
        # Remove header patterns
        for pattern in self.header_patterns:
            content = re.sub(pattern, '', content)
        
        # Remove excessive whitespace
        content = re.sub(r'\n\s*\n\s*\n', '\n\n', content)
        content = re.sub(r'^\s+|\s+$', '', content)
        
        return content

    def get_context_summary(self, documents: List[Document]) -> Dict:
        """Get summary statistics about the context"""
        if not documents:
            return {"total_docs": 0, "total_chars": 0, "total_tokens": 0}
        
        total_chars = sum(len(doc.page_content) for doc in documents)
        total_tokens = total_chars // 4  # Rough estimation
        
        return {
            "total_docs": len(documents),
            "total_chars": total_chars,
            "total_tokens": total_tokens,
            "avg_doc_length": total_chars / len(documents),
            "sources": list(set(doc.metadata.get('source', 'unknown') for doc in documents))
        }


def test_context_optimization():
    """Test the context optimization functionality"""
    optimizer = ContextOptimizer()
    
    # Test documents with redundant content
    test_docs = [
        Document(
            page_content="Los requisitos de admisión incluyen: notas de enseñanza media, puntaje PSU, y carta de recomendación. Para más información contacte con la oficina.",
            metadata={"source": "admision_1.md", "id": "test1"}
        ),
        Document(
            page_content="Para postular necesitas: notas de enseñanza media, puntaje PSU, y carta de recomendación. Si tiene dudas llame a admisiones.",
            metadata={"source": "admision_2.md", "id": "test2"}
        ),
        Document(
            page_content="El proceso de admisión requiere documentación específica. Los documentos necesarios son las notas del colegio y los resultados de la PSU.",
            metadata={"source": "proceso.md", "id": "test3"}
        )
    ]
    
    query = "¿Cuáles son los requisitos de admisión?"
    
    print("Original documents:")
    for i, doc in enumerate(test_docs):
        print(f"{i+1}. {doc.page_content}")
    
    print("\n" + "="*50)
    
    # Test redundancy removal
    optimized_docs = optimizer.remove_redundancy(test_docs)
    print(f"\nAfter redundancy removal: {len(optimized_docs)} docs")
    for i, doc in enumerate(optimized_docs):
        print(f"{i+1}. {doc.page_content}")
    
    # Test context compression
    compressed_context = optimizer.compress_context(test_docs, query, max_tokens=200)
    print(f"\nCompressed context:\n{compressed_context}")
    
    # Test context summary
    summary = optimizer.get_context_summary(test_docs)
    print(f"\nContext summary: {summary}")


if __name__ == "__main__":
    test_context_optimization()