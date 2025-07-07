import os
import torch
import logging
from langchain_huggingface import HuggingFaceEmbeddings

# Configure PyTorch to prevent meta tensor issues
os.environ.setdefault("PYTORCH_ENABLE_MPS_FALLBACK", "1")
os.environ.setdefault("TOKENIZERS_PARALLELISM", "false")

model_name = "sentence-transformers/paraphrase-multilingual-mpnet-base-v2"

# Configure logging
logger = logging.getLogger(__name__)

def get_embedding():
    """
    Get HuggingFace embeddings with robust error handling for device issues
    """
    try:
        # Try to initialize with CUDA if available
        if torch.cuda.is_available():
            try:
                device = "cuda"
                logger.info(f"Attempting to use CUDA device for embeddings")
                embeddings = HuggingFaceEmbeddings(
                    model_name=model_name,
                    model_kwargs={"device": device, "trust_remote_code": True},
                    encode_kwargs={"normalize_embeddings": True}
                )
                # Test the embeddings with a simple query
                _ = embeddings.embed_query("test")
                logger.info("Successfully initialized embeddings with CUDA")
                return embeddings
                
            except Exception as cuda_error:
                logger.warning(f"CUDA initialization failed: {cuda_error}. Falling back to CPU.")
        
        # Fallback to CPU with explicit device handling
        try:
            device = "cpu"
            logger.info(f"Initializing embeddings with CPU device")
            
            # Clear CUDA cache if it was attempted
            if torch.cuda.is_available():
                torch.cuda.empty_cache()
            
            embeddings = HuggingFaceEmbeddings(
                model_name=model_name,
                model_kwargs={
                    "device": device,
                    "trust_remote_code": True
                },
                encode_kwargs={"normalize_embeddings": True}
            )
            
            # Test the embeddings
            _ = embeddings.embed_query("test")
            logger.info("Successfully initialized embeddings with CPU")
            return embeddings
            
        except Exception as cpu_error:
            logger.error(f"CPU initialization also failed: {cpu_error}")
            
            # Last resort: try without device specification
            try:
                logger.info("Attempting initialization without explicit device")
                embeddings = HuggingFaceEmbeddings(
                    model_name=model_name,
                    model_kwargs={"trust_remote_code": True},
                    encode_kwargs={"normalize_embeddings": True}
                )
                _ = embeddings.embed_query("test")
                logger.info("Successfully initialized embeddings without explicit device")
                return embeddings
                
            except Exception as final_error:
                logger.error(f"All embedding initialization attempts failed: {final_error}")
                raise RuntimeError(
                    f"Failed to initialize embeddings after multiple attempts. "
                    f"CUDA error: {cuda_error if 'cuda_error' in locals() else 'N/A'}, "
                    f"CPU error: {cpu_error}, "
                    f"Final error: {final_error}"
                )
    
    except Exception as e:
        logger.error(f"Unexpected error in get_embedding: {e}")
        raise