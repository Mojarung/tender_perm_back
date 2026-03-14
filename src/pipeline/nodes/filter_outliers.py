import math
from src.pipeline.state import PriceRecord


def iqr_filter(
    prices: list[PriceRecord],
    coefficient: float = 1.5,
) -> tuple[list[PriceRecord], list[PriceRecord], str]:
    if len(prices) < 4:
        return prices, [], "Недостаточно данных для IQR-фильтрации"

    sorted_prices = sorted(prices, key=lambda p: p.price_adjusted)
    values = [p.price_adjusted for p in sorted_prices]

    n = len(values)
    q1_idx = n // 4
    q3_idx = (3 * n) // 4
    q1 = values[q1_idx]
    q3 = values[q3_idx]
    iqr = q3 - q1

    lower = q1 - coefficient * iqr
    upper = q3 + coefficient * iqr

    valid = []
    outliers = []
    for p in prices:
        if lower <= p.price_adjusted <= upper:
            valid.append(p)
        else:
            outlier = p.model_copy()
            outlier.is_outlier = True
            outliers.append(outlier)

    justification = (
        f"Фильтрация выбросов методом межквартильного размаха: "
        f"Q1={q1:.2f} руб, Q3={q3:.2f} руб, IQR={iqr:.2f} руб. "
        f"Допустимый диапазон: [{lower:.2f}, {upper:.2f}] руб. "
        f"Отсечено {len(outliers)} из {len(prices)} ценовых значений."
    )

    return valid, outliers, justification


def filter_outliers(
    prices: list[PriceRecord],
) -> tuple[list[PriceRecord], list[PriceRecord], str]:
    valid, outliers, justification = iqr_filter(prices, coefficient=1.5)

    if len(valid) < 3 and len(prices) >= 3:
        valid, outliers, justification = iqr_filter(prices, coefficient=2.5)

    if len(valid) < 3:
        return prices, [], justification + " Применены все цены из-за недостатка данных."

    return valid, outliers, justification
