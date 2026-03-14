import logging
import numpy as np
from openai import OpenAI

logger = logging.getLogger(__name__)

class Embedder:
    def __init__(self, model_name: str = "perplexity-ai/pplx-embed-v1-0.6b"):
        logger.info("Initializing Local Perplexity Embedder: %s", model_name)
        self.api_key = "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"
        self.base_url = "https://integrate.api.nvidia.com/v1"
        self.client = OpenAI(api_key=self.api_key, base_url=self.base_url)
        self.model = "nvidia/llama-nemotron-embed-1b-v2"
        logger.info("Local Perplexity Embedder ready (dim=1024)")

    def encode(self, texts: list[str]) -> np.ndarray:
        if not texts:
            return np.array([])

        try:
            response = self.client.embeddings.create(
                input=texts,
                model=self.model,
                encoding_format="float",
                extra_body={"input_type": "query", "truncate": "END", "dimensions": 1024}
            )
            # Extracted embeddings sorted by original index
            embeddings = [item.embedding for item in sorted(response.data, key=lambda x: x.index)]
            return np.array(embeddings)
        except Exception as e:
            logger.error(f"Error encoding with local PPLX: {e}")
            return np.zeros((len(texts), 1024))

    def encode_single(self, text: str) -> list[float]:
        """Encode a single text and return as list of floats."""
        embedding = self.encode([text])
        return embedding[0].tolist()
