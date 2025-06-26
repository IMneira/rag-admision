"""
Hybrid Search Module for Advanced RAG
Combines semantic search (via Chroma) with keyword search (via BM25) for better retrieval accuracy.
"""

import os
import pickle
import logging
import re
from typing import List, Dict, Tuple, Optional, Union
from dataclasses import dataclass
from concurrent.futures import ThreadPoolExecutor, as_completed
import time

import nltk
from nltk.corpus import stopwords
from nltk.stem import SnowballStemmer
from rank_bm25 import BM25Okapi

from langchain.schema.document import Document
from langchain_chroma import Chroma
from app.services.rag.embedding import get_embedding


@dataclass
class SearchResult:
    """Unified search result with document and score"""
    document: Document
    score: float
    search_type: str  # 'semantic', 'keyword', or 'hybrid'
    rank: int


class SpanishTextProcessor:
    """Text processor optimized for Spanish university admission documents"""
    
    def __init__(self):
        # Download required NLTK data
        try:
            nltk.data.find('corpora/stopwords')
        except LookupError:
            nltk.download('stopwords')
        
        try:
            nltk.data.find('tokenizers/punkt')
        except LookupError:
            nltk.download('punkt')
        
        # Initialize Spanish stemmer and stopwords
        self.stemmer = SnowballStemmer('spanish')
        self.spanish_stopwords = set(stopwords.words('spanish'))
        
        # Add domain-specific stopwords
        self.domain_stopwords = {
            'universidad', 'carrera', 'estudiante', 'alumno', 'programa',
            'documento', 'información', 'proceso', 'sistema'
        }
        self.all_stopwords = self.spanish_stopwords.union(self.domain_stopwords)
        
        # Important terms that should NOT be stemmed (preserve exact matching)
        self.preserve_terms = {
            'psu', 'paes', 'nem', 'ranking', 'admision', 'postulacion',
            'matricula', 'inscripcion', 'requisitos', 'documentos'
        }

    def preprocess_text(self, text: str, enable_stemming: bool = True) -> List[str]:
        """Preprocess text for BM25 indexing"""
        if not text:
            return []
        
        # Convert to lowercase
        text = text.lower()
        
        # Remove special characters but keep Spanish accents
        text = re.sub(r'[^\w\sáéíóúüñ]', ' ', text)
        
        # Tokenize
        tokens = text.split()
        
        # Filter tokens
        processed_tokens = []
        for token in tokens:
            # Skip very short tokens
            if len(token) < 2:
                continue
            
            # Skip stopwords
            if token in self.all_stopwords:
                continue
            
            # Apply stemming if enabled and not a preserved term
            if enable_stemming and token not in self.preserve_terms:
                token = self.stemmer.stem(token)
            
            processed_tokens.append(token)
        
        return processed_tokens

    def preprocess_query(self, query: str) -> str:
        """Preprocess query for BM25 search"""
        tokens = self.preprocess_text(query, enable_stemming=True)
        return ' '.join(tokens)


class BM25KeywordSearcher:
    """BM25-based keyword search implementation"""
    
    def __init__(self, index_path: str = "bm25_index"):
        self.index_path = index_path
        self.text_processor = SpanishTextProcessor()
        self.bm25_index = None
        self.documents = []
        self.document_tokens = []
        self.doc_id_to_index = {}
        
    def build_index(self, documents: List[Document], force_rebuild: bool = False):
        """Build BM25 index from documents"""
        index_file = os.path.join(self.index_path, "bm25_index.pkl")
        metadata_file = os.path.join(self.index_path, "metadata.pkl")
        
        # Load existing index if available and not forcing rebuild
        if not force_rebuild and os.path.exists(index_file) and os.path.exists(metadata_file):
            try:
                self._load_index()
                logging.info(f"Loaded existing BM25 index with {len(self.documents)} documents")
                return
            except Exception as e:
                logging.warning(f"Failed to load existing index: {e}. Rebuilding...")
        
        logging.info(f"Building BM25 index for {len(documents)} documents...")
        start_time = time.time()
        
        # Reset state
        self.documents = []
        self.document_tokens = []
        self.doc_id_to_index = {}
        
        # Process documents
        for i, doc in enumerate(documents):
            try:
                # Preprocess document text
                tokens = self.text_processor.preprocess_text(doc.page_content)
                
                if tokens:  # Only add documents with content
                    self.documents.append(doc)
                    self.document_tokens.append(tokens)
                    
                    # Map document ID to index
                    doc_id = doc.metadata.get('id', f'doc_{i}')
                    self.doc_id_to_index[doc_id] = len(self.documents) - 1
                    
            except Exception as e:
                logging.warning(f"Failed to process document {i}: {e}")
                continue
        
        # Build BM25 index
        if self.document_tokens:
            self.bm25_index = BM25Okapi(self.document_tokens)
            
            # Save index
            self._save_index()
            
            build_time = time.time() - start_time
            logging.info(f"BM25 index built successfully in {build_time:.2f}s with {len(self.documents)} documents")
        else:
            logging.error("No valid documents found for BM25 indexing")

    def search(self, query: str, k: int = 10) -> List[SearchResult]:
        """Search using BM25"""
        if not self.bm25_index:
            logging.warning("BM25 index not available")
            return []
        
        try:
            # Preprocess query
            processed_query = self.text_processor.preprocess_text(query)
            
            if not processed_query:
                return []
            
            # Get BM25 scores
            scores = self.bm25_index.get_scores(processed_query)
            
            # Get top k results
            top_indices = scores.argsort()[-k:][::-1]
            
            results = []
            for rank, idx in enumerate(top_indices):
                if idx < len(self.documents) and scores[idx] > 0:
                    result = SearchResult(
                        document=self.documents[idx],
                        score=float(scores[idx]),
                        search_type='keyword',
                        rank=rank
                    )
                    results.append(result)
            
            return results
            
        except Exception as e:
            logging.error(f"BM25 search failed: {e}")
            return []

    def _save_index(self):
        """Save BM25 index to disk"""
        try:
            os.makedirs(self.index_path, exist_ok=True)
            
            # Save BM25 index
            with open(os.path.join(self.index_path, "bm25_index.pkl"), "wb") as f:
                pickle.dump({
                    'bm25_index': self.bm25_index,
                    'document_tokens': self.document_tokens
                }, f)
            
            # Save metadata
            with open(os.path.join(self.index_path, "metadata.pkl"), "wb") as f:
                pickle.dump({
                    'documents': self.documents,
                    'doc_id_to_index': self.doc_id_to_index
                }, f)
                
            logging.info("BM25 index saved successfully")
            
        except Exception as e:
            logging.error(f"Failed to save BM25 index: {e}")

    def _load_index(self):
        """Load BM25 index from disk"""
        # Load BM25 index
        with open(os.path.join(self.index_path, "bm25_index.pkl"), "rb") as f:
            data = pickle.load(f)
            self.bm25_index = data['bm25_index']
            self.document_tokens = data['document_tokens']
        
        # Load metadata
        with open(os.path.join(self.index_path, "metadata.pkl"), "rb") as f:
            data = pickle.load(f)
            self.documents = data['documents']
            self.doc_id_to_index = data['doc_id_to_index']

    def add_documents(self, new_documents: List[Document]):
        """Add new documents to existing index"""
        if not self.bm25_index:
            # If no index exists, build from scratch
            self.build_index(new_documents)
            return
        
        # Process new documents
        new_doc_tokens = []
        for doc in new_documents:
            try:
                tokens = self.text_processor.preprocess_text(doc.page_content)
                if tokens:
                    self.documents.append(doc)
                    new_doc_tokens.append(tokens)
                    
                    # Update mapping
                    doc_id = doc.metadata.get('id', f'doc_{len(self.documents)-1}')
                    self.doc_id_to_index[doc_id] = len(self.documents) - 1
                    
            except Exception as e:
                logging.warning(f"Failed to process new document: {e}")
                continue
        
        if new_doc_tokens:
            # Rebuild index with all documents (BM25 doesn't support incremental updates)
            self.document_tokens.extend(new_doc_tokens)
            self.bm25_index = BM25Okapi(self.document_tokens)
            self._save_index()
            logging.info(f"Added {len(new_doc_tokens)} new documents to BM25 index")


class SemanticSearcher:
    """Wrapper for semantic search via Chroma"""
    
    def __init__(self, chroma_path: str = "chroma"):
        self.chroma_path = chroma_path
        self.embedding_function = get_embedding()
        self.db = Chroma(
            persist_directory=chroma_path,
            embedding_function=self.embedding_function
        )

    def search(self, query: str, k: int = 10) -> List[SearchResult]:
        """Search using semantic similarity"""
        try:
            docs_with_scores = self.db.similarity_search_with_score(query, k=k)
            
            results = []
            for rank, (doc, score) in enumerate(docs_with_scores):
                # Convert distance to similarity (Chroma returns distance, lower is better)
                similarity_score = 1.0 / (1.0 + score)
                
                result = SearchResult(
                    document=doc,
                    score=similarity_score,
                    search_type='semantic',
                    rank=rank
                )
                results.append(result)
            
            return results
            
        except Exception as e:
            logging.error(f"Semantic search failed: {e}")
            return []


class ResultFusion:
    """Algorithms for fusing semantic and keyword search results"""
    
    @staticmethod
    def reciprocal_rank_fusion(semantic_results: List[SearchResult],
                              keyword_results: List[SearchResult],
                              k: int = 60) -> List[SearchResult]:
        """
        Reciprocal Rank Fusion (RRF) algorithm
        Formula: RRF(d) = Σ 1/(k + rank_i(d))
        """
        fused_scores = {}
        doc_objects = {}
        
        # Process semantic results
        for rank, result in enumerate(semantic_results):
            doc_id = result.document.metadata.get('id', f'semantic_{rank}')
            rrf_score = 1.0 / (k + rank + 1)
            fused_scores[doc_id] = fused_scores.get(doc_id, 0) + rrf_score
            doc_objects[doc_id] = result.document
        
        # Process keyword results
        for rank, result in enumerate(keyword_results):
            doc_id = result.document.metadata.get('id', f'keyword_{rank}')
            rrf_score = 1.0 / (k + rank + 1)
            fused_scores[doc_id] = fused_scores.get(doc_id, 0) + rrf_score
            doc_objects[doc_id] = result.document
        
        # Sort by fused score
        sorted_docs = sorted(fused_scores.items(), key=lambda x: x[1], reverse=True)
        
        # Create fused results
        fused_results = []
        for rank, (doc_id, score) in enumerate(sorted_docs):
            if doc_id in doc_objects:
                result = SearchResult(
                    document=doc_objects[doc_id],
                    score=score,
                    search_type='hybrid',
                    rank=rank
                )
                fused_results.append(result)
        
        return fused_results

    @staticmethod
    def weighted_score_fusion(semantic_results: List[SearchResult],
                             keyword_results: List[SearchResult],
                             semantic_weight: float = 0.6,
                             keyword_weight: float = 0.4) -> List[SearchResult]:
        """
        Weighted score fusion based on normalized scores
        """
        # Normalize scores
        semantic_scores = ResultFusion._normalize_scores([r.score for r in semantic_results])
        keyword_scores = ResultFusion._normalize_scores([r.score for r in keyword_results])
        
        fused_scores = {}
        doc_objects = {}
        
        # Process semantic results
        for i, result in enumerate(semantic_results):
            doc_id = result.document.metadata.get('id', f'semantic_{i}')
            score = semantic_scores[i] * semantic_weight
            fused_scores[doc_id] = fused_scores.get(doc_id, 0) + score
            doc_objects[doc_id] = result.document
        
        # Process keyword results
        for i, result in enumerate(keyword_results):
            doc_id = result.document.metadata.get('id', f'keyword_{i}')
            score = keyword_scores[i] * keyword_weight
            fused_scores[doc_id] = fused_scores.get(doc_id, 0) + score
            doc_objects[doc_id] = result.document
        
        # Sort by fused score
        sorted_docs = sorted(fused_scores.items(), key=lambda x: x[1], reverse=True)
        
        # Create fused results
        fused_results = []
        for rank, (doc_id, score) in enumerate(sorted_docs):
            if doc_id in doc_objects:
                result = SearchResult(
                    document=doc_objects[doc_id],
                    score=score,
                    search_type='hybrid',
                    rank=rank
                )
                fused_results.append(result)
        
        return fused_results

    @staticmethod
    def _normalize_scores(scores: List[float]) -> List[float]:
        """Normalize scores to 0-1 range"""
        if not scores:
            return []
        
        min_score = min(scores)
        max_score = max(scores)
        
        if max_score == min_score:
            return [1.0] * len(scores)
        
        return [(score - min_score) / (max_score - min_score) for score in scores]


class HybridSearcher:
    """Main hybrid search interface combining semantic and keyword search"""
    
    def __init__(self, chroma_path: str = "chroma", bm25_path: str = "bm25_index"):
        self.semantic_searcher = SemanticSearcher(chroma_path)
        self.keyword_searcher = BM25KeywordSearcher(bm25_path)
        self.fusion_engine = ResultFusion()
        
        # Configuration
        self.config = {
            'semantic_weight': 0.6,
            'keyword_weight': 0.4,
            'rrf_k': 60,
            'parallel_search': True,
            'fusion_method': 'rrf'  # 'rrf' or 'weighted'
        }
        
        # Query-type specific weights
        self.query_type_weights = {
            'factual': {'semantic': 0.4, 'keyword': 0.6},
            'procedural': {'semantic': 0.7, 'keyword': 0.3},
            'comparative': {'semantic': 0.6, 'keyword': 0.4},
            'temporal': {'semantic': 0.3, 'keyword': 0.7},
            'location': {'semantic': 0.4, 'keyword': 0.6},
            'requirement': {'semantic': 0.5, 'keyword': 0.5},
            'general': {'semantic': 0.6, 'keyword': 0.4}
        }

    def search(self, query: str, k: int = 10, query_type: str = 'general') -> List[Document]:
        """
        Perform hybrid search combining semantic and keyword results
        
        Args:
            query: Search query
            k: Number of results to return
            query_type: Type of query for weight optimization
            
        Returns:
            List of documents ranked by hybrid score
        """
        try:
            if self.config['parallel_search']:
                # Parallel search execution
                semantic_results, keyword_results = self._parallel_search(query, k)
            else:
                # Sequential search execution
                semantic_results = self.semantic_searcher.search(query, k)
                keyword_results = self.keyword_searcher.search(query, k)
            
            # Fuse results
            if self.config['fusion_method'] == 'rrf':
                fused_results = self.fusion_engine.reciprocal_rank_fusion(
                    semantic_results, keyword_results, self.config['rrf_k']
                )
            else:
                # Use query-type specific weights
                weights = self.query_type_weights.get(query_type, self.query_type_weights['general'])
                fused_results = self.fusion_engine.weighted_score_fusion(
                    semantic_results, keyword_results,
                    weights['semantic'], weights['keyword']
                )
            
            # Extract documents and return top k
            documents = [result.document for result in fused_results[:k]]
            
            logging.info(f"Hybrid search completed: {len(semantic_results)} semantic + {len(keyword_results)} keyword = {len(documents)} fused results")
            return documents
            
        except Exception as e:
            logging.error(f"Hybrid search failed: {e}")
            # Fallback to semantic search only
            try:
                semantic_results = self.semantic_searcher.search(query, k)
                return [result.document for result in semantic_results]
            except Exception as fallback_error:
                logging.error(f"Fallback search also failed: {fallback_error}")
                return []

    def _parallel_search(self, query: str, k: int) -> Tuple[List[SearchResult], List[SearchResult]]:
        """Execute semantic and keyword search in parallel"""
        semantic_results = []
        keyword_results = []
        
        with ThreadPoolExecutor(max_workers=2) as executor:
            # Submit both searches
            semantic_future = executor.submit(self.semantic_searcher.search, query, k)
            keyword_future = executor.submit(self.keyword_searcher.search, query, k)
            
            # Collect results
            for future in as_completed([semantic_future, keyword_future]):
                try:
                    if future == semantic_future:
                        semantic_results = future.result()
                    else:
                        keyword_results = future.result()
                except Exception as e:
                    logging.warning(f"Parallel search task failed: {e}")
        
        return semantic_results, keyword_results

    def build_keyword_index(self, documents: List[Document], force_rebuild: bool = False):
        """Build BM25 keyword index"""
        self.keyword_searcher.build_index(documents, force_rebuild)

    def add_documents(self, documents: List[Document]):
        """Add new documents to both indexes"""
        self.keyword_searcher.add_documents(documents)

    def update_config(self, **kwargs):
        """Update hybrid search configuration"""
        self.config.update(kwargs)

    def get_stats(self) -> Dict:
        """Get hybrid search statistics"""
        return {
            'config': self.config.copy(),
            'bm25_documents': len(self.keyword_searcher.documents),
            'query_type_weights': self.query_type_weights.copy()
        }


def test_hybrid_search():
    """Test hybrid search functionality"""
    # Create test documents
    test_docs = [
        Document(
            page_content="Los requisitos de admisión incluyen PSU mínimo 450 puntos, certificado de enseñanza media y ranking de notas.",
            metadata={'id': 'req_001', 'source': 'requisitos.md'}
        ),
        Document(
            page_content="El proceso de postulación se realiza entre diciembre y enero. Debes completar el formulario online.",
            metadata={'id': 'proc_001', 'source': 'proceso.md'}
        ),
        Document(
            page_content="La PSU se reemplazó por la PAES a partir del año 2022. Ambas evalúan competencias académicas.",
            metadata={'id': 'info_001', 'source': 'cambios.md'}
        )
    ]
    
    # Initialize hybrid searcher
    searcher = HybridSearcher()
    
    # Build indexes
    print("Building BM25 index...")
    searcher.build_keyword_index(test_docs, force_rebuild=True)
    
    # Test queries
    test_queries = [
        ("requisitos admisión PSU", "requirement"),
        ("proceso postulación fechas", "procedural"),
        ("diferencia PSU PAES", "comparative")
    ]
    
    for query, query_type in test_queries:
        print(f"\n{'='*50}")
        print(f"Query: {query} (Type: {query_type})")
        
        # Perform hybrid search
        results = searcher.search(query, k=3, query_type=query_type)
        
        print(f"Results: {len(results)} documents")
        for i, doc in enumerate(results):
            print(f"{i+1}. {doc.metadata.get('source', 'unknown')}: {doc.page_content[:100]}...")
    
    # Print statistics
    print(f"\n{'='*50}")
    print("Hybrid Search Statistics:")
    stats = searcher.get_stats()
    for key, value in stats.items():
        print(f"{key}: {value}")


if __name__ == "__main__":
    test_hybrid_search()