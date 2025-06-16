import argparse
import os

from dotenv import load_dotenv
from langchain_chroma import Chroma
from langchain.prompts import ChatPromptTemplate
from langchain_google_genai import ChatGoogleGenerativeAI

from app.services.rag.embedding import get_embedding


load_dotenv()

API_KEY = os.getenv("API_KEY")
CHROMA_PATH = "chroma"

PROMPT_TEMPLATE = """
Responde la siguiente pregunta basándote solamente en el contexto que se te proporciona a continuación. Si no encuentras información relevante, responde con "No puedo responder a esa pregunta".:

{context}

---

Responde la pregunta basándote en el contexto anterior: {question}
"""


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("query_text", type=str, help="The query text.")
    args = parser.parse_args()
    query_text = args.query_text
    query_rag(query_text)


def query_rag(query_text: str) -> str:
    embedding_function = get_embedding()
    db = Chroma(
        persist_directory=CHROMA_PATH,
        embedding_function=embedding_function
    )

    results = db.similarity_search_with_score(query_text, k=5)

    context_text = "\n\n---\n\n".join(
        [doc.page_content for doc, _ in results]
    )

    prompt_template = ChatPromptTemplate.from_template(PROMPT_TEMPLATE)
    prompt = prompt_template.format(context=context_text, question=query_text)

    model = ChatGoogleGenerativeAI(
        model="gemini-1.5-flash",
        google_api_key=API_KEY
    )

    response_text = model.invoke(prompt)

    if hasattr(response_text, "content"):
        response_text = response_text.content

    sources = [doc.metadata.get("id", None) for doc, _ in results]

    formatted_response = f"Response: {response_text}\nSources: {sources}"
    print(formatted_response)

    return response_text


if __name__ == "__main__":
    main()