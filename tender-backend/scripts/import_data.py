import json
import ijson
import os
import httpx
from sqlalchemy.ext.asyncio import AsyncSession
from core.database import AsyncSessionLocal
from models.domain import SteCatalog, Contract
from datetime import datetime

ML_SERVICE_URL = os.getenv("ML_SERVICE_URL", "http://tender_ml_worker:8001")

async def generate_embedding(text: str) -> list[float]:
    async with httpx.AsyncClient() as client:
        try:
            resp = await client.post(f"{ML_SERVICE_URL}/internal/ml/embed", json={"text": text}, timeout=10.0)
            return resp.json().get("embedding", [0.0]*384)
        except Exception:
            # Fallback local dummy if ml worker offline
            return [0.0] * 384

async def process_ste_batch(session: AsyncSession, batch: list):
    objects = []
    for item in batch:
        raw_char = json.dumps(item.get('характеристики СТЕ', []))
        text_for_embed = f"[КАТЕГОРИЯ] {item.get('Категория', '')} [НАЗВАНИЕ] {item.get('Наименование СТЕ', '')} [ХАРАКТЕРИСТИКИ] {raw_char}"
        
        vector = await generate_embedding(text_for_embed)
        
        # Simplified for Hackathon: Normally we would call /parse-characteristics here for JSONB
        
        obj = SteCatalog(
            ste_id=str(item.get('Идентификатор СТЕ')),
            name=item.get('Наименование СТЕ', ''),
            category=item.get('Категория', ''),
            manufacturer=item.get('Производитель', ''),
            raw_characteristics=raw_char,
            embedding=vector
        )
        objects.append(obj)
        
    session.add_all(objects)
    await session.commit()

async def import_cte_stream(filepath: str):
    print(f"Starting import of {filepath}...")
    batch_size = 500
    batch = []
    async with AsyncSessionLocal() as session:
        try:
            with open(filepath, 'r', encoding='utf-8') as f:
                items = ijson.items(f, 'item')
                for item in items:
                    batch.append(item)
                    if len(batch) >= batch_size:
                        await process_ste_batch(session, batch)
                        print(f"Loaded {batch_size} STE models...")
                        batch = []
                
                if batch:
                    await process_ste_batch(session, batch)
            print("STE import completed successfully.")
        except Exception as e:
            print(f"Error reading STE file: {e}")

async def process_contract_batch(session: AsyncSession, batch: list):
    objects = []
    for item in batch:
        try:
            c_date = datetime.strptime(item.get('Дата заключения контракта'), "%Y-%m-%d %H:%M:%S.%f")
        except (ValueError, TypeError):
            c_date = datetime.now()
            
        obj = Contract(
            contract_id=str(item.get('Идентификатор контракта')),
            ste_id=str(item.get('Идентификатор СТЕ по контракту')),
            purchase_name=item.get('Наименование закупки', ''),
            quantity=item.get('Количество', 0),
            price_per_unit=item.get('Цена за единицу', 0.0),
            contract_date=c_date,
            customer_region=item.get('Регион заказчика', ''),
            supplier_region=item.get('Регион поставщика', ''),
            vat_rate=item.get('Ставка НДС', '')
        )
        objects.append(obj)
    session.add_all(objects)
    await session.commit()

async def import_contracts_stream(filepath: str):
    print(f"Starting import of {filepath}...")
    batch_size = 5000
    batch = []
    async with AsyncSessionLocal() as session:
        try:
            with open(filepath, 'r', encoding='utf-8') as f:
                items = ijson.items(f, 'item')
                for item in items:
                    batch.append(item)
                    if len(batch) >= batch_size:
                        await process_contract_batch(session, batch)
                        print(f"Loaded {batch_size} Contract models...")
                        batch = []
                
                if batch:
                    await process_contract_batch(session, batch)
            print("Contracts import completed successfully.")
        except Exception as e:
            print(f"Error reading Contracts file: {e}")

if __name__ == "__main__":
    # We use asyncio.run to execute these
    pass
