"""Statistical analysis: outlier detection and price metrics."""

import logging
from dataclasses import dataclass, field

import numpy as np
import polars as pl
from sklearn.ensemble import IsolationForest

logger = logging.getLogger(__name__)


@dataclass
class PriceAnalysisResult:
    """Result of price analysis with outlier detection and statistics."""

    valid_prices: list[dict] = field(default_factory=list)
    outlier_prices: list[dict] = field(default_factory=list)
    median: float = 0.0
    mean: float = 0.0
    weighted_average: float = 0.0
    std_dev: float = 0.0
    coefficient_of_variation: float = 0.0
    is_homogeneous: bool = True  # True if CV ≤ 33%
    num_prices: int = 0


def analyze_prices(
    df_prices: pl.DataFrame,
    price_col: str = "Цена за единицу",
    max_cv: float = 33.0,
) -> PriceAnalysisResult:
    """
    Full price analysis pipeline:
    1. Apply IsolationForest to remove outliers (if n >= 3)
    2. Calculate statistics: median, mean, std, CV
    3. Calculate time-weighted average (if time_weight column exists)
    4. Check homogeneity (CV ≤ max_cv)
    """
    if df_prices.height == 0:
        logger.warning("Empty price DataFrame, returning empty result")
        return PriceAnalysisResult()

    # If too few data points, skip outlier detection
    if df_prices.height < 3:
        median_val = df_prices.select(pl.col(price_col).median()).item() or 0.0
        mean_val = df_prices.select(pl.col(price_col).mean()).item() or 0.0
        return PriceAnalysisResult(
            valid_prices=df_prices.to_dicts(),
            outlier_prices=[],
            median=float(median_val),
            mean=float(mean_val),
            weighted_average=float(mean_val),
            std_dev=0.0,
            coefficient_of_variation=0.0,
            is_homogeneous=True,
            num_prices=df_prices.height,
        )

    # ── Step 1: IsolationForest outlier detection ──
    prices_array = df_prices.select(price_col).to_numpy().reshape(-1, 1)

    clf = IsolationForest(random_state=42, contamination="auto")
    predictions = clf.fit_predict(prices_array)

    df_with_preds = df_prices.with_columns(
        pl.Series(name="_is_inlier", values=predictions)
    )
    valid_df = df_with_preds.filter(pl.col("_is_inlier") == 1).drop("_is_inlier")
    outliers_df = df_with_preds.filter(pl.col("_is_inlier") == -1).drop("_is_inlier")

    logger.info(
        "Outlier detection: %d valid, %d outliers (of %d total)",
        valid_df.height,
        outliers_df.height,
        df_prices.height,
    )

    # ── Step 2: Calculate statistics on valid prices ──
    median_val = float(valid_df.select(pl.col(price_col).median()).item() or 0)
    mean_val = float(valid_df.select(pl.col(price_col).mean()).item() or 0)
    std_val = float(valid_df.select(pl.col(price_col).std()).item() or 0)

    # Assign reasons to outliers based on median
    if outliers_df.height > 0 and median_val > 0:
        outliers_dicts = outliers_df.to_dicts()
        for idx, row in enumerate(outliers_dicts):
            price = row.get(price_col, 0)
            if price > median_val:
                diff_percent = ((price - median_val) / median_val) * 100
                outliers_dicts[idx]["_outlier_reason"] = f"Цена значительно выше медианной (+{diff_percent:.0f}%)"
            else:
                diff_percent = ((median_val - price) / median_val) * 100
                outliers_dicts[idx]["_outlier_reason"] = f"Цена значительно ниже медианной (-{diff_percent:.0f}%)"
    else:
        outliers_dicts = outliers_df.to_dicts() if outliers_df.height > 0 else []

    cv = (std_val / mean_val * 100) if mean_val > 0 else 0.0

    # ── Step 3: Time-weighted average ──
    if "time_weight" in valid_df.columns:
        weighted_sum = float(
            valid_df.select(
                (pl.col(price_col) * pl.col("time_weight")).sum()
            ).item()
            or 0
        )
        weight_sum = float(
            valid_df.select(pl.col("time_weight").sum()).item() or 1
        )
        weighted_avg = weighted_sum / weight_sum if weight_sum > 0 else mean_val
    else:
        weighted_avg = mean_val

    return PriceAnalysisResult(
        valid_prices=valid_df.to_dicts(),
        outlier_prices=outliers_dicts,
        median=round(median_val, 2),
        mean=round(mean_val, 2),
        weighted_average=round(weighted_avg, 2),
        std_dev=round(std_val, 2),
        coefficient_of_variation=round(cv, 2),
        is_homogeneous=cv <= max_cv,
        num_prices=valid_df.height,
    )
