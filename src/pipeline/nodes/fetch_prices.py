from datetime import datetime
import polars as pl
from src.pipeline.state import PriceRecord
from src.data_access.polars_repo import ContractRepository


def apply_time_adjustment(
    price: float,
    contract_date: datetime,
    calculation_date: datetime,
) -> tuple[float, float, str]:
    months_ago = (calculation_date - contract_date).days / 30.44

    if months_ago <= 6:
        return price, 1.0, "Актуальная цена (давность <= 6 мес.)"
    elif months_ago <= 12:
        kd = 1.05
        return round(price * kd, 2), kd, f"Пересчёт kd={kd} (давность {months_ago:.0f} мес.)"
    else:
        return 0.0, 0.0, "Отсечено: давность > 12 месяцев"


def fetch_prices(
    approved_cte_ids: list[int],
    target_region: str | None,
    target_unit: str,
    contract_repo: ContractRepository,
    calculation_date: datetime | None = None,
) -> tuple[list[PriceRecord], bool]:
    if calculation_date is None:
        calculation_date = datetime.now()

    region_fallback = False

    # Cascade: region+unit → all_regions+unit → region+all_units → all
    df = contract_repo.get_prices_for_ctes(approved_cte_ids, region=target_region, unit=target_unit)

    if df.height < 3 and target_region:
        df = contract_repo.get_prices_for_ctes(approved_cte_ids, region=None, unit=target_unit)
        region_fallback = True

    if df.height < 3:
        df = contract_repo.get_prices_for_ctes(approved_cte_ids, region=target_region, unit=None)
        region_fallback = False

    if df.height < 3 and target_region:
        df = contract_repo.get_prices_for_ctes(approved_cte_ids, region=None, unit=None)
        region_fallback = True

    records: list[PriceRecord] = []
    for row in df.iter_rows(named=True):
        contract_date = row["Дата заключения контракта"]
        if contract_date is None:
            continue

        price = row["Цена за единицу"]
        adjusted, kd, _ = apply_time_adjustment(price, contract_date, calculation_date)

        if kd == 0.0:
            continue

        records.append(PriceRecord(
            cte_id=row["Идентификатор СТЕ по контракту"],
            cte_name=row["Наименование позиции СТЕ"],
            price_original=price,
            price_adjusted=adjusted,
            kd=kd,
            date=contract_date.strftime("%Y-%m-%d"),
            region=row["Регион заказчика"],
            contract_id=row["Идентификатор контракта"],
            vat_rate=row["Ставка НДС"],
            quantity=row["Количество"],
            unit=row["Единица измерения"],
            is_regional=(row["Регион заказчика"] == target_region) if target_region else True,
            source="contract",
        ))

    return records, region_fallback
