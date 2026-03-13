from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from core.database import get_db
from models.domain import SteCatalog, Contract
import httpx
import os

router = APIRouter()
ML_SERVICE_URL = os.getenv("ML_SERVICE_URL", "http://tender_ml_worker:8001")

@router.get("/search")
async def search_ste(
    query: str = Query(..., description="Semantic search query"),
    target_region: str = Query(None, description="Optional logistics region"),
    months_depth: int = Query(12, description="Months limit for contracts"),
    limit: int = Query(10, description="Max results"),
    session: AsyncSession = Depends(get_db)
):
    # 1. Fetch query vector from ML Worker
    try:
        async with httpx.AsyncClient() as client:
            resp = await client.post(f"{ML_SERVICE_URL}/internal/ml/embed", json={"text": query})
            query_vector = resp.json()["embedding"]
    except Exception:
        # Fallback dummy zero vector
        query_vector = [0.0] * 384

    # 2. Vector Search using pgvector `<=>` operator
    stmt = (
        select(SteCatalog, SteCatalog.embedding.cosine_distance(query_vector).label("distance"))
        .order_by("distance")
        .limit(limit)
    )
    
    result = await session.execute(stmt)
    stelist = result.all()
    
    # 3. Assemble response and fetch historical prices
    results = []
    for ste, distance in stelist:
        # Fetch matching contracts history
        contract_stmt = select(Contract).where(Contract.ste_id == ste.ste_id).order_by(Contract.contract_date.desc()).limit(10)
        c_res = await session.execute(contract_stmt)
        contracts = c_res.scalars().all()
        
        hist_prices = [
            {
                "contract_id": c.contract_id,
                "date": c.contract_date.strftime("%Y-%m-%d"),
                "price": float(c.price_per_unit),
                "region": c.customer_region
            } for c in contracts
        ]
        
        results.append({
            "ste_id": ste.ste_id,
            "name": ste.name,
            "category": ste.category,
            "similarity_score": 1.0 - float(distance),
            "parsed_characteristics": ste.parsed_characteristics or {},
            "historical_prices": hist_prices
        })

    return {"results": results}
