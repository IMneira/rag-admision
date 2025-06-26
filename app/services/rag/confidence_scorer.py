"""
Confidence Scoring System for Advanced RAG
Evaluates answer quality and reliability based on multiple factors.
"""

import re
import logging
from typing import Dict, List, Tuple, Optional
from dataclasses import dataclass
from enum import Enum
from langchain.schema.document import Document
from langchain_google_genai import ChatGoogleGenerativeAI
from config import Config


class ConfidenceLevel(Enum):
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"
    VERY_LOW = "very_low"


@dataclass
class ConfidenceScore:
    overall_score: float  # 0.0 to 1.0
    level: ConfidenceLevel
    factors: Dict[str, float]
    explanation: str
    recommendations: List[str]


class ConfidenceScorer:
    def __init__(self):
        self.llm = ChatGoogleGenerativeAI(
            model="gemini-2.5-flash",
            google_api_key=Config.API_KEY,
            temperature=0.1
        )
        
        # Indicators of high confidence answers
        self.high_confidence_indicators = [
            r'\d{1,2}/\d{1,2}/\d{4}',  # Specific dates
            r'\d+:\d+',  # Times
            r'paso \d+',  # Numbered steps
            r'requisito.*:',  # Listed requirements
            r'documento.*necesario',  # Required documents
            r'según.*reglamento',  # According to regulations
        ]
        
        # Indicators of uncertainty
        self.uncertainty_indicators = [
            r'puede.*ser',
            r'generalmente',
            r'usualmente',
            r'aproximadamente',
            r'alrededor de',
            r'es posible que',
            r'podría.*',
            r'tal vez',
            r'quizás'
        ]
        
        # Indicators of incomplete information
        self.incomplete_indicators = [
            r'no.*información.*disponible',
            r'consulta.*con',
            r'contacta.*para.*más',
            r'información.*adicional',
            r'depende.*de',
            r'varía.*según'
        ]

    def calculate_confidence(self, question: str, answer: str, context: str, 
                           retrieved_docs: List[Document], 
                           similarity_scores: List[float] = None) -> ConfidenceScore:
        """Calculate comprehensive confidence score for an answer"""
        
        factors = {}
        
        # 1. Context relevance (how well context matches question)
        factors['context_relevance'] = self._score_context_relevance(question, context)
        
        # 2. Answer completeness (how complete the answer appears)
        factors['answer_completeness'] = self._score_answer_completeness(question, answer)
        
        # 3. Source quality (quality and relevance of retrieved documents)
        factors['source_quality'] = self._score_source_quality(retrieved_docs, similarity_scores)
        
        # 4. Answer specificity (how specific vs general the answer is)
        factors['answer_specificity'] = self._score_answer_specificity(answer)
        
        # 5. Consistency check (internal consistency of the answer)
        factors['consistency'] = self._score_consistency(answer, context)
        
        # 6. Uncertainty indicators (presence of uncertain language)
        factors['certainty'] = self._score_certainty(answer)
        
        # 7. Information coverage (how much of the question is addressed)
        factors['coverage'] = self._score_information_coverage(question, answer)
        
        # Calculate weighted overall score
        weights = {
            'context_relevance': 0.20,
            'answer_completeness': 0.15,
            'source_quality': 0.15,
            'answer_specificity': 0.15,
            'consistency': 0.10,
            'certainty': 0.15,
            'coverage': 0.10
        }
        
        overall_score = sum(factors[factor] * weight for factor, weight in weights.items())
        
        # Determine confidence level
        level = self._determine_confidence_level(overall_score)
        
        # Generate explanation and recommendations
        explanation = self._generate_explanation(factors, overall_score)
        recommendations = self._generate_recommendations(factors, level)
        
        return ConfidenceScore(
            overall_score=overall_score,
            level=level,
            factors=factors,
            explanation=explanation,
            recommendations=recommendations
        )

    def _score_context_relevance(self, question: str, context: str) -> float:
        """Score how relevant the context is to the question"""
        question_words = set(re.findall(r'\w+', question.lower()))
        context_words = set(re.findall(r'\w+', context.lower()))
        
        if not question_words:
            return 0.0
        
        # Calculate word overlap
        overlap = len(question_words.intersection(context_words))
        relevance = overlap / len(question_words)
        
        # Boost for exact phrase matches
        question_lower = question.lower()
        context_lower = context.lower()
        
        if question_lower in context_lower:
            relevance += 0.3
        
        # Check for key admission terms
        admission_terms = ['requisito', 'admisión', 'postulación', 'psu', 'fecha', 'documento']
        for term in admission_terms:
            if term in question_lower and term in context_lower:
                relevance += 0.1
        
        return min(relevance, 1.0)

    def _score_answer_completeness(self, question: str, answer: str) -> float:
        """Score how complete the answer appears to be"""
        score = 0.0
        
        # Length factor (longer answers tend to be more complete for complex questions)
        answer_length = len(answer)
        if answer_length > 200:
            score += 0.3
        elif answer_length > 100:
            score += 0.2
        elif answer_length > 50:
            score += 0.1
        
        # Structure indicators (lists, steps, organization)
        if re.search(r'[1-9]\.|•|-|\n', answer):
            score += 0.2
        
        # Specific information (dates, numbers, names)
        if re.search(r'\d+', answer):
            score += 0.2
        
        # Addresses multiple aspects of question
        question_words = question.lower().split()
        if len(question_words) > 3:  # Complex question
            word_coverage = sum(1 for word in question_words if word in answer.lower())
            score += (word_coverage / len(question_words)) * 0.3
        
        return min(score, 1.0)

    def _score_source_quality(self, retrieved_docs: List[Document], 
                             similarity_scores: List[float] = None) -> float:
        """Score the quality of retrieved sources"""
        if not retrieved_docs:
            return 0.0
        
        score = 0.0
        
        # Number of sources (more sources generally better)
        num_docs = len(retrieved_docs)
        if num_docs >= 5:
            score += 0.3
        elif num_docs >= 3:
            score += 0.2
        elif num_docs >= 1:
            score += 0.1
        
        # Similarity scores (if available)
        if similarity_scores:
            avg_similarity = sum(similarity_scores) / len(similarity_scores)
            score += avg_similarity * 0.4
        
        # Source diversity (different documents/sources)
        sources = [doc.metadata.get('source', '') for doc in retrieved_docs]
        unique_sources = len(set(sources))
        diversity = unique_sources / max(num_docs, 1)
        score += diversity * 0.2
        
        # Content quality indicators
        total_content_length = sum(len(doc.page_content) for doc in retrieved_docs)
        if total_content_length > 1000:
            score += 0.1
        
        return min(score, 1.0)

    def _score_answer_specificity(self, answer: str) -> float:
        """Score how specific (vs general) the answer is"""
        score = 0.0
        
        # High specificity indicators
        for pattern in self.high_confidence_indicators:
            if re.search(pattern, answer, re.IGNORECASE):
                score += 0.15
        
        # Specific terms and phrases
        specific_terms = [
            'debe', 'obligatorio', 'necesario', 'requerido',
            'exactamente', 'específicamente', 'precisamente'
        ]
        
        for term in specific_terms:
            if term in answer.lower():
                score += 0.1
        
        # Penalty for vague language
        vague_terms = ['puede', 'tal vez', 'posiblemente', 'generalmente']
        for term in vague_terms:
            if term in answer.lower():
                score -= 0.1
        
        return max(min(score, 1.0), 0.0)

    def _score_consistency(self, answer: str, context: str) -> float:
        """Score internal consistency of the answer"""
        score = 1.0  # Start with high consistency
        
        # Check for contradictions (simplified)
        contradiction_patterns = [
            (r'sí.*no', r'no.*sí'),
            (r'necesario.*opcional', r'opcional.*necesario'),
            (r'obligatorio.*opcional', r'opcional.*obligatorio')
        ]
        
        answer_lower = answer.lower()
        for pattern1, pattern2 in contradiction_patterns:
            if re.search(pattern1, answer_lower) or re.search(pattern2, answer_lower):
                score -= 0.3
        
        # Check for factual consistency with context
        # Extract key facts from context and verify in answer
        context_numbers = re.findall(r'\d+', context)
        answer_numbers = re.findall(r'\d+', answer)
        
        # If answer has numbers not in context, might be inconsistent
        if answer_numbers and context_numbers:
            inconsistent_numbers = [num for num in answer_numbers if num not in context_numbers]
            if inconsistent_numbers:
                score -= 0.2
        
        return max(score, 0.0)

    def _score_certainty(self, answer: str) -> float:
        """Score based on certainty indicators in the answer"""
        score = 1.0  # Start with high certainty
        
        # Reduce score for uncertainty indicators
        answer_lower = answer.lower()
        for pattern in self.uncertainty_indicators:
            if re.search(pattern, answer_lower):
                score -= 0.2
        
        # Reduce score for incomplete information indicators
        for pattern in self.incomplete_indicators:
            if re.search(pattern, answer_lower):
                score -= 0.3
        
        return max(score, 0.0)

    def _score_information_coverage(self, question: str, answer: str) -> float:
        """Score how well the answer covers the question"""
        question_lower = question.lower()
        answer_lower = answer.lower()
        
        # Extract key question words (excluding stop words)
        stop_words = {'es', 'son', 'el', 'la', 'los', 'las', 'un', 'una', 'de', 'del', 'en', 'con', 'por', 'para'}
        question_words = [word for word in re.findall(r'\w+', question_lower) 
                         if word not in stop_words and len(word) > 2]
        
        if not question_words:
            return 0.5
        
        # Check coverage of key question words in answer
        covered_words = sum(1 for word in question_words if word in answer_lower)
        coverage = covered_words / len(question_words)
        
        # Boost for addressing question structure
        if '¿cómo' in question_lower and ('paso' in answer_lower or 'proceso' in answer_lower):
            coverage += 0.2
        elif '¿qué' in question_lower and ('es' in answer_lower or 'son' in answer_lower):
            coverage += 0.2
        elif '¿cuál' in question_lower and ('diferencia' in answer_lower or 'opción' in answer_lower):
            coverage += 0.2
        
        return min(coverage, 1.0)

    def _determine_confidence_level(self, score: float) -> ConfidenceLevel:
        """Determine confidence level based on overall score"""
        if score >= 0.8:
            return ConfidenceLevel.HIGH
        elif score >= 0.6:
            return ConfidenceLevel.MEDIUM
        elif score >= 0.4:
            return ConfidenceLevel.LOW
        else:
            return ConfidenceLevel.VERY_LOW

    def _generate_explanation(self, factors: Dict[str, float], overall_score: float) -> str:
        """Generate human-readable explanation of confidence score"""
        explanations = []
        
        if factors['context_relevance'] >= 0.7:
            explanations.append("El contexto es altamente relevante para la pregunta")
        elif factors['context_relevance'] < 0.4:
            explanations.append("El contexto tiene relevancia limitada para la pregunta")
        
        if factors['answer_specificity'] >= 0.7:
            explanations.append("La respuesta contiene información específica y detallada")
        elif factors['answer_specificity'] < 0.4:
            explanations.append("La respuesta es bastante general y carece de detalles específicos")
        
        if factors['certainty'] < 0.6:
            explanations.append("La respuesta contiene indicadores de incertidumbre")
        
        if factors['source_quality'] >= 0.7:
            explanations.append("Las fuentes recuperadas son de alta calidad")
        elif factors['source_quality'] < 0.4:
            explanations.append("Las fuentes recuperadas tienen calidad limitada")
        
        base_explanation = f"Puntuación de confianza: {overall_score:.2f}. "
        return base_explanation + ". ".join(explanations) + "."

    def _generate_recommendations(self, factors: Dict[str, float], level: ConfidenceLevel) -> List[str]:
        """Generate recommendations based on confidence factors"""
        recommendations = []
        
        if level in [ConfidenceLevel.LOW, ConfidenceLevel.VERY_LOW]:
            recommendations.append("Considera reformular la pregunta para obtener información más específica")
            recommendations.append("Verifica la información con fuentes oficiales adicionales")
        
        if factors['context_relevance'] < 0.5:
            recommendations.append("La pregunta podría necesitar más contexto o especificidad")
        
        if factors['source_quality'] < 0.5:
            recommendations.append("Se recomienda buscar en documentación más específica o actualizada")
        
        if factors['certainty'] < 0.6:
            recommendations.append("Confirma la información con la oficina de admisiones")
        
        if not recommendations:
            recommendations.append("La información proporcionada tiene alta confiabilidad")
        
        return recommendations


def test_confidence_scoring():
    """Test the confidence scoring functionality"""
    scorer = ConfidenceScorer()
    
    # Test cases with different confidence levels
    test_cases = [
        {
            "question": "¿Cuáles son los requisitos de admisión?",
            "answer": "Los requisitos de admisión son: 1) Certificado de enseñanza media, 2) Puntaje PSU mínimo de 450 puntos, 3) Completar formulario de postulación antes del 15 de enero de 2024.",
            "context": "Para postular necesitas certificado de enseñanza media, puntaje PSU de 450 puntos mínimo, y completar formulario antes del 15 de enero de 2024.",
            "expected_level": ConfidenceLevel.HIGH
        },
        {
            "question": "¿Cuándo son las fechas de postulación?",
            "answer": "Las fechas de postulación generalmente son en enero, pero puede variar según el programa. Consulta con admisiones para más información.",
            "context": "Las fechas pueden variar cada año.",
            "expected_level": ConfidenceLevel.LOW
        }
    ]
    
    for i, case in enumerate(test_cases):
        print(f"\n{'='*60}")
        print(f"Test Case {i+1}")
        print(f"Question: {case['question']}")
        print(f"Answer: {case['answer']}")
        
        # Create mock documents
        docs = [Document(page_content=case['context'], metadata={'source': 'test.md'})]
        
        confidence = scorer.calculate_confidence(
            question=case['question'],
            answer=case['answer'],
            context=case['context'],
            retrieved_docs=docs,
            similarity_scores=[0.8]
        )
        
        print(f"\nConfidence Score: {confidence.overall_score:.3f}")
        print(f"Confidence Level: {confidence.level.value}")
        print(f"Expected Level: {case['expected_level'].value}")
        print(f"Explanation: {confidence.explanation}")
        print(f"Recommendations: {confidence.recommendations}")
        print(f"Factors: {confidence.factors}")


if __name__ == "__main__":
    test_confidence_scoring()