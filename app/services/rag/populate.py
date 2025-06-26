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
from app.services.rag.llm import get_llm_flash, get_llm_flash_lite
from config import Config
from app.services.rag.drive_loader import iter_local_docs
from app.services.rag.hybrid_search import BM25KeywordSearcher
import json


CHROMA_PATH = "chroma"
BM25_PATH = "bm25_index"
DATA_PATH = "data"
HEADER_CACHE_PATH = "header_cache.json"
HEADER_TAG = "§§DOC_HEADER§§ "
DRIVE_FOLDER_ID = '1rax_JCVVrzFoJBQn8OKPcDFZ5iLyMysN'

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

def get_existing_document_sources() -> set[str]:
    """Get set of document sources that are already in the Chroma database"""
    try:
        db = Chroma(
            persist_directory=CHROMA_PATH,
            embedding_function=get_embedding()
        )
        existing_items = db.get(include=["metadatas"])
        
        # Extract unique source paths from existing documents
        existing_sources = set()
        for metadata in existing_items.get("metadatas", []):
            if metadata and "source" in metadata:
                existing_sources.add(metadata["source"])
        
        logging.info(f"Found {len(existing_sources)} existing document sources in database")
        return existing_sources
        
    except Exception as e:
        logging.warning(f"Could not access existing database: {e}")
        return set()


def filter_new_documents(all_documents: list[Document], existing_sources: set[str]) -> tuple[list[Document], list[Document]]:
    """
    Separate documents into new and existing based on source paths
    
    Returns:
        tuple: (new_documents, existing_documents)
    """
    new_documents = []
    existing_documents = []
    
    for doc in all_documents:
        source = doc.metadata.get("source", "")
        if source in existing_sources:
            existing_documents.append(doc)
        else:
            new_documents.append(doc)
    
    logging.info(f"Document filtering: {len(new_documents)} new, {len(existing_documents)} existing")
    return new_documents, existing_documents


def load_header_cache() -> dict[str, str]:
    """Load cached headers from disk"""
    try:
        if os.path.exists(HEADER_CACHE_PATH):
            with open(HEADER_CACHE_PATH, 'r', encoding='utf-8') as f:
                cache = json.load(f)
                logging.info(f"Loaded {len(cache)} cached headers")
                return cache
    except Exception as e:
        logging.warning(f"Failed to load header cache: {e}")
    
    return {}


def save_header_cache(headers: dict[str, str]) -> None:
    """Save headers to cache file"""
    try:
        with open(HEADER_CACHE_PATH, 'w', encoding='utf-8') as f:
            json.dump(headers, f, indent=2, ensure_ascii=False)
        logging.info(f"Saved {len(headers)} headers to cache")
    except Exception as e:
        logging.error(f"Failed to save header cache: {e}")


def build_headers(docs: list[Document]) -> dict[str, str]:
    """Build headers for documents, using cache when available"""
    if not docs:
        return {}
    
    # Load existing header cache
    cached_headers = load_header_cache()
    
    llm = get_llm_flash_lite()
    grouped: dict[str, list[str]] = defaultdict(list)

    for d in tqdm.tqdm(docs, desc="Grouping documents"):
        try:
            grouped[d.metadata["source"]].append(d.page_content)
        except Exception as e:
            logging.error(f"Error processing document {d.metadata.get('source', 'unknown')}: {e}")
            continue

    headers: dict[str, str] = {}
    failed_headers = []
    cached_count = 0
    generated_count = 0
    
    for src, pages in tqdm.tqdm(grouped.items(), desc="Building headers"):
        try:
            # Check if header is already cached
            if src in cached_headers:
                headers[src] = cached_headers[src]
                cached_count += 1
                continue
            
            # Generate new header
            whole_doc = "\n".join(pages)[:10000]          # stay under token limit
            prompt = (
                "Eres un resumidor conciso.\n"
                "Escribe **tres oraciones cortas** (≤75 palabras en total) que capturen "
                "el contexto principal de este documento para que puedan ser "
                "antepuestos a cada fragmento para la generación aumentada por recuperación.\n\n"
                f"DOCUMENTO:\n{whole_doc}\n\nENCABEZADO:"
            )
            new_header = llm.complete(prompt).text.strip()
            headers[src] = new_header
            generated_count += 1
            
            # Add to cache and save periodically
            cached_headers[src] = new_header
            if generated_count % 5 == 0:  # Save cache every 5 new headers
                save_header_cache(cached_headers)
                
            time.sleep(7)  # avoid rate limits
        except Exception as e:
            logging.error(f"Failed to build header for {src}: {e}")
            failed_headers.append(src)
            continue

    # Save final cache
    if generated_count > 0:
        save_header_cache(cached_headers)

    if failed_headers:
        logging.warning(f"Failed to build headers for {len(failed_headers)} documents: {failed_headers}")
    
    logging.info(f"Headers: {cached_count} from cache, {generated_count} newly generated, {len(failed_headers)} failed")
    logging.info(f"Successfully built headers for {len(headers)} out of {len(grouped)} documents")
    return headers
    

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--reset", action="store_true", help="Reset the database.")
    parser.add_argument("--drive", action="store_true", help="Ingest documents from Google Drive folder.")
    parser.add_argument("--sync-bm25", action="store_true", help="Sync BM25 index with documents already in Chroma DB.")
    args = parser.parse_args()

    try:
        if args.reset:
            print("✨ Clearing Database")
            clear_database()
        
        # Handle BM25 sync operation
        if args.sync_bm25:
            print("🔄 Syncing BM25 index with existing Chroma documents")
            sync_bm25_index()
            return

        # Step 1: Load all documents
        if args.drive:
            print("✨ Ingesting documents from Google Drive")
            all_documents = ingest_drive_folder(DRIVE_FOLDER_ID)
            print(f"Successfully loaded {len(all_documents)} documents from Drive")
        else:
            print("✨ Ingesting documents from local data directory")
            all_documents = load_documents()

        if not all_documents:
            logging.warning("No documents were loaded. Exiting.")
            return

        logging.info(f"Total documents loaded: {len(all_documents)}")
        
        # Step 2: Check which documents are already in the database (EARLY FILTERING)
        print("🔍 Checking for existing documents in database...")
        existing_sources = get_existing_document_sources()
        new_documents, existing_documents = filter_new_documents(all_documents, existing_sources)
        
        if not new_documents:
            print("✅ No new documents found. Database is up to date!")
            print(f"📊 Skipped processing {len(existing_documents)} existing documents")
            return
        
        print(f"📝 Processing {len(new_documents)} new documents")
        print(f"⏭️  Skipping {len(existing_documents)} existing documents")
        
        # Step 3: Only process NEW documents through expensive pipeline
        print("🤖 Building headers for new documents only...")
        headers = build_headers(new_documents)  # Only process new docs!
        
        print("✂️  Splitting new documents into chunks...")
        new_chunks = split_documents(new_documents)  # Only split new docs!

        # Step 4: Apply headers to new chunks
        print("📋 Applying headers to new chunks...")
        successful_chunks = 0
        for chunk in new_chunks:
            try:
                header = headers.get(chunk.metadata["source"])
                if header:
                    chunk.page_content = f"{header}\n\n{chunk.page_content}"
                successful_chunks += 1
            except Exception as e:
                logging.error(f"Error processing chunk from {chunk.metadata.get('source', 'unknown')}: {e}")
                continue

        logging.info(f"Successfully processed {successful_chunks} out of {len(new_chunks)} new chunks")
        
        # Step 5: Add to databases (Chroma will double-check, BM25 will be incremental)
        if successful_chunks > 0:
            print("💾 Adding new chunks to Chroma database...")
            add_to_chroma(new_chunks)
            
            print("🔍 Updating BM25 keyword search index...")
            build_bm25_index_incremental(new_chunks)  # Use incremental update
            
            print(f"✅ Successfully processed {len(new_documents)} new documents!")
            print(f"⚡ Saved significant time by skipping {len(existing_documents)} existing documents")
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

def build_bm25_index(chunks: list[Document]) -> None:
    """Build BM25 keyword search index from document chunks (full rebuild)"""
    try:
        print("✨ Building BM25 keyword search index")
        logging.info(f"Building BM25 index for {len(chunks)} chunks")
        
        # Initialize BM25 searcher
        bm25_searcher = BM25KeywordSearcher(BM25_PATH)
        
        # Build the index
        bm25_searcher.build_index(chunks, force_rebuild=True)
        
        logging.info("BM25 index built successfully")
        print("✅ BM25 index built successfully")
        
    except Exception as e:
        logging.error(f"Failed to build BM25 index: {e}")
        print(f"❌ Failed to build BM25 index: {e}")


def build_bm25_index_incremental(new_chunks: list[Document]) -> None:
    """Build or update BM25 keyword search index incrementally"""
    try:
        if not new_chunks:
            print("✅ No new chunks for BM25 index")
            return
            
        logging.info(f"Updating BM25 index with {len(new_chunks)} new chunks")
        
        # Initialize BM25 searcher
        bm25_searcher = BM25KeywordSearcher(BM25_PATH)
        
        # Check if index exists
        index_file = os.path.join(BM25_PATH, "bm25_index.pkl")
        
        if os.path.exists(index_file):
            # Index exists, try incremental update
            print(f"📄 Existing BM25 index found, adding {len(new_chunks)} new chunks...")
            try:
                bm25_searcher.add_documents(new_chunks)
                logging.info("BM25 index updated incrementally")
                print("✅ BM25 index updated successfully")
                return
            except Exception as e:
                logging.warning(f"Incremental update failed: {e}. Falling back to full rebuild...")
                print("⚠️  Incremental update failed, rebuilding from scratch...")
        
        # No index exists or incremental failed - need to rebuild with all documents
        print("🔄 No existing index found, need to load all documents for full rebuild...")
        
        # Get all existing chunks from Chroma to rebuild complete BM25 index
        try:
            db = Chroma(
                persist_directory=CHROMA_PATH,
                embedding_function=get_embedding()
            )
            
            # Get ALL existing chunks
            all_existing = db.get(include=["documents", "metadatas"])
            existing_chunks = []
            
            if all_existing.get("documents"):
                for i, (content, metadata) in enumerate(zip(
                    all_existing["documents"], 
                    all_existing.get("metadatas", [])
                )):
                    doc = Document(page_content=content, metadata=metadata or {})
                    existing_chunks.append(doc)
            
            # Combine existing + new chunks
            all_chunks = existing_chunks + new_chunks
            
            print(f"🔨 Building complete BM25 index with {len(all_chunks)} total chunks...")
            bm25_searcher.build_index(all_chunks, force_rebuild=True)
            
            logging.info(f"BM25 index rebuilt with {len(existing_chunks)} existing + {len(new_chunks)} new chunks")
            print("✅ BM25 index built successfully")
            
        except Exception as e:
            logging.error(f"Failed to rebuild BM25 index: {e}")
            print(f"❌ Failed to build BM25 index: {e}")
        
    except Exception as e:
        logging.error(f"Failed to update BM25 index: {e}")
        print(f"❌ Failed to update BM25 index: {e}")


def sync_bm25_index() -> None:
    """Sync BM25 index with documents that exist in Chroma DB but are not BM25 indexed"""
    try:
        print("🔍 Checking for documents in Chroma DB that need BM25 indexing...")
        
        # Connect to Chroma DB
        db = Chroma(
            persist_directory=CHROMA_PATH,
            embedding_function=get_embedding()
        )
        
        # Get all document IDs from Chroma
        all_chroma_items = db.get(include=["documents", "metadatas"])
        
        if not all_chroma_items.get("ids"):
            print("❌ No documents found in Chroma DB. Nothing to sync.")
            return
            
        chroma_doc_ids = set(all_chroma_items["ids"])
        print(f"📊 Found {len(chroma_doc_ids)} documents in Chroma DB")
        
        # Initialize BM25 searcher and check existing index
        bm25_searcher = BM25KeywordSearcher(BM25_PATH)
        index_file = os.path.join(BM25_PATH, "bm25_index.pkl")
        metadata_file = os.path.join(BM25_PATH, "metadata.pkl")
        
        # Get existing BM25 document IDs
        bm25_doc_ids = set()
        if os.path.exists(index_file) and os.path.exists(metadata_file):
            try:
                bm25_searcher._load_index()
                bm25_doc_ids = set(bm25_searcher.doc_id_to_index.keys())
                print(f"📊 Found {len(bm25_doc_ids)} documents in BM25 index")
            except Exception as e:
                logging.warning(f"Failed to load existing BM25 index: {e}")
                print("⚠️  Could not load existing BM25 index, will rebuild from scratch")
        else:
            print("📝 No existing BM25 index found")
        
        # Find missing documents (in Chroma but not in BM25)
        missing_doc_ids = chroma_doc_ids - bm25_doc_ids
        
        if not missing_doc_ids:
            print("✅ All Chroma documents are already BM25 indexed. Nothing to sync!")
            return
            
        print(f"🔄 Found {len(missing_doc_ids)} documents that need BM25 indexing")
        
        # Retrieve missing documents from Chroma
        missing_documents = []
        for doc_id in tqdm.tqdm(missing_doc_ids, desc="Retrieving missing documents"):
            try:
                # Find the document in the full list
                doc_index = all_chroma_items["ids"].index(doc_id)
                content = all_chroma_items["documents"][doc_index]
                metadata = all_chroma_items["metadatas"][doc_index] if all_chroma_items.get("metadatas") else {}
                
                # Create Document object
                doc = Document(page_content=content, metadata=metadata)
                missing_documents.append(doc)
                
            except (ValueError, IndexError) as e:
                logging.warning(f"Failed to retrieve document {doc_id}: {e}")
                continue
        
        if not missing_documents:
            print("❌ Failed to retrieve any missing documents")
            return
            
        print(f"📄 Successfully retrieved {len(missing_documents)} missing documents")
        
        # Add missing documents to BM25 index
        print("🔨 Adding missing documents to BM25 index...")
        
        if bm25_doc_ids:
            # Existing index found, use incremental update
            bm25_searcher.add_documents(missing_documents)
        else:
            # No existing index, build from scratch with missing documents
            bm25_searcher.build_index(missing_documents, force_rebuild=True)
            
        print(f"✅ Successfully synced BM25 index with {len(missing_documents)} documents")
        print(f"📊 BM25 index now contains {len(bm25_searcher.documents)} total documents")
        
    except Exception as e:
        logging.error(f"Failed to sync BM25 index: {e}")
        print(f"❌ BM25 sync failed: {e}")
        raise


def clear_database() -> None:
    """Clear all databases and caches"""
    if os.path.exists(CHROMA_PATH):
        shutil.rmtree(CHROMA_PATH)
        print("🗑️  Cleared Chroma vector database")
    
    if os.path.exists(BM25_PATH):
        shutil.rmtree(BM25_PATH)
        print("🗑️  Cleared BM25 keyword index")
    
    if os.path.exists(HEADER_CACHE_PATH):
        os.remove(HEADER_CACHE_PATH)
        print("🗑️  Cleared header cache")


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
                
                # Also add to BM25 index
                try:
                    bm25_searcher = BM25KeywordSearcher(BM25_PATH)
                    bm25_searcher.add_documents(new_chunks)
                    logging.info(f"Added {len(new_chunks)} chunks to BM25 index")
                except Exception as e:
                    logging.warning(f"Failed to update BM25 index: {e}")
                    # Don't fail the entire process if BM25 update fails
                    
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