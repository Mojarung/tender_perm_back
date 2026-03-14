"""
Initial data parsing script.
Reads raw JSON files, cleans them, and saves as Parquet for fast loading.
"""
import sys
import json
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import polars as pl
from src.cleaning.clean_cte import load_and_clean_cte
from src.cleaning.clean_contracts import load_and_clean_contracts


DATA_DIR = Path(__file__).resolve().parent.parent / "data"


def parse_cte():
    cte_path = DATA_DIR / "cte.json"
    if not cte_path.exists():
        print(f"CTE file not found: {cte_path}")
        return

    print(f"Parsing CTE from {cte_path}...")
    start = time.time()
    items = load_and_clean_cte(cte_path)
    elapsed = time.time() - start
    print(f"  Parsed {len(items)} CTE items in {elapsed:.1f}s")

    chars_flat = []
    for item in items:
        for k, v in item["characteristics"].items():
            chars_flat.append({
                "cte_id": item["cte_id"],
                "key": k,
                "value": v,
            })

    cte_rows = []
    for item in items:
        cte_rows.append({
            "cte_id": item["cte_id"],
            "name": item["name"],
            "category": item["category"],
            "manufacturer": item["manufacturer"],
            "raw_name": item["raw_name"],
            "num_characteristics": len(item["characteristics"]),
        })

    cte_df = pl.DataFrame(cte_rows)
    chars_df = pl.DataFrame(chars_flat)

    output_cte = DATA_DIR / "cte_clean.parquet"
    output_chars = DATA_DIR / "cte_characteristics.parquet"

    cte_df.write_parquet(output_cte)
    chars_df.write_parquet(output_chars)

    print(f"  Saved CTE table: {output_cte} ({cte_df.height} rows)")
    print(f"  Saved characteristics table: {output_chars} ({chars_df.height} rows)")

    print("\n  CTE stats:")
    print(f"    Total items: {cte_df.height}")
    print(f"    Categories: {cte_df['category'].n_unique()}")
    print(f"    Items without characteristics: {(cte_df['num_characteristics'] == 0).sum()}")
    print(f"    Unique characteristic keys: {chars_df['key'].n_unique()}")


def parse_contracts():
    contracts_path = DATA_DIR / "contracts.json"
    if not contracts_path.exists():
        alt_path = DATA_DIR.parent / "contracts (2).json"
        if alt_path.exists():
            print(f"Using alternative path: {alt_path}")
            contracts_path = alt_path
        else:
            print(f"Contracts file not found: {contracts_path}")
            return

    print(f"\nParsing contracts from {contracts_path}...")
    start = time.time()
    df = load_and_clean_contracts(contracts_path)
    elapsed = time.time() - start
    print(f"  Parsed {df.height} contracts in {elapsed:.1f}s")

    output = DATA_DIR / "contracts_clean.parquet"
    df.write_parquet(output)
    print(f"  Saved: {output} ({df.height} rows)")

    print("\n  Contract stats:")
    print(f"    Total rows: {df.height}")
    print(f"    Unique contracts: {df['Идентификатор контракта'].n_unique()}")
    print(f"    Unique CTE IDs: {df['Идентификатор СТЕ по контракту'].n_unique()}")
    print(f"    Regions: {df['Регион заказчика'].n_unique()}")
    print(f"    Date range: {df['Дата заключения контракта'].min()} — {df['Дата заключения контракта'].max()}")
    print(f"    Suspicious prices (<1 rub): {df.filter(pl.col('suspicious_price')).height}")
    print(f"    Expensive prices (>1M rub): {df.filter(pl.col('expensive_price')).height}")

    print("\n  Region breakdown:")
    regions = (
        df.group_by("Регион заказчика")
        .agg(pl.len().alias("count"))
        .sort("count", descending=True)
    )
    for row in regions.iter_rows(named=True):
        pct = row["count"] / df.height * 100
        print(f"    {row['Регион заказчика']}: {row['count']} ({pct:.1f}%)")

    print("\n  VAT breakdown:")
    vats = (
        df.group_by("Ставка НДС")
        .agg(pl.len().alias("count"))
        .sort("count", descending=True)
    )
    for row in vats.iter_rows(named=True):
        pct = row["count"] / df.height * 100
        print(f"    {row['Ставка НДС']}: {row['count']} ({pct:.1f}%)")

    print("\n  Unit breakdown:")
    units = (
        df.group_by("Единица измерения")
        .agg(pl.len().alias("count"))
        .sort("count", descending=True)
        .head(10)
    )
    for row in units.iter_rows(named=True):
        pct = row["count"] / df.height * 100
        print(f"    {row['Единица измерения']}: {row['count']} ({pct:.1f}%)")


if __name__ == "__main__":
    parse_cte()
    parse_contracts()
    print("\nDone!")
