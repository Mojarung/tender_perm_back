"""Embedding service using ai-forever/ru-e5-small via ONNX Runtime.

Model: ai-forever/ru-e5-small
Format: ONNX (INT8 quantization)
Runtime: onnxruntime (CPU)
Dimension: 384
"""

import logging
from pathlib import Path

import numpy as np
import onnxruntime as ort
from tokenizers import Tokenizer

from config import EMBEDDING_MODEL_DIR, EMBEDDING_DIM

logger = logging.getLogger(__name__)


class EmbeddingService:
    """Generates text embeddings via ONNX-exported ru-e5-small model."""

    def __init__(self) -> None:
        self._session: ort.InferenceSession | None = None
        self._tokenizer: Tokenizer | None = None
        self._loaded = False

    def load(self) -> None:
        """Load ONNX model and tokenizer from disk."""
        model_path = EMBEDDING_MODEL_DIR / "model.onnx"
        tokenizer_path = EMBEDDING_MODEL_DIR / "tokenizer.json"

        if not model_path.exists():
            raise FileNotFoundError(
                f"ONNX model not found at {model_path}. "
                f"Export ru-e5-small to ONNX first."
            )

        logger.info(f"Loading ONNX embedding model from {model_path}...")

        # CPU-only session options
        sess_options = ort.SessionOptions()
        sess_options.graph_optimization_level = ort.GraphOptimizationLevel.ORT_ENABLE_ALL
        sess_options.intra_op_num_threads = 4

        self._session = ort.InferenceSession(
            str(model_path),
            sess_options,
            providers=["CPUExecutionProvider"],
        )

        self._tokenizer = Tokenizer.from_file(str(tokenizer_path))
        self._tokenizer.enable_truncation(max_length=512)
        self._tokenizer.enable_padding(length=512)

        self._loaded = True
        logger.info("Embedding model loaded successfully")

    @property
    def is_loaded(self) -> bool:
        return self._loaded

    def embed(self, text: str) -> list[float]:
        """
        Generate embedding for a single text.

        Steps:
        1. Tokenize text
        2. Run ONNX inference
        3. Mean pooling over token embeddings
        4. L2 normalization
        """
        if not self._loaded:
            raise RuntimeError("Embedding model not loaded. Call load() first.")

        # Tokenize
        encoded = self._tokenizer.encode(text)
        input_ids = np.array([encoded.ids], dtype=np.int64)
        attention_mask = np.array([encoded.attention_mask], dtype=np.int64)
        token_type_ids = np.zeros_like(input_ids, dtype=np.int64)

        # ONNX inference
        outputs = self._session.run(
            None,
            {
                "input_ids": input_ids,
                "attention_mask": attention_mask,
                "token_type_ids": token_type_ids,
            },
        )

        # outputs[0] shape: (1, seq_len, hidden_dim)
        token_embeddings = outputs[0]

        # Mean pooling with attention mask
        mask_expanded = attention_mask[:, :, np.newaxis].astype(np.float32)
        sum_embeddings = np.sum(token_embeddings * mask_expanded, axis=1)
        sum_mask = np.sum(mask_expanded, axis=1)
        sum_mask = np.clip(sum_mask, a_min=1e-9, a_max=None)
        mean_pooled = sum_embeddings / sum_mask

        # L2 normalization
        norm = np.linalg.norm(mean_pooled, axis=1, keepdims=True)
        norm = np.clip(norm, a_min=1e-9, a_max=None)
        normalized = mean_pooled / norm

        return normalized[0].tolist()

    def embed_batch(self, texts: list[str]) -> list[list[float]]:
        """Generate embeddings for a batch of texts."""
        return [self.embed(text) for text in texts]


# Singleton
embedding_service = EmbeddingService()
