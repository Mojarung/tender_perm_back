"""API router for STE search endpoints."""

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from src.db.session import get_db
from src.schemas.api import STESearchResponse
from src.services.search import search_ste

router = APIRouter(prefix="/api/v1/ste", tags=["STE Search"])


@router.get("/search", response_model=STESearchResponse)
async def ste_search(
    query: str = Query(..., min_length=1, description="Search query"),
    target_region: str | None = Query(None, description="Target customer region"),
    months_depth: int = Query(12, ge=1, le=120, description="Months to look back"),
    limit: int = Query(20, ge=1, le=100, description="Max results"),
    session: AsyncSession = Depends(get_db),
) -> STESearchResponse:
    """
    Hybrid semantic search for STE analogs with historical price data.

    1. Embeds query text via ML Worker (ai-forever/ru-e5-small ONNX)
    2. pgvector cosine similarity search on ste_catalog.embedding
    3. JOINs contracts for historical prices within date range
    """
    return await search_ste(
        session=session,
        query=query,
        target_region=target_region,
        months_depth=months_depth,
        limit=limit,
    )
