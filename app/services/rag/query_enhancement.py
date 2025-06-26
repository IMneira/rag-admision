"""
Query Enhancement Module for Advanced RAG
Provides query rewriting, expansion, and classification for better retrieval.
"""

import re
import logging
from typing import List, Dict, Tuple
from enum import Enum
from app.services.rag.llm import get_llm_flash, get_llm_flash_lite
from config import Config


class QueryType(Enum):
    FACTUAL = "factual"  # What is...?, Who is...?
    PROCEDURAL = "procedural"  # How to...?, What are the steps...?
    COMPARATIVE = "comparative"  # What's the difference...?, Compare...
    TEMPORAL = "temporal"  # When...?, What time...?
    LOCATION = "location"  # Where...?, Which location...?
    REQUIREMENT = "requirement"  # What do I need...?, Requirements for...
    GENERAL = "general"  # General questions


class QueryEnhancer:
    def __init__(self):
        self.llm = get_llm_flash()
        
        # Spanish question patterns for classification
        self.question_patterns = {
            QueryType.FACTUAL: [
                r'\b(?:qué es|qué son|quién es|quién son|cuál es|cuáles son)\b',
                r'\b(?:definición|concepto|significado)\b'
            ],
            QueryType.PROCEDURAL: [
                r'\b(?:cómo|como)\b.*\b(?:hacer|realizar|obtener|conseguir|solicitar)\b',
                r'\b(?:pasos|proceso|procedimiento)\b',
                r'\b(?:trámite|trámites)\b'
            ],
            QueryType.COMPARATIVE: [
                r'\b(?:diferencia|diferencias|comparar|comparación)\b',
                r'\b(?:mejor|peor|ventaja|desventaja)\b',
                r'\b(?:versus|vs|entre)\b'
            ],
            QueryType.TEMPORAL: [
                r'\b(?:cuándo|cuando|fecha|fechas|plazo|plazos)\b',
                r'\b(?:horario|horarios|tiempo)\b',
                r'\b(?:calendario|cronograma)\b'
            ],
            QueryType.LOCATION: [
                r'\b(?:dónde|donde|ubicación|lugar|dirección)\b',
                r'\b(?:campus|sede|oficina)\b'
            ],
            QueryType.REQUIREMENT: [
                r'\b(?:requisitos|requisito|requerimientos|requerimiento)\b',
                r'\b(?:necesito|necesito|necesitar)\b',
                r'\b(?:documentos|documentación)\b'
            ]
        }
        
        # Admission-specific synonyms and expansions
        self.domain_synonyms = {
            'admisión': ['ingreso', 'postulación', 'matrícula', 'inscripción'],
            'requisitos': ['requerimientos', 'condiciones', 'exigencias', 'documentos necesarios'],
            'universidad': ['institución', 'centro de estudios', 'casa de estudios'],
            'carrera': ['programa', 'especialidad', 'licenciatura', 'grado'],
            'estudiante': ['postulante', 'aspirante', 'alumno', 'candidato'],
            'prueba': ['examen', 'test', 'evaluación', 'puntaje'],
            'psu': ['paes', 'prueba de selección universitaria'],
            'nem': ['notas de enseñanza media'],
            'ranking': ['posición', 'orden de mérito']
        }

    def classify_query(self, query: str) -> QueryType:
        """Classify the query type based on patterns"""
        query_lower = query.lower()
        
        for query_type, patterns in self.question_patterns.items():
            for pattern in patterns:
                if re.search(pattern, query_lower):
                    return query_type
        
        return QueryType.GENERAL

    def expand_query_with_synonyms(self, query: str) -> List[str]:
        """Expand query with domain-specific synonyms"""
        expanded_queries = [query]
        query_lower = query.lower()
        
        for term, synonyms in self.domain_synonyms.items():
            if term in query_lower:
                for synonym in synonyms:
                    expanded_query = re.sub(
                        r'\b' + re.escape(term) + r'\b',
                        synonym,
                        query,
                        flags=re.IGNORECASE
                    )
                    if expanded_query != query and expanded_query not in expanded_queries:
                        expanded_queries.append(expanded_query)
        
        return expanded_queries[:3]  # Limit to 3 variations

    def rewrite_query_with_llm(self, query: str, query_type: QueryType) -> List[str]:
        """Use LLM to rewrite query for better retrieval"""
        
        type_specific_prompts = {
            QueryType.FACTUAL: "Reformula esta pregunta para buscar definiciones y conceptos específicos",
            QueryType.PROCEDURAL: "Reformula esta pregunta para buscar pasos y procedimientos",
            QueryType.COMPARATIVE: "Reformula esta pregunta para buscar comparaciones y diferencias",
            QueryType.TEMPORAL: "Reformula esta pregunta para buscar fechas y horarios",
            QueryType.LOCATION: "Reformula esta pregunta para buscar ubicaciones y lugares",
            QueryType.REQUIREMENT: "Reformula esta pregunta para buscar requisitos y documentos necesarios",
            QueryType.GENERAL: "Reformula esta pregunta para obtener mejor información"
        }
        
        prompt = f"""
{type_specific_prompts[query_type]} sobre admisión universitaria.

Pregunta original: "{query}"

Proporciona 2 reformulaciones diferentes de la pregunta que puedan recuperar mejor información de una base de datos de documentos universitarios. Las reformulaciones deben:
1. Ser más específicas y detalladas
2. Incluir términos relevantes para admisión universitaria
3. Mantener el mismo significado pero con diferentes palabras

Responde solo con las 2 reformulaciones, una por línea, sin numeración ni explicación:
"""
        
        try:
            response = self.llm.complete(prompt)
            if hasattr(response, "content"):
                response_text = response.content
            else:
                response_text = str(response)
            
            # Parse response into list
            rewrites = [line.strip() for line in response_text.split('\n') if line.strip()]
            return rewrites[:2]  # Limit to 2 rewrites
            
        except Exception as e:
            logging.warning(f"Query rewriting failed: {e}")
            return []

    def enhance_query(self, query: str) -> Dict:
        """Main method to enhance a query"""
        query_type = self.classify_query(query)
        
        # Get synonym expansions
        synonym_variants = self.expand_query_with_synonyms(query)
        
        # Get LLM rewrites
        llm_rewrites = self.rewrite_query_with_llm(query, query_type)
        
        # Calculate complexity score (affects k selection)
        complexity_score = self._calculate_complexity(query, query_type)
        
        return {
            'original_query': query,
            'query_type': query_type.value,
            'complexity_score': complexity_score,
            'synonym_variants': synonym_variants,
            'llm_rewrites': llm_rewrites,
            'all_queries': [query] + synonym_variants + llm_rewrites
        }

    def _calculate_complexity(self, query: str, query_type: QueryType) -> float:
        """Calculate query complexity score (0.0 to 1.0)"""
        score = 0.0
        
        # Base score by query type
        type_complexity = {
            QueryType.FACTUAL: 0.3,
            QueryType.PROCEDURAL: 0.7,
            QueryType.COMPARATIVE: 0.8,
            QueryType.TEMPORAL: 0.4,
            QueryType.LOCATION: 0.3,
            QueryType.REQUIREMENT: 0.6,
            QueryType.GENERAL: 0.5
        }
        score += type_complexity[query_type]
        
        # Length factor
        words = len(query.split())
        if words > 10:
            score += 0.2
        elif words > 6:
            score += 0.1
        
        # Complexity indicators
        complexity_words = ['comparar', 'diferencia', 'proceso', 'pasos', 'múltiple', 'varios', 'diferentes']
        for word in complexity_words:
            if word in query.lower():
                score += 0.1
                break
        
        # Question marks (multiple questions)
        question_marks = query.count('?')
        if question_marks > 1:
            score += 0.2
        
        return min(score, 1.0)

    def get_optimal_k(self, complexity_score: float) -> int:
        """Determine optimal number of chunks to retrieve based on complexity"""
        if complexity_score >= 0.8:
            return 8  # Complex queries need more context
        elif complexity_score >= 0.6:
            return 6  # Medium complexity
        elif complexity_score >= 0.4:
            return 4  # Simple queries
        else:
            return 3  # Very simple queries


def test_query_enhancement():
    """Test the query enhancement functionality"""
    enhancer = QueryEnhancer()
    
    test_queries = [
        "¿Cuáles son los requisitos de admisión?",
        "¿Cómo puedo postular a la universidad?",
        "¿Cuál es la diferencia entre PSU y PAES?",
        "¿Cuándo son las fechas de postulación?",
        "¿Dónde está ubicada la oficina de admisiones?"
    ]
    
    for query in test_queries:
        result = enhancer.enhance_query(query)
        print(f"\nQuery: {query}")
        print(f"Type: {result['query_type']}")
        print(f"Complexity: {result['complexity_score']:.2f}")
        print(f"Optimal k: {enhancer.get_optimal_k(result['complexity_score'])}")
        print(f"Variants: {result['synonym_variants']}")
        print(f"Rewrites: {result['llm_rewrites']}")


if __name__ == "__main__":
    test_query_enhancement()