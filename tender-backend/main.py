"""FastAPI application entry point for the Tender Backend service."""

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import func, select, text

from src.api.search import router as search_router
from src.api.nmck import router as nmck_router
from src.db.session import engine, async_session, Base
from src.db.models import STECatalog, Contract
from src.ml_client.client import ml_client
from src.schemas.api import HealthResponse
from src.services.ingestion import run_full_ingestion

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan: DB init, data ingestion, shutdown cleanup."""
    logger.info("Starting Tender Backend...")

    # Create tables & enable pgvector extension
    async with engine.begin() as conn:
        await conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
        await conn.run_sync(Base.metadata.create_all)
    logger.info("Database tables created")

    # Run data ingestion
    async with async_session() as session:
        result = await run_full_ingestion(session)
        logger.info(f"Ingestion result: {result}")

    yield

    # Shutdown
    await ml_client.close()
    await engine.dispose()
    logger.info("Tender Backend shut down")


app = FastAPI(
    title="Tender НМЦК Backend",
    description="API for STE semantic search, NMCC calculation, and report generation",
    version="1.0.0",
    lifespan=lifespan,
)

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Routers
app.include_router(search_router)
app.include_router(nmck_router)


@app.get("/health", response_model=HealthResponse)
async def health_check():
    """Health check endpoint with DB row counts."""
    async with async_session() as session:
        ste_count = (await session.execute(select(func.count(STECatalog.id)))).scalar() or 0
        contracts_count = (await session.execute(select(func.count(Contract.id)))).scalar() or 0

    return HealthResponse(
        status="ok",
        ste_count=ste_count,
        contracts_count=contracts_count,
    )


@app.post("/api/v1/ingest/embeddings")
async def trigger_embedding_enrichment():
    """Manually trigger embedding enrichment for STE items without embeddings."""
    from src.services.ingestion import enrich_embeddings

    async with async_session() as session:
        count = await enrich_embeddings(session)
    return {"status": "completed", "enriched_count": count}
