"""Embedding service using sentence-transformers with pplx-embed model."""

import logging

import numpy as np
from sentence_transformers import SentenceTransformer

logger = logging.getLogger(__name__)


class Embedder:
    """Wraps sentence-transformers for pplx-embed-v1-0.6b (1024-dim)."""

    def __init__(self, model_name: str = "perplexity-ai/pplx-embed-v1-0.6b"):
        logger.info("Loading embedding model: %s", model_name)
        self.model = SentenceTransformer(model_name, trust_remote_code=True)
        logger.info("Embedding model loaded (dim=%d)", self.model.get_sentence_embedding_dimension())

    def encode(self, texts: list[str]) -> np.ndarray:
        """
        Encode texts into embeddings.

        Returns numpy array of shape (len(texts), 1024).
        """
        if not texts:
            return np.array([])

        embeddings = self.model.encode(
            texts,
            show_progress_bar=False,
            convert_to_numpy=True,
        )
        return embeddings

    def encode_single(self, text: str) -> list[float]:
        """Encode a single text and return as list of floats."""
        embedding = self.encode([text])
        return embedding[0].tolist()
