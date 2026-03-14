import json
import polars as pl
from pathlib import Path


REGION_NORMALIZE = {
    "Сургут": "Ханты-Мансийский автономный округ",
}


def load_and_clean_contracts(path: Path) -> pl.DataFrame:
    with open(path, "r", encoding="utf-8") as f:
        raw = json.load(f)
    df = pl.DataFrame(raw)

    df = df.with_columns([
        pl.col("Дата заключения контракта")
          .str.to_datetime("%Y-%m-%d %H:%M:%S%.f", strict=False)
          .alias("Дата заключения контракта"),
        pl.col("Цена за единицу").cast(pl.Float64),
        pl.col("Количество").cast(pl.Float64),
        pl.col("% снижения").cast(pl.Float64),
    ])

    df = df.filter(pl.col("Количество") > 0)
    df = df.filter(pl.col("Цена за единицу") >= 0.01)

    df = df.unique(
        subset=["Идентификатор контракта", "Идентификатор СТЕ по контракту", "Цена за единицу"],
        keep="first",
    )

    df = df.with_columns(
        pl.col("Наименование позиции СТЕ")
          .str.replace_all(r"_x000D_", " ")
          .str.replace_all(r"\r\n", " ")
          .str.replace_all(r"\r", " ")
          .str.strip_chars()
          .alias("Наименование позиции СТЕ")
    )

    df = df.with_columns(
        pl.col("Регион заказчика")
          .map_elements(
              lambda r: REGION_NORMALIZE.get(r, r),
              return_dtype=pl.Utf8,
          )
          .alias("Регион заказчика")
    )

    df = df.with_columns(
        pl.col("Дата заключения контракта").dt.strftime("%Y-%m").alias("Месяц")
    )

    df = df.with_columns([
        (pl.col("Цена за единицу") < 1.0).alias("suspicious_price"),
        (pl.col("Цена за единицу") > 1_000_000).alias("expensive_price"),
    ])

    return df
