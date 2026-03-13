from fastapi import FastAPI
from api.routes import router

app = FastAPI(title="Tender ML Worker", version="1.0.0", description="Isolated ML service for CPU inference")

app.include_router(router, prefix="/internal/ml")

@app.get("/health")
def health_check():
    return {"status": "ok"}
