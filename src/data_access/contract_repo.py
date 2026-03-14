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
        unit: str | None = None,
    ) -> pl.DataFrame:
        """
        Filter contracts by CTE IDs, optional region, optional unit, and date window.

        Returns a DataFrame with relevant contract rows.
        """
        if cls._df is None:
            raise ValueError("Contract data not loaded. Call load_data() first.")

        cutoff = datetime.now() - timedelta(days=months_back * 30)

        query = cls._df.filter(
            pl.col("Идентификатор СТЕ по контракту").is_in(cte_ids)
            & (pl.col("Дата заключения контракта") >= cutoff)
        )

        if region:
            query = query.filter(pl.col("Регион заказчика") == region)
            
        if unit:
            query = query.filter(pl.col("Единица измерения") == unit)

        logger.info(
            "Found %d price records for %d CTE IDs (region=%s, unit=%s, months_back=%d)",
            query.height,
            len(cte_ids),
            region,
            unit,
            months_back,
        )
        return query

    @classmethod
    def add_time_weights(cls, df: pl.DataFrame) -> pl.DataFrame:
        """Add time_weight column: newer contracts weigh more (decay over 1 year)."""
        now = datetime.now()
        return df.with_columns(
            (
                1.0
                / (
                    1.0
                    + (
                        (pl.lit(now) - pl.col("Дата заключения контракта")).dt.total_days()
                        / 365.0
                    )
                )
            ).alias("time_weight")
        )

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
