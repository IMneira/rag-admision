# app/services/rag/llm.py
from llama_index.llms.gemini import Gemini
from config import Config

def get_llm():
    """Initializes and returns the Gemini LLM."""
    return Gemini(
        model_name=Config.GEMINI_MODEL, 
        api_key=Config.GEMINI_API_KEY
    )