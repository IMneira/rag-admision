"""
Enhanced Query Engine for Advanced RAG
Integrates all improvements: query enhancement, context optimization, dynamic prompting, and confidence scoring.
"""

import time
import logging
from typing import Dict, List, Tuple, Optional
from dataclasses import dataclass
from langchain_chroma import Chroma
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain.schema.document import Document

from app.services.rag.embedding import get_embedding
from app.services.rag.query_enhancement import QueryEnhancer, QueryType
from app.services.rag.context_optimizer import ContextOptimizer
from app.services.rag.dynamic_prompting import DynamicPromptGenerator, PromptStrategy
from app.services.rag.confidence_scorer import ConfidenceScorer, ConfidenceScore
from config import Config


@dataclass
class EnhancedRAGResponse:
    """Enhanced response object with additional metadata"""
    answer: str
    sources: List[str]
    confidence: ConfidenceScore
    query_analysis: Dict
    processing_time: float
    context_summary: Dict
    recommendations: List[str]


class EnhancedQueryEngine:
    def __init__(self, chroma_path: str = "chroma"):
        self.chroma_path = chroma_path
        self.embedding_function = get_embedding()
        
        # Initialize all components
        self.query_enhancer = QueryEnhancer()
        self.context_optimizer = ContextOptimizer()
        self.prompt_generator = DynamicPromptGenerator()
        self.confidence_scorer = ConfidenceScorer()
        
        # Initialize LLM
        self.llm = ChatGoogleGenerativeAI(
            model="gemini-2.5-flash",
            google_api_key=Config.API_KEY,
            temperature=0.2
        )
        
        # Initialize vector database
        self.db = Chroma(
            persist_directory=self.chroma_path,
            embedding_function=self.embedding_function
        )
        
        # Performance tracking
        self.query_stats = {
            'total_queries': 0,
            'avg_processing_time': 0.0,
            'confidence_distribution': {'high': 0, 'medium': 0, 'low': 0, 'very_low': 0}
        }
        
        logging.info("Enhanced Query Engine initialized successfully")

    def query(self, query_text: str, enable_confidence_scoring: bool = True,
              max_context_tokens: int = 3000) -> EnhancedRAGResponse:
        """
        Process a query using the enhanced RAG pipeline
        
        Args:
            query_text: User's question
            enable_confidence_scoring: Whether to calculate confidence scores
            max_context_tokens: Maximum tokens for context (for compression)
        """
        start_time = time.time()
        
        try:
            # Step 1: Query Enhancement and Analysis
            logging.info(f"Processing query: {query_text}")
            query_analysis = self.query_enhancer.enhance_query(query_text)
            
            # Step 2: Multi-Query Retrieval
            retrieved_docs, similarity_scores = self._multi_query_retrieval(query_analysis)
            
            # Step 3: Context Optimization
            optimized_context = self._optimize_context(
                retrieved_docs, query_text, query_analysis['query_type'], max_context_tokens
            )
            
            # Step 4: Dynamic Prompt Generation
            prompt = self._generate_dynamic_prompt(
                query_text, optimized_context, query_analysis
            )
            
            # Step 5: Answer Generation
            answer = self._generate_answer(prompt)
            
            # Step 6: Confidence Scoring
            confidence = None
            if enable_confidence_scoring:
                confidence = self._calculate_confidence(
                    query_text, answer, optimized_context, retrieved_docs, similarity_scores
                )
            
            # Step 7: Extract Sources
            sources = self._extract_sources(retrieved_docs)
            
            # Step 8: Generate Recommendations
            recommendations = self._generate_recommendations(query_analysis, confidence)
            
            # Step 9: Create Response
            processing_time = time.time() - start_time
            context_summary = self.context_optimizer.get_context_summary(retrieved_docs)
            
            response = EnhancedRAGResponse(
                answer=answer,
                sources=sources,
                confidence=confidence,
                query_analysis=query_analysis,
                processing_time=processing_time,
                context_summary=context_summary,
                recommendations=recommendations
            )
            
            # Update statistics
            self._update_stats(response)
            
            logging.info(f"Query processed successfully in {processing_time:.2f}s")
            return response
            
        except Exception as e:
            logging.error(f"Error processing query: {e}")
            # Return fallback response
            return self._create_fallback_response(query_text, str(e), time.time() - start_time)

    def _multi_query_retrieval(self, query_analysis: Dict) -> Tuple[List[Document], List[float]]:
        """Retrieve documents using multiple query variations"""
        all_queries = query_analysis['all_queries']
        optimal_k = self.query_enhancer.get_optimal_k(query_analysis['complexity_score'])
        
        # Collect all unique documents
        all_docs = []
        all_scores = []
        seen_ids = set()
        
        for query_variant in all_queries[:3]:  # Limit to 3 variants to control latency
            try:
                docs_with_scores = self.db.similarity_search_with_score(query_variant, k=optimal_k)
                
                for doc, score in docs_with_scores:
                    doc_id = doc.metadata.get('id', '')
                    if doc_id not in seen_ids:
                        all_docs.append(doc)
                        all_scores.append(score)
                        seen_ids.add(doc_id)
                        
            except Exception as e:
                logging.warning(f"Error in retrieval for query variant '{query_variant}': {e}")
                continue
        
        # Add neighbor expansion for top documents
        if all_docs:
            expanded_docs = self._expand_with_neighbors(all_docs[:optimal_k])
            all_docs.extend(expanded_docs)
        
        return all_docs, all_scores

    def _expand_with_neighbors(self, core_docs: List[Document]) -> List[Document]:
        """Expand with neighboring chunks for better context"""
        neighbor_ids = []
        for doc in core_docs:
            doc_id = doc.metadata.get('id', '')
            if doc_id:
                neighbors = self._get_neighbor_ids(doc_id)
                neighbor_ids.extend(neighbors)
        
        # Remove duplicates and get neighbor documents
        unique_neighbor_ids = list(set(neighbor_ids))
        if unique_neighbor_ids:
            try:
                extra_docs_raw = self.db.get(ids=unique_neighbor_ids)
                neighbor_docs = [
                    Document(page_content=content, metadata={"id": doc_id})
                    for content, doc_id in zip(extra_docs_raw["documents"], extra_docs_raw["ids"])
                ]
                return neighbor_docs
            except Exception as e:
                logging.warning(f"Error expanding with neighbors: {e}")
        
        return []

    def _get_neighbor_ids(self, chunk_id: str) -> List[str]:
        """Get neighboring chunk IDs"""
        try:
            *base, idx = chunk_id.split(":")
            base = ":".join(base)
            i = int(idx)
            return [f"{base}:{i-1}", f"{base}:{i+1}"]
        except (ValueError, IndexError):
            return []

    def _optimize_context(self, docs: List[Document], query: str, 
                         query_type: str, max_tokens: int) -> str:
        """Optimize context using compression and ranking"""
        if not docs:
            return ""
        
        # Use context optimizer to compress and rank
        compressed_context = self.context_optimizer.compress_context(
            docs, query, max_tokens
        )
        
        return compressed_context

    def _generate_dynamic_prompt(self, query: str, context: str, query_analysis: Dict) -> str:
        """Generate dynamic prompt based on query analysis"""
        query_type = QueryType(query_analysis['query_type'])
        complexity_score = query_analysis['complexity_score']
        
        # Determine optimal prompting strategy
        strategy = self.prompt_generator.get_optimal_strategy(query_type, complexity_score)
        
        # Generate prompt with confidence scoring enabled
        prompt = self.prompt_generator.generate_prompt(
            query=query,
            context=context,
            query_type=query_type,
            strategy=strategy,
            confidence_needed=True
        )
        
        return prompt

    def _generate_answer(self, prompt: str) -> str:
        """Generate answer using the LLM"""
        try:
            response = self.llm.invoke(prompt)
            
            if hasattr(response, "content"):
                return response.content
            else:
                return str(response)
                
        except Exception as e:
            logging.error(f"Error generating answer: {e}")
            return "Lo siento, no pude generar una respuesta en este momento. Por favor, intenta reformular tu pregunta."

    def _calculate_confidence(self, query: str, answer: str, context: str,
                            docs: List[Document], scores: List[float]) -> ConfidenceScore:
        """Calculate confidence score for the answer"""
        try:
            return self.confidence_scorer.calculate_confidence(
                question=query,
                answer=answer,
                context=context,
                retrieved_docs=docs,
                similarity_scores=scores
            )
        except Exception as e:
            logging.warning(f"Error calculating confidence: {e}")
            # Return default low confidence
            from app.services.rag.confidence_scorer import ConfidenceLevel
            return ConfidenceScore(
                overall_score=0.3,
                level=ConfidenceLevel.LOW,
                factors={},
                explanation="No se pudo calcular la confianza debido a un error técnico.",
                recommendations=["Verifica la información con fuentes oficiales."]
            )

    def _extract_sources(self, docs: List[Document]) -> List[str]:
        """Extract source information from documents"""
        sources = []
        for doc in docs:
            doc_id = doc.metadata.get('id', '')
            if doc_id:
                sources.append(doc_id)
        
        return list(set(sources))  # Remove duplicates

    def _generate_recommendations(self, query_analysis: Dict, 
                                confidence: Optional[ConfidenceScore]) -> List[str]:
        """Generate recommendations based on query and confidence"""
        recommendations = []
        
        # Query-based recommendations
        query_type = query_analysis.get('query_type', 'general')
        complexity = query_analysis.get('complexity_score', 0.5)
        
        if query_type == 'procedural' and complexity > 0.7:
            recommendations.append("Para procesos complejos, considera contactar directamente con la oficina de admisiones")
        
        if query_type == 'temporal':
            recommendations.append("Verifica las fechas en el sitio web oficial, ya que pueden cambiar cada año")
        
        # Confidence-based recommendations
        if confidence and confidence.recommendations:
            recommendations.extend(confidence.recommendations)
        
        # Default recommendations
        if not recommendations:
            recommendations = [
                "Para información más detallada, consulta el sitio web oficial",
                "Si tienes dudas específicas, contacta con la oficina de admisiones"
            ]
        
        return recommendations[:3]  # Limit to 3 recommendations

    def _update_stats(self, response: EnhancedRAGResponse):
        """Update query statistics"""
        self.query_stats['total_queries'] += 1
        
        # Update average processing time
        total_time = (self.query_stats['avg_processing_time'] * 
                     (self.query_stats['total_queries'] - 1) + response.processing_time)
        self.query_stats['avg_processing_time'] = total_time / self.query_stats['total_queries']
        
        # Update confidence distribution
        if response.confidence:
            level = response.confidence.level.value
            if level in self.query_stats['confidence_distribution']:
                self.query_stats['confidence_distribution'][level] += 1

    def _create_fallback_response(self, query: str, error: str, 
                                processing_time: float) -> EnhancedRAGResponse:
        """Create fallback response when main processing fails"""
        from app.services.rag.confidence_scorer import ConfidenceScore, ConfidenceLevel
        
        fallback_confidence = ConfidenceScore(
            overall_score=0.1,
            level=ConfidenceLevel.VERY_LOW,
            factors={},
            explanation=f"Error en el procesamiento: {error}",
            recommendations=["Intenta reformular la pregunta", "Contacta con soporte técnico"]
        )
        
        return EnhancedRAGResponse(
            answer="Lo siento, hubo un error procesando tu consulta. Por favor, intenta con una pregunta diferente.",
            sources=[],
            confidence=fallback_confidence,
            query_analysis={'original_query': query, 'query_type': 'general', 'complexity_score': 0.5},
            processing_time=processing_time,
            context_summary={'total_docs': 0, 'total_chars': 0},
            recommendations=["Intenta reformular la pregunta", "Verifica tu conexión"]
        )

    def get_statistics(self) -> Dict:
        """Get query processing statistics"""
        return self.query_stats.copy()

    def reset_statistics(self):
        """Reset query statistics"""
        self.query_stats = {
            'total_queries': 0,
            'avg_processing_time': 0.0,
            'confidence_distribution': {'high': 0, 'medium': 0, 'low': 0, 'very_low': 0}
        }


def test_enhanced_query_engine():
    """Test the enhanced query engine"""
    engine = EnhancedQueryEngine()
    
    test_queries = [
        "¿Cuáles son los requisitos de admisión?",
        "¿Cómo puedo postular a la universidad?",
        "¿Cuándo son las fechas de postulación para 2024?",
        "¿Cuál es la diferencia entre PSU y PAES?"
    ]
    
    for query in test_queries:
        print(f"\n{'='*60}")
        print(f"Query: {query}")
        
        response = engine.query(query)
        
        print(f"Answer: {response.answer}")
        print(f"Processing time: {response.processing_time:.3f}s")
        print(f"Query type: {response.query_analysis.get('query_type', 'unknown')}")
        print(f"Complexity: {response.query_analysis.get('complexity_score', 0):.2f}")
        
        if response.confidence:
            print(f"Confidence: {response.confidence.level.value} ({response.confidence.overall_score:.3f})")
        
        print(f"Sources: {len(response.sources)} documents")
        print(f"Context summary: {response.context_summary}")
        print(f"Recommendations: {response.recommendations}")
    
    print(f"\n{'='*60}")
    print("Statistics:")
    stats = engine.get_statistics()
    for key, value in stats.items():
        print(f"{key}: {value}")


if __name__ == "__main__":
    test_enhanced_query_engine()