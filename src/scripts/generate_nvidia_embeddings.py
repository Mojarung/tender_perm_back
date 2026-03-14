import os
import sys
import logging
from pathlib import Path
import numpy as np
from openai import OpenAI
from qdrant_client import QdrantClient

# Add src to sys path to be able to import from src
sys.path.append(str(Path(__file__).parent.parent.parent))

from src.data_access.cte_repo import CTERepository

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
logger = logging.getLogger(__name__)

class NvidiaEmbedder:
    """Wrapper for NVIDIA API to integrate with CTERepository"""
    
    def __init__(self, api_key: str, base_url: str = "https://integrate.api.nvidia.com/v1", model: str = "nvidia/llama-nemotron-embed-1b-v2"):
        self.client = OpenAI(api_key=api_key, base_url=base_url)
        self.model = model

    def encode(self, texts: list[str]) -> np.ndarray:
        """Encode texts into embeddings using NVIDIA API"""
        if not texts:
            return np.array([])
        
        try:
            # We send batches up to the size defined in python caller (CTE repository uses 256)
            # The NVIDIA API supports lists of strings
            response = self.client.embeddings.create(
                input=texts,
                model=self.model,
                encoding_format="float",
                extra_body={"input_type": "query", "truncate": "END", "dimensions": 1024}
            )
            
            # Response data is ordered by index, we extract embeddings and sort just in case
            embeddings = [item.embedding for item in sorted(response.data, key=lambda x: x.index)]
            return np.array(embeddings)
        except Exception as e:
            logger.error(f"Error generating embeddings via NVIDIA API: {e}")
            raise


def main():
    # Setup paths
    base_dir = Path(__file__).parent.parent.parent
    cte_path = base_dir / "cte.json"
    
    # Qdrant configuration
    qdrant_host = "localhost"
    qdrant_port = 6333
    # Use settings from config to overwrite the existing perplexity collection
    from src.config import settings
    collection_name = settings.qdrant_collection
    
    # NVIDIA Llama Nemotron embed 1b v2 produces 2048-dimensional vectors
    # BUT we need to overwrite the existing perplexity collection, which was created for 1024-dim
    # We must recreate the collection or change the dimension in config.
    # Since we are just filling it, we'll try to recreate it with 2048 or use 1024 if we truncate.
    # NVIDIA Nemotron supports truncating sizes! Let's truncate to the existing dimension!
    
    embedding_dim = settings.embedding_dim 
    
    # API key from prompt
    api_key = "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"
    
    logger.info("Initializing NVIDIA Embedder with truncation to match existing collection...")
    embedder = NvidiaEmbedder(api_key=api_key)
    
    # Initialize Qdrant Client
    logger.info(f"Connecting to Qdrant at {qdrant_host}:{qdrant_port}")
    try:
        qdrant_client = QdrantClient(host=qdrant_host, port=qdrant_port)
    except Exception as e:
        logger.error(f"Failed to connect to Qdrant: {e}")
        return
    
    # Initialize Repository
    repo = CTERepository(
        qdrant_client=qdrant_client,
        collection_name=collection_name,
        embedding_dim=embedding_dim
    )
    
    # Load Data
    if not cte_path.exists():
        logger.error(f"cte.json file not found at {cte_path}")
        return
    
    logger.info(f"Loading CTE data from {cte_path}")
    repo.load_cte_data(cte_path)
    
    # Start embedding and upsert
    logger.info(f"Processing embeddings and upserting into Qdrant collection: {collection_name}...")
    try:
        repo.upsert_items(embedder)
        logger.info("Successfully generated and saved embeddings to Qdrant!")
    except Exception as e:
        logger.error(f"Failed to upsert items: {e}")

if __name__ == "__main__":
    main()
