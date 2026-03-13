"""ML Worker configuration."""

import os
from pathlib import Path

# Model paths
MODELS_DIR = Path(os.getenv("MODELS_DIR", "/app/models"))

# Embedding model (ai-forever/ru-e5-small ONNX)
EMBEDDING_MODEL_DIR = MODELS_DIR / "ru-e5-small-onnx"
EMBEDDING_DIM = 384

# SLM model (Qwen2.5-0.5B-Instruct GGUF)
SLM_MODEL_PATH = MODELS_DIR / "qwen2.5-0.5b-instruct-q4_k_m.gguf"
SLM_CONTEXT_SIZE = 2048
SLM_MAX_TOKENS = 512

# IsolationForest
ISOLATION_FOREST_CONTAMINATION = "auto"
