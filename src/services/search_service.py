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


def rank_search_results(
    raw_results: list[dict[str, Any]],
    query_category: str | None = None,
    query_attributes: dict[str, str] | None = None,
    cosine_weight: float = 0.6,
    attribute_weight: float = 0.4,
    limit: int = 10,
) -> list[dict[str, Any]]:
    """
    Rank raw Qdrant search results using combined score:
      final_score = cosine_weight * cosine_score + attribute_weight * attribute_overlap

    Also builds match_reason for each result (explainability).
    """
    ranked = []

    for result in raw_results:
        cosine_score = result.get("cosine_score", 0.0)
        candidate_attrs = result.get("attributes", {})
        candidate_category = result.get("category", "")

        # Attribute overlap
        attr_overlap = 0.0
        attr_reason = ""
        if query_attributes:
            attr_overlap, attr_reason = compute_attribute_overlap(
                query_attributes, candidate_attrs
            )

        # Category match bonus
        category_match = ""
        if query_category and candidate_category:
            if candidate_category.lower() == query_category.lower():
                category_match = f"Категория: {candidate_category} (exact match)"
            elif query_category.lower() in candidate_category.lower():
                category_match = f"Категория: частичное совпадение ({candidate_category})"

        # Final score
        final_score = cosine_weight * cosine_score + attribute_weight * attr_overlap

        # Build match reason
        reason_parts = []
        if category_match:
            reason_parts.append(category_match)
        reason_parts.append(f"Cosine: {cosine_score:.4f}")
        if attr_reason:
            reason_parts.append(f"Атрибуты: {attr_reason}")

        ranked.append(
            {
                **result,
                "attribute_overlap": attr_overlap,
                "final_score": round(final_score, 4),
                "match_reason": ". ".join(reason_parts),
            }
        )

    # Sort by final_score descending
    ranked.sort(key=lambda x: x["final_score"], reverse=True)

    return ranked[:limit]
