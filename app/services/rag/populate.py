import argparse
import os
import shutil
from collections import defaultdict

from langchain_community.document_loaders import TextLoader, DirectoryLoader
from langchain_community.document_loaders.pdf import PyPDFDirectoryLoader
from langchain_community.document_loaders import PyPDFLoader
from langchain.schema.document import Document
from langchain_text_splitters import RecursiveCharacterTextSplitter
from langchain_chroma import Chroma
import tqdm
import time

from app.services.rag.embedding import get_embedding
from app.services.rag.llm import get_llm
from config import Config
from app.services.rag.drive_loader import iter_local_docs


CHROMA_PATH = "chroma"
DATA_PATH = "data"
HEADER_TAG = "§§DOC_HEADER§§ "
DRIVE_FOLDER_ID = '1rax_JCVVrzFoJBQn8OKPcDFZ5iLyMysN'

def build_headers(docs: list[Document]) -> dict[str, str]:
    llm = get_llm()
    grouped: dict[str, list[str]] = defaultdict(list)

    for d in tqdm.tqdm(docs):
        grouped[d.metadata["source"]].append(d.page_content)

    headers: dict[str, str] = {}
    for src, pages in tqdm.tqdm(grouped.items()):
        whole_doc = "\n".join(pages)[:10000]          # stay under token limit
        prompt = (
            "You are a concise summarizer.\n"
            "Write **three short sentences** (≤75 words total) that capture "
            "the main context of this document so they can be prepended to "
            "each chunk for retrieval-augmented generation.\n\n"
            f"DOCUMENT:\n{whole_doc}\n\nHEADER:"
        )
        headers[src] = llm.complete(prompt).text.strip()
        time.sleep(7)  # avoid rate limits

    return headers
    

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--reset", action="store_true", help="Reset the database.")
    parser.add_argument("--drive", action="store_true", help="Ingest documents from Google Drive folder.")
    args = parser.parse_args()

    if args.reset:
        print("✨ Clearing Database")
        clear_database()

    if args.drive:
        print("✨ Ingesting documents from Google Drive")
        documents = ingest_drive_folder(DRIVE_FOLDER_ID)
        print(documents)
    else:
        print("✨ Ingesting documents from local data directory")
        documents = load_documents()

    headers = build_headers(documents)
    chunks = split_documents(documents)

    for chunk in chunks:
        header = headers.get(chunk.metadata["source"])
        if header:
            chunk.page_content = f"{header}\n\n{chunk.page_content}"


    add_to_chroma(chunks)

def load_documents(file_types: list[str] = [".txt"]) -> list[Document]:
    documents = []

    if ".pdf" in file_types:
        print("Including .pdf in documents.")
        pdf_loader = PyPDFDirectoryLoader(DATA_PATH)
        documents.extend(pdf_loader.load())
    else:
        print("Skipping .pdf in documents")

    if ".txt" in file_types:
        print("Including .txt in documents.")
        txt_loader = DirectoryLoader(DATA_PATH, glob="**/*.txt",
                                     loader_cls=TextLoader)
        documents.extend(txt_loader.load())
    else:
        print("Skipping .txt in documents")

    return documents

def split_documents(documents: list[Document]) -> list[Document]:
    text_splitter = RecursiveCharacterTextSplitter(
        chunk_size=800,
        chunk_overlap=80,
        length_function=len,
        is_separator_regex=False,
    )
    return text_splitter.split_documents(documents)

def add_to_chroma(chunks: list[Document]) -> None:
    db = Chroma(
        persist_directory=CHROMA_PATH,
        embedding_function=get_embedding()
    )

    chunks_with_ids = calculate_chunk_ids(chunks)
    existing_items = db.get(include=[])
    existing_ids = set(existing_items["ids"])
    print(f"Number of existing documents in DB: {len(existing_ids)}")

    new_chunks = [
        chunk for chunk in chunks_with_ids
        if chunk.metadata["id"] not in existing_ids
    ]

    if new_chunks:
        print(f"👉 Adding new documents: {len(new_chunks)}")
        new_chunk_ids = [chunk.metadata["id"] for chunk in new_chunks]
        db.add_documents(new_chunks, ids=new_chunk_ids)
    else:
        print("✅ No new documents to add")

def calculate_chunk_ids(chunks: list[Document]) -> list[Document]:
    last_page_id = None
    current_chunk_index = 0

    for chunk in chunks:
        source = chunk.metadata.get("source")
        page = chunk.metadata.get("page")
        current_page_id = f"{source}:{page}"

        if current_page_id == last_page_id:
            current_chunk_index += 1
        else:
            current_chunk_index = 0

        chunk_id = f"{current_page_id}:{current_chunk_index}"
        last_page_id = current_page_id
        chunk.metadata["id"] = chunk_id

    return chunks

def clear_database() -> None:
    if os.path.exists(CHROMA_PATH):
        shutil.rmtree(CHROMA_PATH)


def ingest_drive_folder(folder_id: str):
    docs = []
    for path in iter_local_docs(folder_id):
        if path.suffix == ".pdf":
            loader = PyPDFLoader(str(path))
        elif path.suffix == ".txt":
            loader = TextLoader(str(path))
        else:
            print(f"Skipping unsupported file type: {path.suffix}")
            continue

        docs.extend(loader.load())

    return docs

    
    










if __name__ == "__main__":
    main()