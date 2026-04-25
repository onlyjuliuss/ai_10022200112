"""
embedder.py - Custom Embedding Pipeline (Part B)
"""

import logging
import numpy as np
from typing import List, Union

logger = logging.getLogger(__name__)


def cosine_similarity(a: np.ndarray, b: np.ndarray) -> float:
    a = a / (np.linalg.norm(a) + 1e-9)
    b = b / (np.linalg.norm(b) + 1e-9)
    return float(np.dot(a, b))


def batch_cosine_similarity(query: np.ndarray, matrix: np.ndarray) -> np.ndarray:
    q     = query / (np.linalg.norm(query) + 1e-9)
    norms = np.linalg.norm(matrix, axis=1, keepdims=True) + 1e-9
    return (matrix / norms) @ q


class Embedder:
    def __init__(self, dim: int = 384):
        from sklearn.feature_extraction.text import TfidfVectorizer
        from sklearn.decomposition import TruncatedSVD
        self.dim        = dim
        self.vectorizer = TfidfVectorizer(
            max_features=8000,
            stop_words="english",
            ngram_range=(1, 2),
            sublinear_tf=True,
        )
        self.svd     = TruncatedSVD(n_components=dim, random_state=42)
        self._fitted = False
        logger.info(f"Embedder initialised (TF-IDF + SVD, dim={dim})")

    def fit(self, texts: List[str]):
        mat = self.vectorizer.fit_transform(texts)
        max_comp = min(self.dim, mat.shape[0] - 1, mat.shape[1] - 1)
        if max_comp < 1:
            max_comp = 1
        self.svd.n_components = max_comp
        self.svd.fit(mat)
        self._fitted     = True
        self._actual_dim = max_comp

    def embed(self, texts: Union[str, List[str]], batch_size: int = 32) -> np.ndarray:
        if isinstance(texts, str):
            texts = [texts]
        if not self._fitted:
            self.fit(texts)
        mat    = self.vectorizer.transform(texts)
        result = self.svd.transform(mat).astype("float32")
        if result.shape[1] < self.dim:
            pad    = np.zeros((result.shape[0], self.dim - result.shape[1]), dtype="float32")
            result = np.hstack([result, pad])
        norms  = np.linalg.norm(result, axis=1, keepdims=True) + 1e-9
        return (result / norms).astype("float32")

    def embed_single(self, text: str) -> np.ndarray:
        return self.embed([text])[0]