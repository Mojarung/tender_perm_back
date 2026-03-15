from pydantic import BaseModel, Field
from typing import Any


# ── API Request models ──────────────────────────────────────────────


class SessionStartRequest(BaseModel):
    cte_name: str = Field(..., description="Name of the CTE item to search for")
    category: str | None = Field(None, description="Category filter for hybrid search")
    region: str | None = Field(None, description="Region filter for price lookup")
    quantity: float = Field(1.0, gt=0, description="Required quantity")
    purchase_id: int | None = Field(None, description="Associated purchase ID for history tracking")


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
    available_units: list[str] = Field(default_factory=list)
    contract_count: int = Field(0, description="Contracts in last 12 months")
    regions: list[str] = Field(default_factory=list, description="Regions where sold")
    unique_suppliers: int = Field(0, description="Unique suppliers (by INN)")


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


class PriceSearchInfo(BaseModel):
    requested_region: str = ""
    scope: str = "region"
    months: int = 12


class PricesResponse(BaseModel):
    session_id: str
    filtered_prices: list[PriceResult]
    outlier_prices: list[PriceResult]
    total_found: int
    search_info: PriceSearchInfo | None = None


class CalculationResponse(BaseModel):
    session_id: str
    result: NMCKResult


class DocumentResponse(BaseModel):
    session_id: str
    document_path: str


# ── History models ─────────────────────────────────────────────────


class CalculationSummary(BaseModel):
    id: int
    session_id: str
    cte_name: str
    cte_category: str
    cte_id: int
    status: str
    current_step: str
    nmck_per_unit: float | None = None
    total_nmck: float | None = None
    coefficient_of_variation: float | None = None
    is_homogeneous: bool | None = None
    num_prices_used: int | None = None
    document_path: str | None = None
    approved_analog_ids: list[int] = []
    selected_units: list[str] = []
    created_at: str
    completed_at: str | None = None


class PurchaseSummary(BaseModel):
    id: int
    created_at: str
    region: str
    status: str
    total_nmck: float
    items_count: int
    completed_count: int
    calculations: list[CalculationSummary]


class PurchaseListResponse(BaseModel):
    purchases: list[PurchaseSummary]
    total: int


class CreatePurchaseRequest(BaseModel):
    region: str = ""
    items: list[dict]


class CreatePurchaseResponse(BaseModel):
    purchase_id: int


class ItemSummary(BaseModel):
    session_id: str
    cte_name: str
    quantity: float
    unit: str | None = None
    nmck_per_unit: float
    total_nmck: float
    coefficient_of_variation: float
    is_homogeneous: bool
    num_prices_used: int
    median_price: float
    weighted_average_price: float


class PurchaseSummaryBoard(BaseModel):
    purchase_id: int
    region: str
    items_count: int
    completed_count: int
    grand_total_nmck: float
    grand_total_nmck_words: str
    items: list[ItemSummary]
    any_non_homogeneous: bool
    average_cv: float
