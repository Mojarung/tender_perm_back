import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse

from src.config import settings
from src.data_access.cte_repo import CTERepository
from src.data_access.polars_repo import ContractRepository
from src.data_access.qdrant_repo import QdrantRepository
from src.ml.embeddings import EmbeddingService, build_embedding_text
from src.dependencies import init_cte_repo, init_contract_repo, init_qdrant_repo, init_embedding_service
from src.api.router import router

from qdrant_client.models import PointStruct

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def _index_cte_to_qdrant(
    cte_repo: CTERepository,
    qdrant_repo: QdrantRepository,
    embedding_service: EmbeddingService,
) -> None:
    if qdrant_repo.collection_size() > 0:
        logger.info("Qdrant collection already populated, skipping indexing")
        return

    logger.info("Indexing CTE catalog to Qdrant...")
    items = cte_repo.all_items()
    batch_size = settings.embedding_batch_size

    for i in range(0, len(items), batch_size):
        batch = items[i:i + batch_size]
        texts = [build_embedding_text(item) for item in batch]
        vectors = embedding_service.encode(texts, batch_size=batch_size)

        points = []
        for item, vector in zip(batch, vectors):
            points.append(PointStruct(
                id=item["cte_id"],
                vector=vector,
                payload={
                    "cte_id": item["cte_id"],
                    "name": item["name"],
                    "category": item["category"],
                    "manufacturer": item["manufacturer"],
                    "characteristics": item["characteristics"],
                    "embedding_text": build_embedding_text(item),
                },
            ))
        qdrant_repo.upsert_batch(points)
        logger.info(f"Indexed {min(i + batch_size, len(items))}/{len(items)} CTE items")

    logger.info("CTE indexing complete")


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Loading CTE catalog...")
    cte_repo = CTERepository()
    cte_repo.load(settings.cte_json_path)
    init_cte_repo(cte_repo)
    logger.info(f"Loaded {cte_repo.size} CTE items")

    logger.info("Loading contracts...")
    contract_repo = ContractRepository()
    contract_repo.load(settings.contracts_json_path)
    init_contract_repo(contract_repo)
    logger.info(f"Loaded {contract_repo.size} contracts")

    if settings.enable_embeddings:
        logger.info("Connecting to Qdrant...")
        qdrant_repo = QdrantRepository(
            host=settings.qdrant_host,
            port=settings.qdrant_port,
            collection=settings.qdrant_collection,
        )
        init_qdrant_repo(qdrant_repo)

        logger.info("Initializing embedding service (API: %s)...", settings.embedding_api_url)
        embedding_service = EmbeddingService(
            model_name=settings.embedding_model,
            api_url=settings.embedding_api_url,
            api_key=settings.embedding_api_key,
            dimensions=settings.embedding_dimensions,
        )
        init_embedding_service(embedding_service)
        logger.info("Embedding service ready")

        if settings.reindex_embeddings_on_startup:
            logger.info("Qdrant reindex is enabled; rebuilding collection if needed")
            qdrant_repo.ensure_collection(vector_size=embedding_service.vector_size)
            _index_cte_to_qdrant(cte_repo, qdrant_repo, embedding_service)
        else:
            if not qdrant_repo.has_collection():
                raise RuntimeError(
                    f"Qdrant collection '{settings.qdrant_collection}' not found. "
                    "Provide precomputed embeddings or enable reindex_embeddings_on_startup=true."
                )
            points_count = qdrant_repo.collection_size()
            if points_count == 0:
                raise RuntimeError(
                    f"Qdrant collection '{settings.qdrant_collection}' is empty. "
                    "Provide precomputed embeddings or enable reindex_embeddings_on_startup=true."
                )
            logger.info(
                "Using precomputed embeddings from Qdrant collection '%s' (%s points)",
                settings.qdrant_collection,
                points_count,
            )
    else:
        logger.info("Embeddings disabled, skipping Qdrant and embedding model")

    logger.info("All systems ready")
    yield
    logger.info("Shutting down")


app = FastAPI(title="NMCC Calculator", version="0.1.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(router)

static_dir = Path(__file__).parent / "static"
app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")


@app.get("/")
async def root():
    return FileResponse(str(static_dir / "index.html"))
