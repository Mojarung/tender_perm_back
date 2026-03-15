"""Contract data repository using Polars for high-performance filtering."""

import json
import logging
from datetime import datetime, timedelta
from pathlib import Path

import polars as pl

logger = logging.getLogger(__name__)


class ContractRepository:
    """Singleton-like repository for contract data loaded via Polars."""

    _df: pl.DataFrame | None = None
    _loaded: bool = False

    @classmethod
    def load_data(cls, file_path: Path) -> None:
        """Load contracts.json into a Polars DataFrame."""
        logger.info("Loading contracts from %s ...", file_path)
        with open(file_path, "r", encoding="utf-8") as f:
            raw = json.load(f)
        logger.info("Loaded %d contract records from JSON", len(raw))

        cls._df = pl.DataFrame(raw)

        # Parse and cast columns
        cls._df = cls._df.with_columns(
            pl.col("Дата заключения контракта")
            .str.to_datetime("%Y-%m-%d %H:%M:%S%.f", strict=False)
            .alias("Дата заключения контракта"),
            pl.col("Цена за единицу").cast(pl.Float64),
            pl.col("Количество").cast(pl.Float64),
            pl.col("Идентификатор СТЕ по контракту").cast(pl.Int64),
            pl.col("Идентификатор контракта").cast(pl.Int64),
        )
        cls._loaded = True
        logger.info(
            "Contract DataFrame ready: %d rows, %d columns",
            cls._df.height,
            cls._df.width,
        )

    @classmethod
    def is_loaded(cls) -> bool:
        return cls._loaded

    @classmethod
    def get_units_by_cte(cls, cte_ids: list[int]) -> dict[int, list[str]]:
        """Get a mapping of CTE ID to its available units of measurement."""
        if cls._df is None:
            return {}
            
        df_filtered = cls._df.filter(pl.col("Идентификатор СТЕ по контракту").is_in(cte_ids))
        if df_filtered.height == 0:
            return {}
            
        grouped = df_filtered.group_by("Идентификатор СТЕ по контракту").agg(
            pl.col("Единица измерения").drop_nulls().unique()
        )
        
        result = {}
        for row in grouped.iter_rows():
            cte_id = row[0]
            units = row[1]
            result[cte_id] = [str(u) for u in units if str(u).strip()]
        return result

    @classmethod
    def get_prices_for_ctes(
        cls,
        cte_ids: list[int],
        region: str | None = None,
        months_back: int = 12,
        units: list[str] | None = None,
    ) -> pl.DataFrame:
        """
        Filter contracts by CTE IDs, optional region, optional units, and date window.

        Returns a DataFrame with relevant contract rows.
        """
        if cls._df is None:
            raise ValueError("Contract data not loaded. Call load_data() first.")

        query = cls._df.filter(
            pl.col("Идентификатор СТЕ по контракту").is_in(cte_ids)
        )

        if region:
            query = query.filter(pl.col("Регион заказчика") == region)
            
        if units and len(units) > 0:
            query = query.filter(pl.col("Единица измерения").is_in(units))

        logger.info(
            "Found %d price records for %d CTE IDs (region=%s, units=%s, months_back=%d)",
            query.height,
            len(cte_ids),
            region,
            units,
            months_back,
        )
        return query

    @classmethod
    def add_time_weights(cls, df: pl.DataFrame) -> pl.DataFrame:
        """Add time_weight column: newer contracts weigh more (decay over 1 year)."""
        now = datetime.now()
        return df.with_columns(
            (
                pl.lit(1.0)
                / (
                    pl.lit(1.0)
                    + (
                        (pl.lit(now) - pl.col("Дата заключения контракта")).dt.total_days()
                        / 365.0
                    )
                )
            ).alias("time_weight")
        )

    @classmethod
    def get_analog_stats(cls, cte_ids: list[int], months_back: int = 12) -> dict[int, dict]:
        """Per-CTE stats: contract count, regions, unique suppliers (last N months)."""
        if cls._df is None or not cte_ids:
            return {}

        df = cls._df.filter(
            pl.col("Идентификатор СТЕ по контракту").is_in(cte_ids)
        )

        if df.height == 0:
            return {}

        grouped = df.group_by("Идентификатор СТЕ по контракту").agg(
            pl.len().alias("contract_count"),
            pl.col("Регион заказчика").drop_nulls().unique().alias("regions"),
            pl.col("ИНН поставщика").drop_nulls().n_unique().alias("unique_suppliers"),
        )

        result = {}
        for row in grouped.iter_rows(named=True):
            cte_id = row["Идентификатор СТЕ по контракту"]
            result[cte_id] = {
                "contract_count": row["contract_count"],
                "regions": sorted([str(r) for r in row["regions"] if r]),
                "unique_suppliers": row["unique_suppliers"],
            }
        return result

    @classmethod
    def get_region_price_stats(
        cls, cte_ids: list[int], months_back: int = 12, units: list[str] | None = None
    ) -> list[dict]:
        """Per-region price stats: avg, median, min, max, count, unique suppliers."""
        if cls._df is None or not cte_ids:
            return []

        df = cls._df.filter(
            pl.col("Идентификатор СТЕ по контракту").is_in(cte_ids)
            & (pl.col("Цена за единицу") > 0)
        )

        if units and len(units) > 0:
            df = df.filter(pl.col("Единица измерения").is_in(units))

        if df.height == 0:
            return []

        grouped = df.group_by("Регион заказчика").agg(
            pl.col("Цена за единицу").mean().alias("avg_price"),
            pl.col("Цена за единицу").median().alias("median_price"),
            pl.col("Цена за единицу").min().alias("min_price"),
            pl.col("Цена за единицу").max().alias("max_price"),
            pl.len().alias("contract_count"),
            pl.col("ИНН поставщика").drop_nulls().n_unique().alias("unique_suppliers"),
        )

        return grouped.rename({"Регион заказчика": "region"}).to_dicts()

    @classmethod
    def get_all_regions(cls) -> list[str]:
        """Return list of unique regions."""
        if cls._df is None:
            return []
        return (
            cls._df.select("Регион заказчика")
            .unique()
            .sort("Регион заказчика")
            .to_series()
            .to_list()
        )
