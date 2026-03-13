from fastapi import APIRouter
from pydantic import BaseModel
from typing import List, Dict, Any
from services.embedding import embed_text
from services.llm_parser import parse_text
from services.anomaly import detect_anomalies

router = APIRouter()

class EmbedRequest(BaseModel):
    text: str

class EmbedResponse(BaseModel):
    embedding: List[float]

class ParseRequest(BaseModel):
    raw_text: str

class ParseResponse(BaseModel):
    parsed_json: Dict[str, Any]

class AnomalyRequest(BaseModel):
    prices: List[float]

class AnomalyResponse(BaseModel):
    valid_prices: List[float]
    outliers: List[float]

@router.post("/embed", response_model=EmbedResponse)
def get_embedding(payload: EmbedRequest):
    vector = embed_text(payload.text)
    return {"embedding": vector}

@router.post("/parse-characteristics", response_model=ParseResponse)
def parse_characteristics(payload: ParseRequest):
    result = parse_text(payload.raw_text)
    return {"parsed_json": result}

@router.post("/detect-outliers", response_model=AnomalyResponse)
def detect_outliers_endpoint(payload: AnomalyRequest):
    valid, outliers = detect_anomalies(payload.prices)
    return {
        "valid_prices": valid,
        "outliers": outliers
    }
