"""Pydantic v2 schemas for API request/response models."""

from pydantic import BaseModel, Field
from datetime import datetime


# ──────────────── Search ────────────────


class STESearchRequest(BaseModel):
    query: str = Field(..., min_length=1, description="Search query text")
    target_region: str | None = Field(None, description="Target customer region")
    months_depth: int = Field(12, ge=1, le=120, description="Months to look back")
    limit: int = Field(20, ge=1, le=100, description="Max results to return")


class HistoricalPrice(BaseModel):
    contract_id: int
    date: datetime | None
    price: float
    region: str | None


class STESearchResult(BaseModel):
    ste_id: int
    name: str
    category: str | None
    manufacturer: str | None
    similarity_score: float
    parsed_characteristics: dict | None
    historical_prices: list[HistoricalPrice]


class STESearchResponse(BaseModel):
    results: list[STESearchResult]
    total: int


# ──────────────── NMCC Calculation ────────────────


class NMCKCalculateRequest(BaseModel):
    target_ste_id: int
    target_region: str | None = None
    selected_prices: list[float] = Field(..., min_length=1)


class NMCKCalculateResponse(BaseModel):
    nmck_value: float
    variation_coefficient: float
    valid_prices_used: list[float]
    detected_outliers: list[float]
    requires_manual_input: bool


# ──────────────── Report ────────────────


class NMCKReportRequest(BaseModel):
    target_ste_id: int
    target_region: str | None = None
    nmck_value: float
    variation_coefficient: float
    valid_prices_used: list[float]
    detected_outliers: list[float]


# ──────────────── Health ────────────────


class HealthResponse(BaseModel):
    status: str = "ok"
    ste_count: int = 0
    contracts_count: int = 0
