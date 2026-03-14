import polars as pl
from pathlib import Path
from src.cleaning.clean_contracts import load_and_clean_contracts


class ContractRepository:
    def __init__(self) -> None:
        self._df: pl.DataFrame | None = None

    def load(self, path: Path) -> None:
        self._df = load_and_clean_contracts(path)

    @property
    def df(self) -> pl.DataFrame:
        if self._df is None:
            raise RuntimeError("Contract data not loaded")
        return self._df

    def get_prices_for_cte(self, cte_id: int) -> pl.DataFrame:
        return self.df.filter(pl.col("Идентификатор СТЕ по контракту") == cte_id)

    def get_prices_for_ctes(
        self,
        cte_ids: list[int],
        region: str | None = None,
        unit: str | None = None,
    ) -> pl.DataFrame:
        result = self.df.filter(
            pl.col("Идентификатор СТЕ по контракту").is_in(cte_ids)
        )
        if region:
            result = result.filter(pl.col("Регион заказчика") == region)
        if unit:
            result = result.filter(pl.col("Единица измерения") == unit)
        return result

    def get_regions(self) -> list[str]:
        return (
            self.df.select("Регион заказчика")
            .unique()
            .sort("Регион заказчика")
            .to_series()
            .to_list()
        )

    def get_units_for_cte(self, cte_id: int) -> list[str]:
        return (
            self.get_prices_for_cte(cte_id)
            .select("Единица измерения")
            .unique()
            .to_series()
            .to_list()
        )

    def get_most_common_unit(self, cte_id: int) -> str | None:
        units = (
            self.get_prices_for_cte(cte_id)
            .group_by("Единица измерения")
            .agg(pl.len().alias("count"))
            .sort("count", descending=True)
        )
        if units.height == 0:
            return None
        return units.row(0)[0]

    @property
    def size(self) -> int:
        return self.df.height
