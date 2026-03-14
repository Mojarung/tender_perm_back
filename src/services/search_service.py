"""Search service: hybrid search combining vector similarity + attribute ranking."""

import logging
from typing import Any

logger = logging.getLogger(__name__)


def compute_attribute_overlap(
    query_attrs: dict[str, str],
    candidate_attrs: dict[str, str],
) -> tuple[float, str]:
    """
    Compute attribute overlap between query and candidate.

    Returns (overlap_score 0-1, human-readable match_reason).
    """
    if not query_attrs or not candidate_attrs:
        return 0.0, "Нет атрибутов для сравнения"

    matches = []
    total_keys = len(query_attrs)

    for key, val in query_attrs.items():
        if key in candidate_attrs:
            if candidate_attrs[key] == val:
                matches.append(f"{key}={val} (exact)")
            else:
                matches.append(f"{key} (key only)")

    overlap = len(matches) / total_keys if total_keys > 0 else 0.0
    reason = "; ".join(matches) if matches else "Нет совпадений атрибутов"

    return round(overlap, 4), reason


def _get_keyword_score(query: str, name: str) -> float:
    """Calculate basic word overlap score between query and item name."""
    if not query or not name:
        return 0.0
    
    query = query.lower().replace(",", " ").replace("-", " ")
    name = name.lower().replace(",", " ").replace("-", " ")
    
    query_words = set(w for w in query.split() if len(w) > 2)
    name_words = set(w for w in name.split())
    
    if not query_words:
        return 0.0
    
    matches = query_words.intersection(name_words)
    return len(matches) / len(query_words)


def rank_search_results(
    raw_results: list[dict[str, Any]],
    query_text: str | None = None,
    query_category: str | None = None,
    query_attributes: dict[str, str] | None = None,
    limit: int = 10,
) -> list[dict[str, Any]]:
    """
    Rank raw Qdrant search results using hybrid scoring:
      final_score = (semantic * 0.5) + (keyword_boost * 0.4) + (attr_overlap * 0.1)
    """
    ranked = []

    for result in raw_results:
        cosine_score = result.get("cosine_score", 0.0)
        candidate_name = result.get("name", "")
        candidate_attrs = result.get("attributes", {})
        candidate_category = result.get("category", "")

        # 1. Keyword Boost (Lexical overlap)
        keyword_score = 0.0
        if query_text:
            keyword_score = _get_keyword_score(query_text, candidate_name)

        # 2. Attribute overlap
        attr_overlap = 0.0
        attr_reason = ""
        if query_attributes:
            attr_overlap, attr_reason = compute_attribute_overlap(
                query_attributes, candidate_attrs
            )

        # 3. Category match bonus
        category_match = ""
        if query_category and candidate_category:
            if candidate_category.lower() == query_category.lower():
                category_match = "Категория: Точное совпадение"
            elif query_category.lower() in candidate_category.lower():
                category_match = "Категория: Частичное совпадение"

        # 4. Final score (Hybrid weighted)
        # We value keywords strongly to fix "Accordion vs Chair" issues
        final_score = (cosine_score * 0.5) + (keyword_score * 0.4) + (attr_overlap * 0.1)
        
        # Apply category bonus if matched
        if category_match:
            final_score = min(1.0, final_score + 0.05)

        # Build match reason
        reason_parts = []
        if keyword_score > 0:
            reason_parts.append(f"Текст: {int(keyword_score*100)}%")
        if category_match:
            reason_parts.append(category_match)
        reason_parts.append(f"Вектор: {cosine_score:.2f}")

        ranked.append(
            {
                **result,
                "attribute_overlap": attr_overlap,
                "final_score": round(final_score, 4),
                "match_reason": " | ".join(reason_parts),
            }
        )

    # Sort by final_score descending
    ranked.sort(key=lambda x: x["final_score"], reverse=True)

    return ranked[:limit]
