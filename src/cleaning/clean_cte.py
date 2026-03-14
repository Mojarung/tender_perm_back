import json
import re
from pathlib import Path


NUMERIC_REGEX = re.compile(r"(\d+[\.,]?\d*)\s*(л|мл|мм|см|м|кг|г|шт|мкм|%)")
HTML_ENTITIES = {"&amp;": "&", "&lt;": "<", "&gt;": ">", "&quot;": '"', "&#39;": "'"}
MULTI_SPACE = re.compile(r"\s+")


def _normalize_name(name: str) -> str:
    for entity, char in HTML_ENTITIES.items():
        name = name.replace(entity, char)
    name = name.replace("\t", " ").replace("\r", " ").replace("\n", " ")
    name = MULTI_SPACE.sub(" ", name).strip()
    return name


def _convert_characteristics(raw: list[list[str]]) -> dict[str, str]:
    result = {}
    for pair in raw:
        if len(pair) >= 2:
            key, value = pair[0].strip(), pair[1].strip()
            if key and value:
                result[key] = value
    return result


def _parse_numbers_from_name(name: str) -> dict[str, float]:
    parsed = {}
    for match in NUMERIC_REGEX.finditer(name):
        num_str = match.group(1).replace(",", ".")
        unit = match.group(2)
        try:
            parsed[unit] = float(num_str)
        except ValueError:
            continue
    return parsed


def clean_cte_record(raw: dict) -> dict:
    raw_name = raw.get("Наименование СТЕ", "")
    name = _normalize_name(raw_name)
    characteristics = _convert_characteristics(raw.get("характеристики СТЕ", []))
    parsed_from_name = _parse_numbers_from_name(name)

    return {
        "cte_id": raw["Идентификатор СТЕ"],
        "name": name,
        "category": raw.get("Категория", ""),
        "manufacturer": raw.get("Производитель", ""),
        "characteristics": characteristics,
        "parsed_from_name": parsed_from_name,
        "raw_name": raw_name,
    }


def load_and_clean_cte(path: Path) -> list[dict]:
    with open(path, "r", encoding="utf-8") as f:
        raw_data = json.load(f)
    return [clean_cte_record(item) for item in raw_data]
