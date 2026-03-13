"""NMCC (НМЦК) calculation service using Polars and ML outlier detection."""

import logging

import polars as pl

from src.ml_client.client import ml_client
from src.schemas.api import NMCKCalculateResponse

logger = logging.getLogger(__name__)


async def calculate_nmck(
    selected_prices: list[float],
    target_ste_id: int | None = None,
    target_region: str | None = None,
) -> NMCKCalculateResponse:
    """
    Calculate NMCC (Начальная Максимальная Цена Контракта):
    1. Detect outliers via IsolationForest (ML Worker)
    2. Compute mean, std, variation coefficient using Polars
    3. Determine if manual input is required (v > 33%)
    """

    # Step 1: Outlier detection via ML Worker
    if len(selected_prices) >= 3:
        try:
            outlier_result = await ml_client.detect_outliers(selected_prices)
            valid_prices = outlier_result["valid_prices"]
            detected_outliers = outlier_result["outliers"]
        except Exception as e:
            logger.warning(f"ML outlier detection failed, using all prices: {e}")
            valid_prices = selected_prices
            detected_outliers = []
    else:
        # Too few prices for IsolationForest
        valid_prices = selected_prices
        detected_outliers = []

    if not valid_prices:
        valid_prices = selected_prices
        detected_outliers = []

    # Step 2: Polars math
    series = pl.Series("prices", valid_prices)

    mean_price = series.mean()
    std_price = series.std()

    # Variation coefficient: v = (std / mean) * 100
    if mean_price and mean_price > 0:
        variation_coefficient = (std_price / mean_price) if std_price else 0.0
    else:
        variation_coefficient = 0.0

    # NMCC = mean price (average method per 44-FZ methodology)
    nmck_value = mean_price if mean_price else 0.0

    # v > 33% means prices are too spread — requires manual justification
    requires_manual_input = variation_coefficient > 0.33

    return NMCKCalculateResponse(
        nmck_value=round(nmck_value, 2),
        variation_coefficient=round(variation_coefficient, 4),
        valid_prices_used=valid_prices,
        detected_outliers=detected_outliers,
        requires_manual_input=requires_manual_input,
    )
