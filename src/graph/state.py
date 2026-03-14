"""LangGraph pipeline state definition."""

from typing import Any, TypedDict


class PipelineState(TypedDict, total=False):
    """State for the NMCK calculation pipeline."""

    # Session
    session_id: str
    target_cte_name: str
    target_category: str | None
    region_filter: str | None
    unit_filter: str | None
    quantity: float
    inflation_coefficient: float

    # Step 1: Analog search
    retrieved_analogs: list[dict[str, Any]]
    user_approved_analogs: list[dict[str, Any]]
    manual_prices_from_analogs: list[dict[str, Any]]

    # Step 2: Price fetching & filtering
    raw_prices: list[dict[str, Any]]
    filtered_prices: list[dict[str, Any]]
    outlier_prices: list[dict[str, Any]]
    user_approved_prices: list[dict[str, Any]]

    # Step 3: Calculation results
    weighted_average_price: float
    median_price: float
    coefficient_of_variation: float
    is_homogeneous: bool
    nmck_per_unit: float
    total_nmck: float
    price_range_min: float
    price_range_max: float

    # Step 4: Document
    document_path: str | None

    # Explainability
    justification: list[dict[str, Any]]

    # Meta
    current_step: str
    error: str | None
