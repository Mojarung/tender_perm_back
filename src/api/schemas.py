from pydantic import BaseModel, Field
from src.pipeline.state import AnalogItem, PriceRecord, NMCCResult


class CreateSessionRequest(BaseModel):
    target_cte_name: str
    target_cte_id: int | None = None
    target_quantity: float = 1.0
    target_unit: str = "шт"
    target_region: str | None = None


class CreateSessionResponse(BaseModel):
    session_id: str
    current_step: str
    found_analogs: list[AnalogItem]


class SessionResponse(BaseModel):
    session_id: str
    current_step: str
    target_cte_name: str
    target_quantity: float
    target_unit: str
    target_region: str | None
    found_analogs: list[AnalogItem]
    user_approved_analogs: list[AnalogItem]
    all_prices: list[PriceRecord]
    valid_prices: list[PriceRecord]
    outlier_prices: list[PriceRecord]
    outlier_justification: str
    nmcc_result: NMCCResult | None
    region_fallback_used: bool
    errors: list[str]


class ApproveAnalogsRequest(BaseModel):
    approved_cte_ids: list[int]


class ApproveAnalogsResponse(BaseModel):
    current_step: str
    all_prices: list[PriceRecord]
    valid_prices: list[PriceRecord]
    outlier_prices: list[PriceRecord]
    outlier_justification: str
    region_fallback_used: bool


class ManualPrice(BaseModel):
    price: float = Field(gt=0)
    source_description: str = "Ручной ввод"


class ApprovePricesRequest(BaseModel):
    approved_price_indices: list[int]
    manual_prices: list[ManualPrice] = Field(default_factory=list)


class ApprovePricesResponse(BaseModel):
    current_step: str
    nmcc_result: NMCCResult


class ApproveCalculationRequest(BaseModel):
    approved: bool


class ApproveCalculationResponse(BaseModel):
    current_step: str
    document_path: str | None = None


class GoBackRequest(BaseModel):
    target_step: str  # "analogs" | "prices"


class CTESearchResult(BaseModel):
    cte_id: int
    name: str
    category: str
    manufacturer: str
