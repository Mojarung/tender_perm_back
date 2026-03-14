from pydantic import BaseModel, Field
from typing import Any


# ── API Request models ──────────────────────────────────────────────


class SessionStartRequest(BaseModel):
    cte_name: str = Field(..., description="Name of the CTE item to search for")
    category: str | None = Field(None, description="Category filter for hybrid search")
    region: str | None = Field(None, description="Region filter for price lookup")
    quantity: float = Field(1.0, gt=0, description="Required quantity")


class AnalogApprovalRequest(BaseModel):
    approved_analog_ids: list[int] = Field(
        ..., description="List of approved CTE IDs (Идентификатор СТЕ)"
    )
    manual_cte_ids: list[int] = Field(
        default_factory=list,
        description="Additional CTE IDs manually added by user",
    )
    units: list[str] | None = Field(None, description="Selected units of measurement for price filtering")
    manual_prices: list["ManualPrice"] = Field(
        default_factory=list,
        description="Custom manual prices added at the analog stage",
    )


class PriceApprovalRequest(BaseModel):
    approved_price_indices: list[int] = Field(
        ..., description="Indices of approved prices from filtered list"
    )
    manual_prices: list["ManualPrice"] = Field(
        default_factory=list,
        description="Manually entered prices",
    )


class ManualPrice(BaseModel):
    name: str
    price: float
    region: str | None = None
    source: str = "manual"


class RecalculateRequest(BaseModel):
    inflation_coefficient: float = 1.0
    quantity: float | None = None


# ── API Response models ─────────────────────────────────────────────


class AnalogResult(BaseModel):
    cte_id: int
    name: str
    category: str
    manufacturer: str
    attributes: dict[str, str]
    cosine_score: float
    attribute_overlap: float
    final_score: float
    match_reason: str
    available_units: list[str] = Field(default_factory=list, description="List of units supported by this analog")


class PriceResult(BaseModel):
    index: int
    cte_id: int
    cte_name: str
    price: float
    quantity: float
    unit: str
    region: str
    contract_date: str
    contract_id: int
    procurement_method: str
    is_outlier: bool = False
    outlier_reason: str | None = None
    time_weight: float = 1.0


class NMCKResult(BaseModel):
    weighted_average_price: float
    median_price: float
    coefficient_of_variation: float
    is_homogeneous: bool
    nmck_per_unit: float
    total_nmck: float
    price_range_min: float
    price_range_max: float
    num_prices_used: int
    justification: list[dict[str, Any]]


class SessionStatus(BaseModel):
    session_id: str
    current_step: str
    error: str | None = None


class SearchResponse(BaseModel):
    session_id: str
    analogs: list[AnalogResult]
    total_found: int
    available_units: list[str] = Field(default_factory=list, description="List of unique units of measurement for these analogs")


class PricesResponse(BaseModel):
    session_id: str
    filtered_prices: list[PriceResult]
    outlier_prices: list[PriceResult]
    total_found: int


class CalculationResponse(BaseModel):
    session_id: str
    result: NMCKResult


class DocumentResponse(BaseModel):
    session_id: str
    document_path: str
