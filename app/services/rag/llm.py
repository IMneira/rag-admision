# app/services/rag/llm.py
from llama_index.llms.gemini import Gemini
from config import Config

def get_llm_flash():
    """Initializes and returns the Gemini LLM."""
    return Gemini(
        model_name=Config.GEMINI_MODEL_FLASH, 
        api_key=Config.GEMINI_API_KEY
    )


def get_llm_flash_lite():
    """Initializes and returns the Gemini LLM."""
    return Gemini(
        model_name=Config.GEMINI_MODEL_LITE, 
        api_key=Config.GEMINI_API_KEY
    )