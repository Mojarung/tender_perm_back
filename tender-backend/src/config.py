"""Application configuration via environment variables."""

from pydantic_settings import BaseSettings
from functools import lru_cache


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    # Database
    database_url: str = "postgresql+asyncpg://tender_user:tender_password@localhost:5432/tenderhack_db"

    # ML Worker
    ml_service_url: str = "http://localhost:8001"

    # Data files
    cte_json_path: str = "cte.json"
    contracts_json_path: str = "contracts.json"

    # Ingestion
    ingestion_batch_size: int = 5000
    embedding_batch_size: int = 100

    # Search defaults
    default_months_depth: int = 12
    default_search_limit: int = 20

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8"}


@lru_cache
def get_settings() -> Settings:
    return Settings()
