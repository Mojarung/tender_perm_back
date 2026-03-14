from src.cleaning.clean_cte import load_and_clean_cte
from pathlib import Path


class CTERepository:
    def __init__(self) -> None:
        self._items: dict[int, dict] = {}
        self._by_category: dict[str, list[dict]] = {}

    def load(self, path: Path) -> None:
        items = load_and_clean_cte(path)
        for item in items:
            self._items[item["cte_id"]] = item
            cat = item["category"]
            if cat not in self._by_category:
                self._by_category[cat] = []
            self._by_category[cat].append(item)

    def get(self, cte_id: int) -> dict | None:
        return self._items.get(cte_id)

    def get_by_category(self, category: str) -> list[dict]:
        return self._by_category.get(category, [])

    def search_by_name(self, query: str, limit: int = 10) -> list[dict]:
        query_lower = query.lower()
        results = []
        for item in self._items.values():
            if query_lower in item["name"].lower():
                results.append(item)
                if len(results) >= limit:
                    break
        return results

    def all_items(self) -> list[dict]:
        return list(self._items.values())

    @property
    def size(self) -> int:
        return len(self._items)

    def get_all_categories(self) -> list[str]:
        return list(self._by_category.keys())
