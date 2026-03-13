"""FastAPI application for the ML Worker service.

Internal microservice providing:
- POST /internal/ml/embed         → ai-forever/ru-e5-small (ONNX INT8)
- POST /internal/ml/parse-characteristics → Qwen2.5-0.5B-Instruct-GGUF (Q4_K_M)
- POST /internal/ml/detect-outliers      → sklearn IsolationForest
- GET  /health
"""

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field

from services.embedding import embedding_service
from services.slm_parser import slm_service
from services.outlier_detection import outlier_service

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Load models on startup."""
    logger.info("Starting ML Worker...")

    # Load embedding model
    try:
        embedding_service.load()
        logger.info("✅ Embedding model loaded")
    except FileNotFoundError as e:
        logger.warning(f"⚠️ Embedding model not available: {e}")

    # Load SLM model
    try:
        slm_service.load()
        logger.info("✅ SLM model loaded")
    except FileNotFoundError as e:
        logger.warning(f"⚠️ SLM model not available: {e}")

    # Outlier detection doesn't need loading (sklearn is in-memory)
    logger.info("✅ Outlier detection ready")

    yield

    logger.info("ML Worker shut down")


app = FastAPI(
    title="Tender ML Worker",
    description="Internal ML service for embeddings, parsing, and outlier detection",
    version="1.0.0",
    lifespan=lifespan,
)


# ───────────────── Request/Response Models ─────────────────


class EmbedRequest(BaseModel):
    text: str = Field(..., min_length=1)


class EmbedResponse(BaseModel):
    embedding: list[float]


class ParseRequest(BaseModel):
    raw_text: str = Field(..., min_length=1)


class ParseResponse(BaseModel):
    parsed_json: dict


class OutlierRequest(BaseModel):
    prices: list[float] = Field(..., min_length=1)


class OutlierResponse(BaseModel):
    valid_prices: list[float]
    outliers: list[float]


class HealthResponse(BaseModel):
    status: str
    embedding_loaded: bool
    slm_loaded: bool
    outlier_ready: bool = True


# ───────────────── Endpoints ─────────────────


@app.post("/internal/ml/embed", response_model=EmbedResponse)
async def embed_text(request: EmbedRequest) -> EmbedResponse:
    """Generate embedding vector for input text.

    Model: ai-forever/ru-e5-small (ONNX INT8, dim=384)
    """
    if not embedding_service.is_loaded:
        raise HTTPException(503, "Embedding model not loaded")

    try:
        vector = embedding_service.embed(request.text)
        return EmbedResponse(embedding=vector)
    except Exception as e:
        logger.error(f"Embedding error: {e}")
        raise HTTPException(500, f"Embedding failed: {str(e)}")


@app.post("/internal/ml/parse-characteristics", response_model=ParseResponse)
async def parse_characteristics(request: ParseRequest) -> ParseResponse:
    """Parse raw characteristics array into structured JSON.

    Model: Qwen2.5-0.5B-Instruct-GGUF (Q4_K_M, llama-cpp-python)
    """
    if not slm_service.is_loaded:
        # Fallback: try simple parsing without SLM
        import json
        try:
            data = json.loads(request.raw_text)
            if isinstance(data, list):
                result = {}
                for pair in data:
                    if isinstance(pair, list) and len(pair) >= 2:
                        key = str(pair[0]).strip()
                        val = str(pair[1]).strip()
                        try:
                            result[key] = float(val)
                        except ValueError:
                            result[key] = val
                return ParseResponse(parsed_json=result)
        except Exception:
            pass
        raise HTTPException(503, "SLM model not loaded and simple parsing failed")

    try:
        parsed = slm_service.parse_characteristics(request.raw_text)
        return ParseResponse(parsed_json=parsed)
    except Exception as e:
        logger.error(f"Parse error: {e}")
        raise HTTPException(500, f"Parsing failed: {str(e)}")


@app.post("/internal/ml/detect-outliers", response_model=OutlierResponse)
async def detect_outliers(request: OutlierRequest) -> OutlierResponse:
    """Detect price outliers using IsolationForest.

    Model: sklearn.ensemble.IsolationForest (contamination='auto')
    """
    try:
        result = outlier_service.detect(request.prices)
        return OutlierResponse(**result)
    except Exception as e:
        logger.error(f"Outlier detection error: {e}")
        raise HTTPException(500, f"Outlier detection failed: {str(e)}")


@app.get("/health", response_model=HealthResponse)
async def health_check() -> HealthResponse:
    """Health check for Docker healthcheck and backend readiness probes."""
    return HealthResponse(
        status="ok",
        embedding_loaded=embedding_service.is_loaded,
        slm_loaded=slm_service.is_loaded,
    )
