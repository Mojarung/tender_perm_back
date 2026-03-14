from pathlib import Path
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    # Qdrant
    qdrant_host: str = "127.0.0.1"
    qdrant_port: int = 6333
    qdrant_collection: str = "cte_catalog"

    # Embedding model
    embedding_model: str = "perplexity-ai/pplx-embed-v1-0.6b"
    embedding_dim: int = 1024

    # Data paths
    contracts_path: Path = Path("contracts.json")
    cte_path: Path = Path("cte.json")

    # Search
    search_top_k: int = 20
    search_score_threshold: float = 0.5
    search_result_limit: int = 10

    # Price filtering
    price_months_back: int = 12

    # NMCK
    max_coefficient_of_variation: float = 33.0

    # Document
    template_path: Path = Path("templates/nmck_template.docx")
    output_dir: Path = Path("output")

    # Server
    host: str = "0.0.0.0"
    port: int = 8000

    model_config = {"env_prefix": "TENDER_"}


settings = Settings()
