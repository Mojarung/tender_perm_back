"""Data ingestion service: loads cte.json and contracts.json into PostgreSQL."""

import json
import logging
from datetime import datetime
from pathlib import Path

from sqlalchemy import func, select, text
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from src.config import get_settings
from src.db.models import Contract, STECatalog
from src.ml_client.client import ml_client

logger = logging.getLogger(__name__)
settings = get_settings()


async def is_data_loaded(session: AsyncSession) -> bool:
    """Check if STE catalog already has data."""
    result = await session.execute(select(func.count(STECatalog.id)))
    count = result.scalar()
    return count is not None and count > 0


async def ingest_ste_catalog(session: AsyncSession) -> int:
    """Load STE items from cte.json into database."""
    path = Path(settings.cte_json_path)
    if not path.exists():
        logger.warning(f"STE data file not found: {path}")
        return 0

    logger.info(f"Loading STE catalog from {path}...")
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)

    total = len(data)
    logger.info(f"Found {total} STE items to ingest")

    batch_size = settings.ingestion_batch_size
    inserted = 0

    for i in range(0, total, batch_size):
        batch = data[i : i + batch_size]
        values = []
        for item in batch:
            raw_chars = item.get("характеристики СТЕ")
            values.append(
                {
                    "ste_id": item["Идентификатор СТЕ"],
                    "name": item["Наименование СТЕ"],
                    "category": item.get("Категория"),
                    "manufacturer": item.get("Производитель"),
                    "raw_characteristics": json.dumps(raw_chars, ensure_ascii=False)
                    if raw_chars
                    else None,
                }
            )

        stmt = pg_insert(STECatalog).values(values)
        stmt = stmt.on_conflict_do_nothing(index_elements=["ste_id"])
        await session.execute(stmt)
        await session.commit()

        inserted += len(values)
        if inserted % 50000 == 0 or inserted >= total:
            logger.info(f"  STE ingestion progress: {inserted}/{total}")

    logger.info(f"STE catalog ingestion complete: {inserted} items")
    return inserted


async def ingest_contracts(session: AsyncSession) -> int:
    """Load contracts from contracts.json into database."""
    path = Path(settings.contracts_json_path)
    if not path.exists():
        logger.warning(f"Contracts data file not found: {path}")
        return 0

    logger.info(f"Loading contracts from {path}...")
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)

    total = len(data)
    logger.info(f"Found {total} contracts to ingest")

    batch_size = settings.ingestion_batch_size

    inserted = 0
    for i in range(0, total, batch_size):
        batch = data[i : i + batch_size]
        values = []
        for item in batch:
            contract_date = None
            raw_date = item.get("Дата заключения контракта")
            if raw_date:
                try:
                    contract_date = datetime.fromisoformat(raw_date.replace(" ", "T"))
                except (ValueError, AttributeError):
                    pass

            values.append(
                {
                    "contract_id": item["Идентификатор контракта"],
                    "ste_id": item.get("Идентификатор СТЕ по контракту"),
                    "purchase_name": item.get("Наименование закупки"),
                    "ste_position_name": item.get("Наименование позиции СТЕ"),
                    "quantity": item.get("Количество"),
                    "unit": item.get("Единица измерения"),
                    "price_per_unit": item.get("Цена за единицу"),
                    "purchase_method": item.get("Способ закупки"),
                    "initial_contract_cost": item.get("Начальная стоимость контракта"),
                    "final_contract_cost": item.get(
                        "Стоимость контракта после заключения"
                    ),
                    "discount_percent": item.get("% снижения"),
                    "contract_date": contract_date,
                    "customer_inn": str(item.get("ИНН заказчика", "")),
                    "customer_region": item.get("Регион заказчика"),
                    "supplier_inn": str(item.get("ИНН поставщика", "")),
                    "supplier_region": item.get("Регион поставщика"),
                    "vat_rate": item.get("Ставка НДС"),
                }
            )

        stmt = pg_insert(Contract).values(values)
        stmt = stmt.on_conflict_do_nothing()
        await session.execute(stmt)
        await session.commit()

        inserted += len(values)
        if inserted % 50000 == 0 or inserted >= total:
            logger.info(f"  Contracts ingestion progress: {inserted}/{total}")

    logger.info(f"Contracts ingestion complete: {inserted} items")
    return inserted


async def enrich_embeddings(session: AsyncSession) -> int:
    """Generate embeddings for STE items that don't have them yet."""
    result = await session.execute(
        select(STECatalog.id, STECatalog.ste_id, STECatalog.name, STECatalog.category, STECatalog.raw_characteristics)
        .where(STECatalog.embedding.is_(None))
        .limit(10000)
    )
    rows = result.all()

    if not rows:
        logger.info("All STE items already have embeddings")
        return 0

    logger.info(f"Generating embeddings for {len(rows)} STE items...")
    count = 0

    for row in rows:
        # Build composite text for embedding
        parts = [f"[КАТЕГОРИЯ] {row.category or ''}"]
        parts.append(f"[НАЗВАНИЕ] {row.name}")
        if row.raw_characteristics:
            try:
                chars = json.loads(row.raw_characteristics)
                char_str = " ".join(f"{c[0]}: {c[1]}" for c in chars if len(c) >= 2)
                parts.append(f"[ХАРАКТЕРИСТИКИ] {char_str}")
            except (json.JSONDecodeError, TypeError):
                pass
        composite_text = " ".join(parts)

        try:
            embedding = await ml_client.get_embedding(composite_text)
            await session.execute(
                text("UPDATE ste_catalog SET embedding = :emb WHERE id = :id"),
                {"emb": str(embedding), "id": str(row.id)},
            )
            count += 1

            if count % 500 == 0:
                await session.commit()
                logger.info(f"  Embeddings progress: {count}/{len(rows)}")
        except Exception as e:
            logger.error(f"Failed to embed STE {row.ste_id}: {e}")
            continue

    await session.commit()
    logger.info(f"Embedding enrichment complete: {count} items")
    return count


async def run_full_ingestion(session: AsyncSession) -> dict:
    """Run the full data ingestion pipeline."""
    if await is_data_loaded(session):
        logger.info("Data already loaded, skipping ingestion")
        return {"status": "already_loaded"}

    ste_count = await ingest_ste_catalog(session)
    contracts_count = await ingest_contracts(session)

    return {
        "status": "completed",
        "ste_items": ste_count,
        "contracts": contracts_count,
    }
