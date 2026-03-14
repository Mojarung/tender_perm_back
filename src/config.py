from pydantic_settings import BaseSettings
from pathlib import Path


class Settings(BaseSettings):
    cte_json_path: Path = Path("data/cte.json")
    contracts_json_path: Path = Path("data/contracts.json")

    qdrant_host: str = "localhost"
    qdrant_port: int = 6333
    qdrant_collection: str = "cte_catalog"

    embedding_model: str = "nvidia/llama-nemotron-embed-1b-v2"
    embedding_api_url: str = "https://integrate.api.nvidia.com/v1"
    embedding_api_key: str = ""
    embedding_dimensions: int = 1024
    embedding_batch_size: int = 256
    enable_embeddings: bool = True
    reindex_embeddings_on_startup: bool = False

    host: str = "0.0.0.0"
    port: int = 8000

    model_config = {"env_prefix": "", "env_file": ".env"}


settings = Settings()
