from fastapi import FastAPI
from core.database import engine, Base
from api.nmcc_routes import router as nmcc_router
from api.ste_routes import router as ste_router
from api.report_routes import router as report_router
import contextlib
from sqlalchemy import text

@contextlib.asynccontextmanager
async def lifespan(app: FastAPI):
    async with engine.begin() as conn:
        await conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector;"))
        await conn.run_sync(Base.metadata.create_all)
    yield

app = FastAPI(title="Tender Backend", version="1.0.0", lifespan=lifespan)

app.include_router(nmcc_router, prefix="/api/v1/nmck")
app.include_router(ste_router, prefix="/api/v1/ste")
app.include_router(report_router, prefix="/api/v1/document")

@app.get("/health")
def health():
    return {"status": "ok"}
