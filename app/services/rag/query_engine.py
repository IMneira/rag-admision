import argparse
import os
import time

from dotenv import load_dotenv
from langchain_chroma import Chroma
from langchain.prompts import ChatPromptTemplate
from app.services.rag.llm import get_llm_flash, get_llm_flash_lite
from langchain.schema.document import Document
from config import Config
from app.services.rag.embedding import get_embedding
from app.services.rag.query_logger import get_query_logger, log_query_context


API_KEY = Config.API_KEY
CHROMA_PATH = "chroma"

PROMPT_TEMPLATE = """
Responde la siguiente pregunta basándote solamente en el contexto que se te proporciona a continuación. 
Si no encuentras información relevante, responde con "No puedo responder a esa pregunta".:

{context}

---

Responde la pregunta basándote en el contexto anterior: {question}
"""



def _neighbor_ids(chunk_id: str) -> list[str]:
    *base, idx = chunk_id.split(":")
    base = ":".join(base)
    i = int(idx)
    return [f"{base}:{i-1}", f"{base}:{i+1}"]

def _collapse_headers(docs: list[Document]) -> str:
    seen_header = set()
    cleaned_parts = []

    for d in docs:
        text = d.page_content
        if text.startswith("§§DOC_HEADER§§ "):
            header, body = text.split("\n\n", 1)
            # keep only the first time we see this exact header
            if header not in seen_header:
                seen_header.add(header)
                cleaned_parts.append(header)     # keep it *once*
            cleaned_parts.append(body)           # always keep body
        else:
            cleaned_parts.append(text)           # fallback (shouldn’t happen)

    return "\n\n---\n\n".join(cleaned_parts)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("query_text", type=str, help="The query text.")
    args = parser.parse_args()
    query_text = args.query_text
    query_rag(query_text)


def query_rag(query_text: str) -> tuple[str, list[str]]:
    # Initialize logging
    logger = get_query_logger()
    query_id = logger.start_query(query_text, "simple_rag")
    start_time = time.time()
    
    try:
        embedding_function = get_embedding()
        db = Chroma(
            persist_directory=CHROMA_PATH,
            embedding_function=embedding_function
        )

        # Log retrieval phase
        retrieval_start = time.time()
        core_hits = db.similarity_search_with_score(query_text, k=6)
        retrieval_time = time.time() - retrieval_start
        
        logger.log_retrieval(
            query_id, 
            "semantic_similarity", 
            len(core_hits),
            {
                "k": 6,
                "retrieval_time": retrieval_time,
                "scores": [float(score) for _, score in core_hits]
            }
        )

        # Context expansion with neighbor documents
        extra_ids = []
        for doc, _ in core_hits:
            extra_ids.extend(_neighbor_ids(doc.metadata["id"]))

        extra_docs_raw = db.get(ids=list(set(extra_ids)))
        extra_docs = [
            Document(page_content=p, metadata={"id": i})
            for p, i in zip(extra_docs_raw["documents"], extra_docs_raw["ids"])
        ]

        # Combine core hits with expanded context
        seen = set()
        all_docs = []
        for doc, _ in core_hits:
            if doc.metadata["id"] not in seen:
                all_docs.append(doc)
                seen.add(doc.metadata["id"])
        for doc in extra_docs:
            if doc.metadata["id"] not in seen:
                all_docs.append(doc)
                seen.add(doc.metadata["id"])




        # Log context assembly
        context_text = _collapse_headers(all_docs)
        context_parts = [
            {
                "content": doc.page_content,
                "source": doc.metadata.get("id", "unknown")
            } 
            for doc in all_docs
        ]
        logger.log_context_assembly(query_id, context_parts, len(context_text))

        # Log prompt construction
        prompt_template = ChatPromptTemplate.from_template(PROMPT_TEMPLATE)
        logger.log_prompt_construction(
            query_id, 
            "simple_template",
            PROMPT_TEMPLATE,
            {"context": f"<{len(context_text)} chars>", "question": query_text}
        )
        
        prompt = prompt_template.format(context=context_text, question=query_text)
        
        # Log final prompt
        context_summary = {
            "source_count": len(all_docs),
            "total_length": len(context_text)
        }
        logger.log_final_prompt(query_id, prompt, context_summary)

        # LLM invocation
        model = get_llm_flash()
        llm_start = time.time()
        response_text = model.complete(prompt)
        llm_time = time.time() - llm_start

        if hasattr(response_text, "content"):
            response_text = response_text.content

        # Log LLM response
        logger.log_llm_response(query_id, str(response_text), llm_time)

        sources = [doc.metadata.get("id", None) for doc, _ in core_hits]

        # Keep original debug prints for backward compatibility
        print(f'Prompt: {prompt}')
        formatted_response = f"Response: {response_text}\nSources: {sources}"
        print(formatted_response)
        
        # Log completion
        total_time = time.time() - start_time
        logger.log_query_complete(query_id, total_time, len(str(response_text)))

        return (response_text, sources)
        
    except Exception as e:
        logger.log_error(query_id, e, "query_rag")
        raise


if __name__ == "__main__":
    main()