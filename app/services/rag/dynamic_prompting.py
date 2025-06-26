"""
Dynamic Prompting System for Advanced RAG
Provides query-type specific prompts with few-shot examples and chain-of-thought reasoning.
"""

from typing import Dict, List, Optional
from enum import Enum
from langchain.prompts import ChatPromptTemplate
from app.services.rag.query_enhancement import QueryType


class PromptStrategy(Enum):
    DIRECT = "direct"
    CHAIN_OF_THOUGHT = "chain_of_thought"
    FEW_SHOT = "few_shot"
    STEP_BY_STEP = "step_by_step"


class DynamicPromptGenerator:
    def __init__(self):
        self.base_instructions = """
Eres un asistente especializado en admisiones universitarias. Tu objetivo es proporcionar respuestas precisas, útiles y completas basándote únicamente en el contexto proporcionado.

REGLAS IMPORTANTES:
- Responde SOLO con información presente en el contexto
- Si no hay información suficiente, indica claramente "No hay información disponible sobre esto en la documentación proporcionada"
- Incluye detalles específicos como fechas, requisitos, y pasos cuando estén disponibles
- Organiza la información de manera clara y estructurada
- Cita las fuentes cuando sea relevante
"""
        
        # Query-type specific templates
        self.query_templates = {
            QueryType.FACTUAL: self._get_factual_template(),
            QueryType.PROCEDURAL: self._get_procedural_template(),
            QueryType.COMPARATIVE: self._get_comparative_template(),
            QueryType.TEMPORAL: self._get_temporal_template(),
            QueryType.LOCATION: self._get_location_template(),
            QueryType.REQUIREMENT: self._get_requirement_template(),
            QueryType.GENERAL: self._get_general_template()
        }
        
        # Few-shot examples for different query types
        self.few_shot_examples = {
            QueryType.FACTUAL: self._get_factual_examples(),
            QueryType.PROCEDURAL: self._get_procedural_examples(),
            QueryType.REQUIREMENT: self._get_requirement_examples()
        }

    def generate_prompt(self, query: str, context: str, query_type: str, 
                       strategy: PromptStrategy = PromptStrategy.DIRECT,
                       include_examples: bool = False,
                       confidence_needed: bool = False) -> str:
        """Generate dynamic prompt based on query type and strategy"""
        
        # Convert string to enum
        q_type = QueryType(query_type) if isinstance(query_type, str) else query_type
        
        # Get base template for query type
        template = self.query_templates[q_type]
        
        # Add strategy-specific modifications
        if strategy == PromptStrategy.CHAIN_OF_THOUGHT:
            template = self._add_cot_instructions(template, q_type)
        elif strategy == PromptStrategy.FEW_SHOT:
            template = self._add_few_shot_examples(template, q_type)
        elif strategy == PromptStrategy.STEP_BY_STEP:
            template = self._add_step_by_step_instructions(template, q_type)
        
        # Add confidence scoring if needed
        if confidence_needed:
            template = self._add_confidence_instructions(template)
        
        # Format the final prompt
        return template.format(
            base_instructions=self.base_instructions,
            context=context,
            question=query
        )

    def _get_factual_template(self) -> str:
        return """{base_instructions}

PARA PREGUNTAS SOBRE DEFINICIONES Y CONCEPTOS:
- Proporciona una definición clara y completa
- Incluye características importantes
- Menciona cualquier variación o tipo específico
- Usa ejemplos cuando sea apropiado

CONTEXTO:
{context}

PREGUNTA: {question}

RESPUESTA:"""

    def _get_procedural_template(self) -> str:
        return """{base_instructions}

PARA PREGUNTAS SOBRE PROCESOS Y PROCEDIMIENTOS:
- Lista los pasos en orden cronológico
- Incluye requisitos previos si los hay
- Menciona documentos necesarios para cada paso
- Indica plazos y fechas importantes
- Proporciona información de contacto si está disponible

CONTEXTO:
{context}

PREGUNTA: {question}

RESPUESTA:
Aquí está el proceso paso a paso:"""

    def _get_comparative_template(self) -> str:
        return """{base_instructions}

PARA PREGUNTAS COMPARATIVAS:
- Identifica claramente las opciones que se comparan
- Lista similitudes y diferencias específicas
- Organiza la información en categorías relevantes
- Proporciona recomendaciones basadas en diferentes escenarios

CONTEXTO:
{context}

PREGUNTA: {question}

RESPUESTA:
Comparación detallada:"""

    def _get_temporal_template(self) -> str:
        return """{base_instructions}

PARA PREGUNTAS SOBRE FECHAS Y HORARIOS:
- Proporciona fechas exactas cuando estén disponibles
- Incluye horarios específicos
- Menciona cualquier variación por programa o facultad
- Indica fechas límite importantes
- Considera diferentes periodos académicos

CONTEXTO:
{context}

PREGUNTA: {question}

RESPUESTA:
Información de fechas y horarios:"""

    def _get_location_template(self) -> str:
        return """{base_instructions}

PARA PREGUNTAS SOBRE UBICACIONES:
- Proporciona direcciones completas cuando estén disponibles
- Incluye referencias y puntos de referencia
- Menciona horarios de atención
- Indica medios de transporte o acceso
- Proporciona información de contacto

CONTEXTO:
{context}

PREGUNTA: {question}

RESPUESTA:
Información de ubicación:"""

    def _get_requirement_template(self) -> str:
        return """{base_instructions}

PARA PREGUNTAS SOBRE REQUISITOS:
- Lista todos los requisitos obligatorios
- Distingue entre requisitos generales y específicos por programa
- Incluye formatos y documentación necesaria
- Menciona excepciones o casos especiales
- Proporciona plazos para cumplir requisitos

CONTEXTO:
{context}

PREGUNTA: {question}

RESPUESTA:
Requisitos detallados:"""

    def _get_general_template(self) -> str:
        return """{base_instructions}

CONTEXTO:
{context}

PREGUNTA: {question}

RESPUESTA:"""

    def _add_cot_instructions(self, template: str, query_type: QueryType) -> str:
        """Add chain-of-thought reasoning instructions"""
        cot_instruction = """
RAZONAMIENTO PASO A PASO:
Antes de responder, sigue estos pasos:
1. Identifica los elementos clave de la pregunta
2. Busca información relevante en el contexto
3. Organiza la información encontrada
4. Estructura tu respuesta de manera lógica

"""
        return template.replace("RESPUESTA:", cot_instruction + "RESPUESTA:")

    def _add_few_shot_examples(self, template: str, query_type: QueryType) -> str:
        """Add few-shot examples for the query type"""
        if query_type in self.few_shot_examples:
            examples = self.few_shot_examples[query_type]
            examples_text = "\n\nEJEMPLOS DE RESPUESTAS SIMILARES:\n" + examples + "\n"
            return template.replace("CONTEXTO:", examples_text + "\nCONTEXTO:")
        return template

    def _add_step_by_step_instructions(self, template: str, query_type: QueryType) -> str:
        """Add step-by-step instructions"""
        step_instruction = """
INSTRUCCIONES PASO A PASO:
1. Lee cuidadosamente toda la información del contexto
2. Identifica la información más relevante para la pregunta
3. Organiza la respuesta en puntos claros y numerados
4. Verifica que toda la información esté respaldada por el contexto

"""
        return template.replace("RESPUESTA:", step_instruction + "RESPUESTA:")

    def _add_confidence_instructions(self, template: str) -> str:
        """Add confidence scoring instructions"""
        confidence_instruction = """
EVALUACIÓN DE CONFIANZA:
Al final de tu respuesta, incluye una evaluación de confianza:
- ALTA CONFIANZA: La información está claramente presente en el contexto
- MEDIA CONFIANZA: La información se puede inferir del contexto
- BAJA CONFIANZA: La información es limitada o parcial en el contexto

"""
        return template.replace("RESPUESTA:", confidence_instruction + "RESPUESTA:")

    def _get_factual_examples(self) -> str:
        return """
Ejemplo:
PREGUNTA: "¿Qué es la PSU?"
RESPUESTA: "La PSU (Prueba de Selección Universitaria) es un examen estandarizado que mide conocimientos y habilidades académicas de los estudiantes que terminan la educación secundaria. Se compone de diferentes pruebas: Lenguaje y Comunicación, Matemáticas, Historia y Ciencias Sociales, y Ciencias. Los resultados se usan como criterio de selección para el ingreso a las universidades."
"""

    def _get_procedural_examples(self) -> str:
        return """
Ejemplo:
PREGUNTA: "¿Cómo puedo postular a la universidad?"
RESPUESTA: "Para postular a la universidad, sigue estos pasos:
1. Rendir la PSU en las fechas establecidas
2. Registrarte en el sistema de admisión online
3. Seleccionar hasta 10 carreras en orden de preferencia
4. Pagar el arancel de postulación
5. Subir los documentos requeridos (certificado de notas, etc.)
6. Confirmar tu postulación antes del cierre del proceso
El período de postulación generalmente es entre diciembre y enero."
"""

    def _get_requirement_examples(self) -> str:
        return """
Ejemplo:
PREGUNTA: "¿Cuáles son los requisitos de admisión?"
RESPUESTA: "Los requisitos de admisión incluyen:

Requisitos obligatorios:
• Licencia de educación media o título técnico equivalente
• Puntaje PSU mínimo (varía por carrera)
• Certificado de notas de enseñanza media

Requisitos específicos (según carrera):
• Pruebas específicas de la PSU (Historia, Ciencias)
• Puntajes mínimos diferenciados por programa
• Documentación adicional para carreras especiales

El puntaje de selección se calcula considerando NEM (20%), ranking (20%) y PSU (60%)."
"""

    def get_optimal_strategy(self, query_type: QueryType, complexity_score: float) -> PromptStrategy:
        """Determine optimal prompting strategy based on query type and complexity"""
        
        # High complexity queries benefit from chain-of-thought
        if complexity_score >= 0.7:
            if query_type in [QueryType.PROCEDURAL, QueryType.COMPARATIVE]:
                return PromptStrategy.CHAIN_OF_THOUGHT
            else:
                return PromptStrategy.STEP_BY_STEP
        
        # Medium complexity might benefit from examples
        elif complexity_score >= 0.5:
            if query_type in [QueryType.FACTUAL, QueryType.REQUIREMENT]:
                return PromptStrategy.FEW_SHOT
            else:
                return PromptStrategy.DIRECT
        
        # Simple queries use direct approach
        else:
            return PromptStrategy.DIRECT

    def create_chat_prompt_template(self, query_type: QueryType, strategy: PromptStrategy = PromptStrategy.DIRECT) -> ChatPromptTemplate:
        """Create a ChatPromptTemplate for the given query type and strategy"""
        prompt_text = self.generate_prompt(
            query="{question}",
            context="{context}",
            query_type=query_type,
            strategy=strategy
        )
        return ChatPromptTemplate.from_template(prompt_text)


def test_dynamic_prompting():
    """Test the dynamic prompting functionality"""
    generator = DynamicPromptGenerator()
    
    test_cases = [
        ("¿Qué es la PSU?", QueryType.FACTUAL, 0.3),
        ("¿Cómo puedo postular a la universidad?", QueryType.PROCEDURAL, 0.7),
        ("¿Cuáles son los requisitos de admisión?", QueryType.REQUIREMENT, 0.6),
        ("¿Cuál es la diferencia entre PSU y PAES?", QueryType.COMPARATIVE, 0.8)
    ]
    
    context = "La PSU es una prueba de selección universitaria. Para postular necesitas rendir la PSU y subir documentos."
    
    for query, q_type, complexity in test_cases:
        print(f"\n{'='*60}")
        print(f"Query: {query}")
        print(f"Type: {q_type.value}")
        print(f"Complexity: {complexity}")
        
        # Get optimal strategy
        strategy = generator.get_optimal_strategy(q_type, complexity)
        print(f"Strategy: {strategy.value}")
        
        # Generate prompt
        prompt = generator.generate_prompt(
            query=query,
            context=context,
            query_type=q_type,
            strategy=strategy,
            confidence_needed=True
        )
        
        print(f"\nGenerated Prompt:\n{prompt[:300]}...")


if __name__ == "__main__":
    test_dynamic_prompting()