"""Semantic search service using pgvector cosine similarity."""

import logging
from datetime import datetime, timedelta

from sqlalchemy import select, func, and_, cast, Float
from sqlalchemy.ext.asyncio import AsyncSession

from src.db.models import STECatalog, Contract
from src.ml_client.client import ml_client
from src.schemas.api import (
    HistoricalPrice,
    STESearchResult,
    STESearchResponse,
)

logger = logging.getLogger(__name__)


async def search_ste(
    session: AsyncSession,
    query: str,
    target_region: str | None = None,
    months_depth: int = 12,
    limit: int = 20,
) -> STESearchResponse:
    """
    Hybrid semantic search:
    1. Embed query via ML Worker
    2. pgvector cosine similarity on ste_catalog.embedding
    3. JOIN with contracts table for historical prices
    4. Filter by date range
    """
    # Step 1: Get query embedding from ML Worker
    query_embedding = await ml_client.get_embedding(query)

    # Step 2: Compute cosine distance & similarity
    # pgvector <=> operator returns cosine distance, so similarity = 1 - distance
    cosine_distance = STECatalog.embedding.cosine_distance(query_embedding)
    similarity = (1 - cosine_distance).label("similarity_score")

    # Step 3: Query STE catalog with similarity ranking
    ste_query = (
        select(
            STECatalog.ste_id,
            STECatalog.name,
            STECatalog.category,
            STECatalog.manufacturer,
            STECatalog.parsed_characteristics,
            similarity,
        )
        .where(STECatalog.embedding.is_not(None))
        .order_by(cosine_distance)
        .limit(limit)
    )

    ste_result = await session.execute(ste_query)
    ste_rows = ste_result.all()

    if not ste_rows:
        return STESearchResponse(results=[], total=0)

    # Step 4: For each STE result, fetch historical prices from contracts
    cutoff_date = datetime.utcnow() - timedelta(days=months_depth * 30)
    results = []

    for row in ste_rows:
        # Fetch contracts for this STE
        contracts_query = (
            select(
                Contract.contract_id,
                Contract.contract_date,
                Contract.price_per_unit,
                Contract.customer_region,
            )
            .where(
                and_(
                    Contract.ste_id == row.ste_id,
                    Contract.contract_date >= cutoff_date,
                    Contract.price_per_unit.is_not(None),
                )
            )
            .order_by(Contract.contract_date.desc())
            .limit(50)
        )

        contracts_result = await session.execute(contracts_query)
        contracts_rows = contracts_result.all()

        historical_prices = [
            HistoricalPrice(
                contract_id=c.contract_id,
                date=c.contract_date,
                price=float(c.price_per_unit),
                region=c.customer_region,
            )
            for c in contracts_rows
        ]

        results.append(
            STESearchResult(
                ste_id=row.ste_id,
                name=row.name,
                category=row.category,
                manufacturer=row.manufacturer,
                similarity_score=round(float(row.similarity_score), 4),
                parsed_characteristics=row.parsed_characteristics,
                historical_prices=historical_prices,
            )
        )

    return STESearchResponse(results=results, total=len(results))
