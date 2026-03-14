"""NMCK calculation service — own formulas based on comparable prices method."""

import logging
from dataclasses import dataclass
from typing import Any

from src.ml.stats import PriceAnalysisResult

logger = logging.getLogger(__name__)


@dataclass
class NMCKCalculation:
    """Final NMCK calculation result."""

    weighted_average_price: float = 0.0
    median_price: float = 0.0
    coefficient_of_variation: float = 0.0
    is_homogeneous: bool = True
    nmck_per_unit: float = 0.0
    total_nmck: float = 0.0
    price_range_min: float = 0.0
    price_range_max: float = 0.0
    num_prices_used: int = 0
    justification: list[dict[str, Any]] | None = None


def calculate_nmck(
    analysis: PriceAnalysisResult,
    quantity: float = 1.0,
    inflation_coefficient: float = 1.0,
    max_cv: float = 33.0,
) -> NMCKCalculation:
    """
    Calculate NMCK using the comparable prices method.

    Formulas:
    1. Weighted average price (using time_weight if available):
       Ц_avg = Σ(Цi * wi) / Σ(wi)

    2. Coefficient of variation:
       V = (σ / Ц_avg) * 100%

    3. NMCK per unit:
       НМЦК_ед = Ц_avg * K_infl

    4. Total NMCK:
       НМЦК = НМЦК_ед * Q

    5. Price range:
       Ц_min = Ц_avg * (1 - V/100)
       Ц_max = Ц_avg * (1 + V/100)
    """
    if analysis.num_prices == 0:
        logger.warning("No valid prices for NMCK calculation")
        return NMCKCalculation()

    avg_price = analysis.weighted_average
    median_price = analysis.median
    cv = analysis.coefficient_of_variation
    is_homogeneous = cv <= max_cv

    # If inhomogeneous, use median instead of weighted average
    base_price = avg_price if is_homogeneous else median_price

    nmck_per_unit = round(base_price * inflation_coefficient, 2)
    total_nmck = round(nmck_per_unit * quantity, 2)

    # Price range based on CV (clamped to reasonable bounds)
    cv_factor = min(cv / 100, 0.5)  # cap at 50% range
    price_range_min = round(base_price * (1 - cv_factor), 2)
    price_range_max = round(base_price * (1 + cv_factor), 2)

    # Build justification
    justification = [
        {
            "step": "price_analysis",
            "description": "Статистика цен",
            "data": {
                "num_prices": analysis.num_prices,
                "mean": analysis.mean,
                "median": analysis.median,
                "weighted_average": analysis.weighted_average,
                "std_dev": analysis.std_dev,
            },
        },
        {
            "step": "homogeneity_check",
            "description": "Проверка однородности выборки",
            "data": {
                "coefficient_of_variation": cv,
                "threshold": max_cv,
                "is_homogeneous": is_homogeneous,
                "verdict": (
                    f"V={cv:.1f}% ≤ {max_cv}% — выборка однородна, используется средневзвешенная цена"
                    if is_homogeneous
                    else f"V={cv:.1f}% > {max_cv}% — выборка неоднородна, используется медиана"
                ),
            },
        },
        {
            "step": "nmck_calculation",
            "description": "Расчёт НМЦК",
            "data": {
                "base_price": base_price,
                "inflation_coefficient": inflation_coefficient,
                "nmck_per_unit": nmck_per_unit,
                "quantity": quantity,
                "total_nmck": total_nmck,
                "price_range": f"{price_range_min} — {price_range_max}",
            },
        },
    ]

    return NMCKCalculation(
        weighted_average_price=analysis.weighted_average,
        median_price=analysis.median,
        coefficient_of_variation=cv,
        is_homogeneous=is_homogeneous,
        nmck_per_unit=nmck_per_unit,
        total_nmck=total_nmck,
        price_range_min=price_range_min,
        price_range_max=price_range_max,
        num_prices_used=analysis.num_prices,
        justification=justification,
    )
