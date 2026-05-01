"""
retriever.py - Custom Retrieval System (Part B)
"""

import json
import logging
import numpy as np
import faiss
from pathlib import Path
from typing import List, Dict, Tuple, Optional
from rank_bm25 import BM25Okapi

from src.embedder import Embedder

logger = logging.getLogger(__name__)

INDEX_PATH  = Path("data/processed/faiss.index")
CHUNKS_PATH = Path("data/processed/chunks.json")


def load_chunks_json(chunks_path: Path) -> list:
    """Load chunks; tolerate legacy non-UTF8 bytes (e.g. lone 0xA0) in older exports."""
    raw = chunks_path.read_bytes()
    text = raw.decode("utf-8", errors="replace").replace("\ufffd", " ")
    return json.loads(text)


class VectorStore:
    """
    Manual FAISS-based vector store.
    Stores chunk texts alongside their embeddings for retrieval.
    """

    def __init__(self, dim: int = 384):
        self.dim    = dim
        self.index  = faiss.IndexFlatIP(dim)  # Inner product (cosine on normalised vecs)
        self.chunks: List[Dict] = []
        logger.info(f"VectorStore initialised (dim={dim})")

    def add(self, chunks: List[Dict], embeddings: np.ndarray):
        """Add chunks and their pre-computed embeddings to the index."""
        assert len(chunks) == embeddings.shape[0], "Chunk/embedding count mismatch"
        self.index.add(embeddings)
        self.chunks.extend(chunks)
        logger.info(f"VectorStore now holds {self.index.ntotal} vectors")

    def search(self, query_vec: np.ndarray, k: int = 5) -> List[Tuple[Dict, float]]:
        """
        Top-k cosine similarity search.

        Args:
            query_vec: L2-normalised query embedding (1, dim) or (dim,)
            k: number of results

        Returns:
            List of (chunk_dict, similarity_score) tuples, sorted descending.
        """
        if query_vec.ndim == 1:
            query_vec = query_vec.reshape(1, -1)
        k = min(k, self.index.ntotal)
        scores, indices = self.index.search(query_vec, k)
        results = []
        for score, idx in zip(scores[0], indices[0]):
            if idx >= 0:
                results.append((self.chunks[idx], float(score)))
        return results

    def save(self, index_path: Path = INDEX_PATH, chunks_path: Path = CHUNKS_PATH):
        index_path.parent.mkdir(parents=True, exist_ok=True)
        faiss.write_index(self.index, str(index_path))
        with open(chunks_path, "w", encoding="utf-8") as f:
            json.dump(self.chunks, f, ensure_ascii=False, indent=2)
        logger.info(f"Saved FAISS index → {index_path}")

    @classmethod
    def load(cls, index_path: Path = INDEX_PATH, chunks_path: Path = CHUNKS_PATH) -> "VectorStore":
        store = cls()
        store.index = faiss.read_index(str(index_path))
        store.chunks = load_chunks_json(chunks_path)
        logger.info(f"Loaded FAISS index: {store.index.ntotal} vectors, {len(store.chunks)} chunks")
        return store


class BM25Index:
    """
    Keyword-based BM25 index for the hybrid search component.
    Tokenises by whitespace/punctuation (simple but effective for this domain).
    """

    def __init__(self):
        self.corpus_tokens: List[List[str]] = []
        self.chunks: List[Dict] = []
        self.bm25: Optional[BM25Okapi] = None

    def build(self, chunks: List[Dict]):
        self.chunks = chunks
        self.corpus_tokens = [self._tokenise(c["text"]) for c in chunks]
        self.bm25 = BM25Okapi(self.corpus_tokens)
        logger.info(f"BM25 index built on {len(chunks)} docs")

    def _tokenise(self, text: str) -> List[str]:
        return text.lower().split()

    def search(self, query: str, k: int = 5) -> List[Tuple[Dict, float]]:
        tokens = self._tokenise(query)
        scores = self.bm25.get_scores(tokens)
        top_k  = np.argsort(scores)[::-1][:k]
        return [(self.chunks[i], float(scores[i])) for i in top_k if scores[i] > 0]


class HybridRetriever:
    """
    Hybrid retrieval: combines BM25 (keyword) and FAISS (vector) results
    using Reciprocal Rank Fusion (RRF).

    RRF formula: score(d) = Σ 1 / (k + rank(d))   where k=60
    This is robust to score-scale differences between BM25 and cosine similarity.
    """

    def __init__(self, vector_store: VectorStore, bm25_index: BM25Index, embedder: Embedder):
        self.vs      = vector_store
        self.bm25    = bm25_index
        self.embedder = embedder

    # ── Query Expansion ────────────────────────────────────────────────────────
    def expand_query(self, query: str) -> str:
        """
        Simple rule-based query expansion for the Ghana/Budget domain.
        Adds domain synonyms to improve recall.
        """
        expansions = {
            "election":  ["election", "voting", "results", "presidential"],
            "budget":    ["budget", "fiscal", "expenditure", "revenue", "2025"],
            "education": ["education", "schools", "universities", "teachers", "students", "learning"],
            "npp":       ["NPP", "New Patriotic Party"],
            "ndc":       ["NDC", "National Democratic Congress"],
            "gdp":       ["GDP", "gross domestic product", "economic growth"],
            "inflation": ["inflation", "prices", "cost of living"],
            "winner":    ["winner", "won", "elected", "victory", "votes"],
            "ghana":     ["Ghana", "republic of ghana"],
        }
        query_lower = query.lower()
        extra = []
        for keyword, synonyms in expansions.items():
            if keyword in query_lower:
                extra.extend(synonyms)
        if extra:
            expanded = query + " " + " ".join(set(extra))
            logger.info(f"Query expanded: '{query}' -> '{expanded}'")
            return expanded
        return query

    def retrieve(
        self,
        query: str,
        k: int = 5,
        vector_weight: float = 0.7,
        keyword_weight: float = 0.3,
        expand: bool = True,
    ) -> List[Dict]:
        """
        Full hybrid retrieval pipeline.

        1. Optional query expansion
        2. Vector search (top 2k candidates)
        3. BM25 keyword search (top 2k candidates)
        4. Reciprocal Rank Fusion to merge rankings
        5. Return top-k with scores and provenance

        Args:
            query:          User's natural language question
            k:              Number of final results to return
            vector_weight:  Weight for vector similarity in RRF (0-1)
            keyword_weight: Weight for BM25 in RRF (0-1)
            expand:         Whether to apply query expansion

        Returns:
            List of result dicts with 'text', 'source', 'score', 'rank_method'
        """
        if expand:
            expanded_query = self.expand_query(query)
        else:
            expanded_query = query

        # ── Vector search ──────────────────────────────────────────────────
        q_vec = self.embedder.embed_single(expanded_query)
        vector_results = self.vs.search(q_vec, k=k * 2)

        # ── BM25 keyword search ────────────────────────────────────────────
        keyword_results = self.bm25.search(expanded_query, k=k * 2)

        # ── Reciprocal Rank Fusion ─────────────────────────────────────────
        rrf_k   = 60
        scores  = {}  # chunk_id → fused RRF score

        # Extract year from query for targeted boosting
        import re
        year_match = re.search(r'\b(20\d{2})\b', query)
        query_year = year_match.group(1) if year_match else None
        education_terms = {"education", "school", "teacher", "student", "learning", "university", "curriculum"}
        query_lower = query.lower()
        query_education = any(term in query_lower for term in education_terms)

        def chunk_id(chunk):
            return chunk.get("id", chunk["text"][:50])

        for rank, (chunk, _score) in enumerate(vector_results):
            cid = chunk_id(chunk)
            scores[cid] = scores.get(cid, {"chunk": chunk, "rrf": 0.0, "methods": []})
            base_score = vector_weight / (rrf_k + rank + 1)
            # Boost summary chunks, especially those matching query year
            boost = 1.0
            if chunk.get("type") in ("election_summary", "budget_data"):
                boost *= 50.0
                if query_year and query_year in chunk.get("id", ""):
                    boost *= 10.0  # Additional 10x boost for year match
            if query_education:
                chunk_text = chunk.get("text", "").lower()
                if any(term in chunk_text for term in education_terms):
                    boost *= 4.0
            base_score *= boost
            scores[cid]["rrf"] += base_score
            scores[cid]["methods"].append("vector")

        for rank, (chunk, _score) in enumerate(keyword_results):
            cid = chunk_id(chunk)
            if cid not in scores:
                scores[cid] = {"chunk": chunk, "rrf": 0.0, "methods": []}
            base_score = keyword_weight / (rrf_k + rank + 1)
            # Boost summary chunks, especially those matching query year
            boost = 1.0
            if chunk.get("type") in ("election_summary", "budget_data"):
                boost *= 50.0
                if query_year and query_year in chunk.get("id", ""):
                    boost *= 10.0  # Additional 10x boost for year match
            if query_education:
                chunk_text = chunk.get("text", "").lower()
                if any(term in chunk_text for term in education_terms):
                    boost *= 2.0
            base_score *= boost
            scores[cid]["rrf"] += base_score
            if "keyword" not in scores[cid]["methods"]:
                scores[cid]["methods"].append("keyword")

        # Sort by fused score
        ranked = sorted(scores.values(), key=lambda x: x["rrf"], reverse=True)[:k]

        results = []
        for item in ranked:
            chunk = item["chunk"].copy()
            chunk["score"]       = round(item["rrf"], 6)
            chunk["rank_method"] = "+".join(item["methods"])
            results.append(chunk)

        logger.info(f"Retrieved {len(results)} chunks for query: '{query[:60]}...'")
        return results

    # ── Failure analysis ───────────────────────────────────────────────────────
    def detect_low_confidence(self, results: List[Dict], threshold: float = 0.001) -> bool:
        """
        Failure case: retrieval returns low-confidence / irrelevant results.
        Fix: flag to caller so it can fall back to a broader search or
             inform the user that the answer may not be in the knowledge base.
        """
        if not results:
            return True
        top_score = results[0].get("score", 0)
        return top_score < threshold


# ── Index builder ─────────────────────────────────────────────────────────────
def build_index(chunks: List[Dict], embedder: Embedder) -> Tuple[VectorStore, BM25Index]:
    """
    Build FAISS + BM25 indices from chunks.
    Called once after ingestion; results saved to disk.
    """
    logger.info(f"Building indices for {len(chunks)} chunks...")
    texts = [c["text"] for c in chunks]

    # Embed in batches
    logger.info("Embedding chunks (this may take a few minutes)...")
    embeddings = embedder.embed(texts, batch_size=64)

    vs = VectorStore(dim=embeddings.shape[1])
    vs.add(chunks, embeddings)
    vs.save()

    bm25 = BM25Index()
    bm25.build(chunks)

    logger.info("Index building complete.")
    return vs, bm25


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    from src.ingest import run_ingestion

    chunks   = run_ingestion()
    embedder = Embedder()
    vs, bm25 = build_index(chunks, embedder)
    retriever = HybridRetriever(vs, bm25, embedder)

    test_query = "Who won the 2024 presidential election in Ghana?"
    results    = retriever.retrieve(test_query, k=3)
    for i, r in enumerate(results, 1):
        print(f"\n--- Result {i} (score={r['score']}) ---")
        print(r["text"][:200])
