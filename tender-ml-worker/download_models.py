"""Script to download and prepare ML models.

Downloads:
1. ai-forever/ru-e5-small → exports to ONNX
2. Qwen2.5-0.5B-Instruct-GGUF (Q4_K_M)

Run: python download_models.py
"""

import os
import logging
from pathlib import Path

from huggingface_hub import hf_hub_download, snapshot_download

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

MODELS_DIR = Path(os.getenv("MODELS_DIR", "./models"))


def download_embedding_model() -> None:
    """Download ru-e5-small and its tokenizer for ONNX export."""
    output_dir = MODELS_DIR / "ru-e5-small-onnx"
    output_dir.mkdir(parents=True, exist_ok=True)

    if (output_dir / "model.onnx").exists():
        logger.info("Embedding ONNX model already exists, skipping")
        return

    logger.info("Downloading ai-forever/ru-e5-small for ONNX export...")

    # Download model files
    snapshot_download(
        repo_id="ai-forever/ru-e5-small",
        local_dir=str(output_dir / "original"),
        ignore_patterns=["*.bin", "*.safetensors"],
    )

    # Download tokenizer
    for fname in ["tokenizer.json", "tokenizer_config.json", "special_tokens_map.json"]:
        try:
            hf_hub_download(
                repo_id="ai-forever/ru-e5-small",
                filename=fname,
                local_dir=str(output_dir),
            )
        except Exception as e:
            logger.warning(f"Could not download {fname}: {e}")

    logger.info(
        f"Downloaded to {output_dir}. "
        f"Run `python export_onnx.py` to export model to ONNX format."
    )


def download_slm_model() -> None:
    """Download Qwen2.5-0.5B-Instruct GGUF model."""
    output_path = MODELS_DIR / "qwen2.5-0.5b-instruct-q4_k_m.gguf"

    if output_path.exists():
        logger.info("SLM GGUF model already exists, skipping")
        return

    logger.info("Downloading Qwen2.5-0.5B-Instruct GGUF (Q4_K_M)...")

    MODELS_DIR.mkdir(parents=True, exist_ok=True)

    hf_hub_download(
        repo_id="Qwen/Qwen2.5-0.5B-Instruct-GGUF",
        filename="qwen2.5-0.5b-instruct-q4_k_m.gguf",
        local_dir=str(MODELS_DIR),
    )

    logger.info(f"SLM model saved to {output_path}")


if __name__ == "__main__":
    MODELS_DIR.mkdir(parents=True, exist_ok=True)

    logger.info(f"Models directory: {MODELS_DIR.absolute()}")

    download_embedding_model()
    download_slm_model()

    logger.info("All models downloaded!")
