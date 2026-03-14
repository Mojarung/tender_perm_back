from pydantic import BaseModel, Field


class AnalogItem(BaseModel):
    cte_id: int
    name: str
    category: str
    cosine_score: float = 0.0
    char_match_score: float = 0.0
    combined_score: float = 0.0
    source: str = "category"
    match_details: dict = Field(default_factory=dict)


class PriceRecord(BaseModel):
    cte_id: int
    cte_name: str
    price_original: float
    price_adjusted: float
    kd: float = 1.0
    date: str
    region: str
    contract_id: int
    vat_rate: str
    quantity: float
    unit: str
    is_outlier: bool = False
    is_regional: bool = False
    source: str = "contract"


class NMCCResult(BaseModel):
    mean_price: float
    sigma: float
    cv_percent: float
    is_homogeneous: bool
    nmcc: float
    prices_used: int
    quantity: float
    interpretation: str


class PipelineState(BaseModel):
    session_id: str

    target_cte_id: int | None = None
    target_cte_name: str = ""
    target_quantity: float = 1.0
    target_unit: str = "шт"
    target_region: str | None = None

    found_analogs: list[AnalogItem] = Field(default_factory=list)
    user_approved_analogs: list[AnalogItem] = Field(default_factory=list)

    all_prices: list[PriceRecord] = Field(default_factory=list)
    valid_prices: list[PriceRecord] = Field(default_factory=list)
    outlier_prices: list[PriceRecord] = Field(default_factory=list)
    outlier_justification: str = ""
    user_approved_prices: list[PriceRecord] = Field(default_factory=list)

    nmcc_result: NMCCResult | None = None
    document_path: str | None = None

    current_step: str = "init"
    region_fallback_used: bool = False
    errors: list[str] = Field(default_factory=list)
