import math
from src.pipeline.state import NMCCResult


def calculate_nmcc(prices: list[float], quantity: float) -> NMCCResult:
    n = len(prices)
    if n < 1:
        return NMCCResult(
            mean_price=0, sigma=0, cv_percent=0,
            is_homogeneous=False, nmcc=0, prices_used=0,
            quantity=quantity, interpretation="Нет ценовых данных",
        )

    mean_price = sum(prices) / n
    variance = sum((p - mean_price) ** 2 for p in prices) / n
    sigma = math.sqrt(variance)
    cv = (sigma / mean_price * 100) if mean_price > 0 else 0
    nmcc = mean_price * quantity

    if cv <= 10:
        interpretation = "Однородная выборка"
    elif cv <= 20:
        interpretation = "Средняя вариация"
    elif cv <= 33:
        interpretation = "Значительная вариация"
    else:
        interpretation = "НЕОДНОРОДНАЯ ВЫБОРКА — требуется пересмотр"

    return NMCCResult(
        mean_price=round(mean_price, 2),
        sigma=round(sigma, 2),
        cv_percent=round(cv, 2),
        is_homogeneous=cv <= 33,
        nmcc=round(nmcc, 2),
        prices_used=n,
        quantity=quantity,
        interpretation=interpretation,
    )
