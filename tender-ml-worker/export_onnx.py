"""Export ai-forever/ru-e5-small to ONNX format with INT8 quantization.

Run this AFTER download_models.py:
  python export_onnx.py

Requires: torch, transformers, onnx, onnxruntime
"""

import logging
from pathlib import Path

import torch
import numpy as np
from transformers import AutoModel, AutoTokenizer

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

MODELS_DIR = Path("./models")
INPUT_DIR = MODELS_DIR / "ru-e5-small-onnx" / "original"
OUTPUT_DIR = MODELS_DIR / "ru-e5-small-onnx"


def export_to_onnx() -> None:
    """Export the model to ONNX format."""
    output_path = OUTPUT_DIR / "model.onnx"

    if output_path.exists():
        logger.info("ONNX model already exists, skipping export")
        return

    logger.info("Loading PyTorch model for ONNX export...")
    tokenizer = AutoTokenizer.from_pretrained("ai-forever/ru-e5-small")
    model = AutoModel.from_pretrained("ai-forever/ru-e5-small")
    model.eval()

    # Save tokenizer
    tokenizer.save_pretrained(str(OUTPUT_DIR))

    # Dummy input
    dummy_text = "Пример текста для экспорта"
    inputs = tokenizer(
        dummy_text,
        return_tensors="pt",
        padding="max_length",
        max_length=512,
        truncation=True,
    )

    logger.info("Exporting to ONNX...")
    torch.onnx.export(
        model,
        (inputs["input_ids"], inputs["attention_mask"], inputs["token_type_ids"]),
        str(output_path),
        input_names=["input_ids", "attention_mask", "token_type_ids"],
        output_names=["last_hidden_state"],
        dynamic_axes={
            "input_ids": {0: "batch", 1: "sequence"},
            "attention_mask": {0: "batch", 1: "sequence"},
            "token_type_ids": {0: "batch", 1: "sequence"},
            "last_hidden_state": {0: "batch", 1: "sequence"},
        },
        opset_version=14,
    )

    logger.info(f"ONNX model exported to {output_path}")

    # Optional: quantize to INT8
    try:
        from onnxruntime.quantization import quantize_dynamic, QuantType

        quantized_path = OUTPUT_DIR / "model_int8.onnx"
        quantize_dynamic(
            str(output_path),
            str(quantized_path),
            weight_type=QuantType.QInt8,
        )
        logger.info(f"INT8 quantized model saved to {quantized_path}")

        # Replace original with quantized
        output_path.unlink()
        quantized_path.rename(output_path)
        logger.info("Replaced original with INT8 quantized version")
    except ImportError:
        logger.warning("onnxruntime.quantization not available, skipping INT8 quantization")


if __name__ == "__main__":
    export_to_onnx()
