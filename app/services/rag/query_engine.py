import argparse
import os

from dotenv import load_dotenv
from langchain_chroma import Chroma
from langchain.prompts import ChatPromptTemplate
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain.schema.document import Document
from config import Config
from app.services.rag.embedding import get_embedding


API_KEY = Config.API_KEY
CHROMA_PATH = "chroma"

PROMPT_TEMPLATE = """
Responde la siguiente pregunta basándote solamente en el contexto que se te proporciona a continuación. Si no encuentras información relevante, responde con "No puedo responder a esa pregunta".:

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
    embedding_function = get_embedding()
    db = Chroma(
        persist_directory=CHROMA_PATH,
        embedding_function=embedding_function
    )

    core_hits = db.similarity_search_with_score(query_text, k=6)

    extra_ids = []
    for doc, _ in core_hits:
        extra_ids.extend(_neighbor_ids(doc.metadata["id"]))

    extra_docs_raw = db.get(ids=list(set(extra_ids)))
    extra_docs = [
        Document(page_content=p, metadata={"id": i})
        for p, i in zip(extra_docs_raw["documents"], extra_docs_raw["ids"])
    ]

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




    context_text = _collapse_headers(all_docs)

    prompt_template = ChatPromptTemplate.from_template(PROMPT_TEMPLATE)
    prompt = prompt_template.format(context=context_text, question=query_text)

    model = ChatGoogleGenerativeAI(
        model="gemini-2.5-flash",
        google_api_key=API_KEY
    )

    response_text = model.invoke(prompt)

    if hasattr(response_text, "content"):
        response_text = response_text.content

    sources = [doc.metadata.get("id", None) for doc, _ in core_hits]

    print(f'Prompt: {prompt}')

    formatted_response = f"Response: {response_text}\nSources: {sources}"
    print(formatted_response)

    return (response_text, sources)


if __name__ == "__main__":
    main()