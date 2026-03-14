from src.data_access.cte_repo import CTERepository
from src.data_access.polars_repo import ContractRepository
from src.data_access.qdrant_repo import QdrantRepository
from src.ml.embeddings import EmbeddingService

_cte_repo: CTERepository | None = None
_contract_repo: ContractRepository | None = None
_qdrant_repo: QdrantRepository | None = None
_embedding_service: EmbeddingService | None = None


def init_cte_repo(repo: CTERepository) -> None:
    global _cte_repo
    _cte_repo = repo


def init_contract_repo(repo: ContractRepository) -> None:
    global _contract_repo
    _contract_repo = repo


def init_qdrant_repo(repo: QdrantRepository) -> None:
    global _qdrant_repo
    _qdrant_repo = repo


def init_embedding_service(service: EmbeddingService) -> None:
    global _embedding_service
    _embedding_service = service


def get_cte_repo() -> CTERepository:
    assert _cte_repo is not None, "CTERepository not initialized"
    return _cte_repo


def get_contract_repo() -> ContractRepository:
    assert _contract_repo is not None, "ContractRepository not initialized"
    return _contract_repo


def get_qdrant_repo() -> QdrantRepository | None:
    return _qdrant_repo


def get_embedding_service() -> EmbeddingService | None:
    return _embedding_service
