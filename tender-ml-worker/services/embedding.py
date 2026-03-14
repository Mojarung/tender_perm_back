import numpy as np
import onnxruntime as ort
from transformers import AutoTokenizer
import os

MODEL_DIR = os.getenv("EMBEDDING_MODEL_DIR", "../model_weights/ru-e5-small-onnx")

try:
    if not os.path.exists(MODEL_DIR):
        print(f"Warning: Embedding model directory not found at {MODEL_DIR}")
        tokenizer, session = None, None
    else:
        tokenizer = AutoTokenizer.from_pretrained(MODEL_DIR)
        session = ort.InferenceSession(os.path.join(MODEL_DIR, "model.onnx"))
except Exception as e:
    print(f"Failed to load ONNX model: {e}")
    tokenizer, session = None, None

def embed_text(text: str) -> list[float]:
    """
    Executes multilingual-e5-small via ONNX Runtime to generate a 384-dimensional text embedding.
    """
    if tokenizer is None or session is None:
        # Fallback deterministic dummy vector
        np.random.seed(len(text) % 10000)
        vector = np.random.randn(384).tolist()
    else:
        # e5 models expect prefixes
        inputs = tokenizer(f"query: {text}", return_tensors="np", padding=True, truncation=True, max_length=512)
        onnx_inputs = {
            "input_ids": inputs["input_ids"].astype(np.int64),
            "attention_mask": inputs["attention_mask"].astype(np.int64)
        }
        if "token_type_ids" in inputs:
            onnx_inputs["token_type_ids"] = inputs["token_type_ids"].astype(np.int64)
        else:
            onnx_inputs["token_type_ids"] = np.zeros_like(inputs["input_ids"]).astype(np.int64)
            
        outputs = session.run(None, onnx_inputs)
        token_embeddings = outputs[0]
        attention_mask = inputs["attention_mask"]
        
        input_mask_expanded = np.repeat(attention_mask[:, :, np.newaxis], token_embeddings.shape[-1], axis=-1)
        sum_embeddings = np.sum(token_embeddings * input_mask_expanded, axis=1)
        sum_mask = np.clip(np.sum(input_mask_expanded, axis=1), a_min=1e-9, a_max=None)
        mean_pooled = sum_embeddings / sum_mask
        vector = mean_pooled[0].tolist()

    # L2 Normalization (required for e5 models)
    norm = np.linalg.norm(vector)
    vector = [float(v / norm) for v in vector]
    
    return vector
