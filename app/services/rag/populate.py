import argparse
import os
import shutil
import logging
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

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

def build_headers(docs: list[Document]) -> dict[str, str]:
    llm = get_llm()
    grouped: dict[str, list[str]] = defaultdict(list)

    for d in tqdm.tqdm(docs, desc="Grouping documents"):
        try:
            grouped[d.metadata["source"]].append(d.page_content)
        except Exception as e:
            logging.error(f"Error processing document {d.metadata.get('source', 'unknown')}: {e}")
            continue

    headers: dict[str, str] = {}
    failed_headers = []
    
    for src, pages in tqdm.tqdm(grouped.items(), desc="Building headers"):
        try:
            whole_doc = "\n".join(pages)[:10000]          # stay under token limit
            prompt = (
                "Eres un resumidor conciso.\n"
                "Escribe **tres oraciones cortas** (≤75 palabras en total) que capturen "
                "el contexto principal de este documento para que puedan ser "
                "antepuestos a cada fragmento para la generación aumentada por recuperación.\n\n"
                f"DOCUMENTO:\n{whole_doc}\n\nENCABEZADO:"
            )
            headers[src] = llm.complete(prompt).text.strip()
            time.sleep(7)  # avoid rate limits
        except Exception as e:
            logging.error(f"Failed to build header for {src}: {e}")
            failed_headers.append(src)
            continue

    if failed_headers:
        logging.warning(f"Failed to build headers for {len(failed_headers)} documents: {failed_headers}")
    
    logging.info(f"Successfully built headers for {len(headers)} out of {len(grouped)} documents")
    return headers
    

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--reset", action="store_true", help="Reset the database.")
    parser.add_argument("--drive", action="store_true", help="Ingest documents from Google Drive folder.")
    args = parser.parse_args()

    try:
        if args.reset:
            print("✨ Clearing Database")
            clear_database()

        if args.drive:
            print("✨ Ingesting documents from Google Drive")
            documents = ingest_drive_folder(DRIVE_FOLDER_ID)
            print(f"Successfully loaded {len(documents)} documents from Drive")
        else:
            print("✨ Ingesting documents from local data directory")
            documents = load_documents()

        if not documents:
            logging.warning("No documents were loaded. Exiting.")
            return

        logging.info(f"Total documents loaded: {len(documents)}")
        
        headers = build_headers(documents)
        chunks = split_documents(documents)

        successful_chunks = 0
        for chunk in chunks:
            try:
                header = headers.get(chunk.metadata["source"])
                if header:
                    chunk.page_content = f"{header}\n\n{chunk.page_content}"
                successful_chunks += 1
            except Exception as e:
                logging.error(f"Error processing chunk from {chunk.metadata.get('source', 'unknown')}: {e}")
                continue

        logging.info(f"Successfully processed {successful_chunks} out of {len(chunks)} chunks")
        
        if successful_chunks > 0:
            add_to_chroma(chunks)
        else:
            logging.error("No chunks were successfully processed. Nothing to add to database.")
            
    except Exception as e:
        logging.error(f"Critical error in main process: {e}")
        raise

def load_documents(file_types: list[str] = [".md"]) -> list[Document]:
    documents = []
    failed_files = []

    if ".pdf" in file_types:
        print("Including .pdf in documents.")
        try:
            pdf_loader = PyPDFDirectoryLoader(DATA_PATH)
            pdf_docs = pdf_loader.load()
            documents.extend(pdf_docs)
            logging.info(f"Successfully loaded {len(pdf_docs)} PDF documents")
        except Exception as e:
            logging.error(f"Failed to load PDF documents: {e}")
            failed_files.append("PDF directory")
    else:
        print("Skipping .pdf in documents")

    if ".txt" in file_types:
        print("Including .txt in documents.")
        try:
            txt_loader = DirectoryLoader(DATA_PATH, glob="**/*.txt",
                                         loader_cls=TextLoader)
            txt_docs = txt_loader.load()
            documents.extend(txt_docs)
            logging.info(f"Successfully loaded {len(txt_docs)} TXT documents")
        except Exception as e:
            logging.error(f"Failed to load TXT documents: {e}")
            failed_files.append("TXT directory")
    else:
        print("Skipping .txt in documents")
    
    if ".md" in file_types:
        print("Including .md (Markdown) in documents.")
        try:
            md_loader = DirectoryLoader(DATA_PATH, glob="**/*.md",
                                        loader_cls=TextLoader)
            md_docs = md_loader.load()
            documents.extend(md_docs)
            logging.info(f"Successfully loaded {len(md_docs)} Markdown documents")
        except Exception as e:
            logging.error(f"Failed to load Markdown documents: {e}")
            failed_files.append("Markdown directory")
    else:
        print("Skipping .md in documents")

    if failed_files:
        logging.warning(f"Failed to load documents from: {failed_files}")
    
    return documents

def split_documents(documents: list[Document]) -> list[Document]:
    text_splitter = RecursiveCharacterTextSplitter(
        chunk_size=800,
        chunk_overlap=80,
        length_function=len,
        is_separator_regex=False,
    )
    
    successful_chunks = []
    failed_documents = []
    
    for doc in tqdm.tqdm(documents, desc="Splitting documents"):
        try:
            chunks = text_splitter.split_documents([doc])
            successful_chunks.extend(chunks)
        except Exception as e:
            logging.error(f"Failed to split document {doc.metadata.get('source', 'unknown')}: {e}")
            failed_documents.append(doc.metadata.get('source', 'unknown'))
            continue
    
    if failed_documents:
        logging.warning(f"Failed to split {len(failed_documents)} documents: {failed_documents}")
    
    logging.info(f"Successfully split documents into {len(successful_chunks)} chunks")
    return successful_chunks

def add_to_chroma(chunks: list[Document]) -> None:
    try:
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
            
            # Add documents in batches to handle potential failures
            batch_size = 100
            successful_batches = 0
            failed_batches = 0
            
            for i in range(0, len(new_chunks), batch_size):
                batch = new_chunks[i:i + batch_size]
                batch_ids = new_chunk_ids[i:i + batch_size]
                
                try:
                    db.add_documents(batch, ids=batch_ids)
                    successful_batches += 1
                    logging.info(f"Successfully added batch {successful_batches} ({len(batch)} documents)")
                except Exception as e:
                    failed_batches += 1
                    logging.error(f"Failed to add batch {i//batch_size + 1}: {e}")
                    continue
            
            logging.info(f"Database update complete: {successful_batches} successful batches, {failed_batches} failed batches")
        else:
            print("✅ No new documents to add")
            
    except Exception as e:
        logging.error(f"Critical error accessing Chroma database: {e}")
        raise

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


def process_single_document(file_path: str, source_url: str = None) -> dict:
    """
    Process a single uploaded document through the complete RAG pipeline.
    
    Args:
        file_path: Path to the document file in the data directory
        source_url: Optional source URL for the document
        
    Returns:
        dict: Processing result with status and details
    """
    result = {
        'success': False,
        'chunks_added': 0,
        'header_generated': False,
        'error': None
    }
    
    try:
        # Load the single document
        logging.info(f"Processing single document: {file_path}")
        
        if not os.path.exists(file_path):
            result['error'] = f"File not found: {file_path}"
            return result
            
        # Determine file type and load accordingly
        file_extension = os.path.splitext(file_path)[1].lower()
        
        if file_extension == ".pdf":
            loader = PyPDFLoader(file_path)
        elif file_extension in [".txt", ".md"]:
            loader = TextLoader(file_path)
        else:
            result['error'] = f"Unsupported file type: {file_extension}"
            return result
            
        # Load document
        documents = loader.load()
        if not documents:
            result['error'] = "No content could be loaded from the file"
            return result
            
        logging.info(f"Loaded {len(documents)} document sections from {file_path}")
        
        # Build header for the document
        try:
            headers = build_headers(documents)
            header = headers.get(documents[0].metadata["source"]) if headers else None
            result['header_generated'] = bool(header)
            logging.info(f"Generated header for document: {bool(header)}")
        except Exception as e:
            logging.warning(f"Failed to build header for {file_path}: {e}")
            header = None
            result['header_generated'] = False
        
        # Split documents into chunks
        chunks = split_documents(documents)
        if not chunks:
            result['error'] = "No chunks were created from the document"
            return result
            
        logging.info(f"Split document into {len(chunks)} chunks")
        
        # Add header to each chunk if available
        if header:
            for chunk in chunks:
                chunk.page_content = f"{header}\n\n{chunk.page_content}"
        
        # Add chunks to Chroma database
        try:
            # Initialize database connection
            db = Chroma(
                persist_directory=CHROMA_PATH,
                embedding_function=get_embedding()
            )
            
            # Calculate chunk IDs
            chunks_with_ids = calculate_chunk_ids(chunks)
            
            # Check for existing chunks
            existing_items = db.get(include=[])
            existing_ids = set(existing_items["ids"])
            
            # Filter out existing chunks
            new_chunks = [
                chunk for chunk in chunks_with_ids
                if chunk.metadata["id"] not in existing_ids
            ]
            
            if new_chunks:
                new_chunk_ids = [chunk.metadata["id"] for chunk in new_chunks]
                db.add_documents(new_chunks, ids=new_chunk_ids)
                result['chunks_added'] = len(new_chunks)
                logging.info(f"Added {len(new_chunks)} new chunks to database")
            else:
                result['chunks_added'] = 0
                logging.info("All chunks already exist in database")
            
            result['success'] = True
            
        except Exception as e:
            result['error'] = f"Failed to add chunks to database: {str(e)}"
            logging.error(f"Database error for {file_path}: {e}")
            return result
            
    except Exception as e:
        result['error'] = f"Processing error: {str(e)}"
        logging.error(f"Critical error processing {file_path}: {e}")
        
    return result


def ingest_drive_folder(folder_id: str):
    docs = []
    failed_files = []
    
    try:
        file_paths = list(iter_local_docs(folder_id))
        logging.info(f"Found {len(file_paths)} files in Drive folder")
    except Exception as e:
        logging.error(f"Failed to list files from Drive folder {folder_id}: {e}")
        return docs
    
    for path in tqdm.tqdm(file_paths, desc="Loading Drive documents"):
        try:
            if path.suffix == ".pdf":
                loader = PyPDFLoader(str(path))
            elif path.suffix == ".txt":
                loader = TextLoader(str(path))
            else:
                logging.info(f"Skipping unsupported file type: {path.suffix} for {path}")
                continue

            file_docs = loader.load()
            docs.extend(file_docs)
            logging.debug(f"Successfully loaded {len(file_docs)} documents from {path}")
            
        except Exception as e:
            logging.error(f"Failed to load document {path}: {e}")
            failed_files.append(str(path))
            continue

    if failed_files:
        logging.warning(f"Failed to load {len(failed_files)} files from Drive: {failed_files}")
    
    logging.info(f"Successfully loaded {len(docs)} documents from Drive folder")
    return docs

    
    










if __name__ == "__main__":
    main()