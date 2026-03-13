import numpy as np

def embed_text(text: str) -> list[float]:
    """
    Executes ru-e5-small via ONNX Runtime to generate a 384-dimensional text embedding.
    For this prototype phase without model weights downloaded, it returns a deterministic dummy vector.
    """
    # Deterministic dummy vector generation based on string length
    np.random.seed(len(text) % 10000)
    vector = np.random.randn(384).tolist()
    
    # L2 Normalization (required for e5 models)
    norm = np.linalg.norm(vector)
    vector = [float(v / norm) for v in vector]
    
    return vector
