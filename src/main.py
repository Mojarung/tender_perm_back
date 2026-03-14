"""FastAPI application entry point with async lifespan for data loading."""

import logging
import os
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from qdrant_client import QdrantClient

from src.config import settings
from src.data_access.contract_repo import ContractRepository
from src.data_access.cte_repo import CTERepository
from src.ml.embedder import Embedder
from src.graph.nodes import build_graph, set_dependencies
from src.api.routes import router, set_graph

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Application lifespan: load all data and models on startup.

    Order:
    1. Load embedding model
    2. Connect to Qdrant
    3. Load & embed CTE catalog → upsert to Qdrant
    4. Load contracts into Polars
    5. Build LangGraph pipeline
    """
    logger.info("=" * 60)
    logger.info("TENDER HACK PERM — Starting up ...")
    logger.info("=" * 60)

    # 1. Load embedding model
    logger.info("Step 1/5: Loading embedding model ...")
    embedder = Embedder(model_name=settings.embedding_model)

    # 2. Connect to Qdrant
    logger.info(
        "Step 2/5: Connecting to Qdrant at %s:%d ...",
        settings.qdrant_host,
        settings.qdrant_port,
    )
    qdrant_client = QdrantClient(
        host=settings.qdrant_host,
        port=settings.qdrant_port,
    )

    # 3. Load CTE catalog and upsert to Qdrant
    logger.info("Step 3/5: Loading CTE catalog ...")
    cte_repo = CTERepository(
        qdrant_client=qdrant_client,
        collection_name=settings.qdrant_collection,
        embedding_dim=settings.embedding_dim,
    )
    cte_repo.load_cte_data(settings.cte_path)
    cte_repo.upsert_items(embedder)

    # 4. Load contracts
    logger.info("Step 4/5: Loading contracts ...")
    ContractRepository.load_data(settings.contracts_path)

    # 5. Build graph
    logger.info("Step 5/5: Building LangGraph pipeline ...")
    set_dependencies(embedder, cte_repo)
    graph = build_graph()
    set_graph(graph)

    # Store refs on app for potential direct access
    app.state.embedder = embedder
    app.state.qdrant_client = qdrant_client
    app.state.cte_repo = cte_repo
    app.state.graph = graph

    logger.info("=" * 60)
    logger.info("STARTUP COMPLETE — Server ready")
    logger.info("=" * 60)

    yield  # ← Application runs here

    # Shutdown
    logger.info("Shutting down ...")
    qdrant_client.close()


# ── Create app ──

app = FastAPI(
    title="Tender Hack Perm — NMCK Calculator",
    description="Intelligent service for calculating and justifying the Initial Maximum Contract Price (НМЦК)",
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(router)

os.makedirs("static", exist_ok=True)
app.mount("/ui", StaticFiles(directory="static", html=True), name="static")


@app.get("/health")
async def health():
    return {
        "status": "ok",
        "contracts_loaded": ContractRepository.is_loaded(),
    }
