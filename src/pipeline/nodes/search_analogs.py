from src.pipeline.state import AnalogItem
from src.data_access.cte_repo import CTERepository
from src.data_access.polars_repo import ContractRepository
from src.data_access.qdrant_repo import QdrantRepository
from src.ml.embeddings import EmbeddingService, build_embedding_text
from src.ml.matching import match_score, combined_score


def search_analogs(
    target_cte_id: int | None,
    target_cte_name: str,
    cte_repo: CTERepository,
    contract_repo: ContractRepository,
    qdrant_repo: QdrantRepository | None = None,
    embedding_service: EmbeddingService | None = None,
) -> list[AnalogItem]:
    results: dict[int, AnalogItem] = {}
    target_item = None

    if target_cte_id:
        target_item = cte_repo.get(target_cte_id)

    # Stage 1: exact match
    if target_cte_id:
        prices = contract_repo.get_prices_for_cte(target_cte_id)
        if prices.height > 0 and target_item:
            results[target_cte_id] = AnalogItem(
                cte_id=target_cte_id,
                name=target_item["name"],
                category=target_item["category"],
                cosine_score=1.0,
                char_match_score=1.0,
                combined_score=1.0,
                source="exact",
            )

    # Stage 2: category + characteristics
    if target_item:
        category = target_item["category"]
        target_chars = target_item["characteristics"]
        candidates = cte_repo.get_by_category(category)

        for cand in candidates:
            cand_id = cand["cte_id"]
            if cand_id in results:
                continue
            cand_chars = cand["characteristics"]
            char_score, details = match_score(target_chars, cand_chars)
            if char_score > 0.3:
                cs = combined_score(0.0, char_score, "category")
                results[cand_id] = AnalogItem(
                    cte_id=cand_id,
                    name=cand["name"],
                    category=cand["category"],
                    cosine_score=0.0,
                    char_match_score=char_score,
                    combined_score=cs,
                    source="category",
                    match_details=details,
                )

    # Stages 3-4: semantic search (only if embeddings enabled)
    if not qdrant_repo or not embedding_service:
        sorted_results = sorted(results.values(), key=lambda x: x.combined_score, reverse=True)
        return sorted_results[:20]

    if target_item:
        text = build_embedding_text(target_item)
    else:
        text = target_cte_name

    vector = embedding_service.encode_single(text)
    category_filter = target_item["category"] if target_item else None
    qdrant_results = qdrant_repo.search(
        vector=vector,
        category=category_filter,
        limit=50,
        score_threshold=0.70,
    )

    for qr in qdrant_results:
        cand_id = qr["cte_id"]
        if cand_id in results:
            existing = results[cand_id]
            existing.cosine_score = qr["cosine_score"]
            existing.combined_score = combined_score(
                qr["cosine_score"], existing.char_match_score, existing.source
            )
            continue

        cand_item = cte_repo.get(cand_id)
        char_score = 0.0
        details = {}
        if target_item and cand_item:
            char_score, details = match_score(
                target_item["characteristics"],
                cand_item["characteristics"],
            )

        cs = combined_score(qr["cosine_score"], char_score, "semantic")
        results[cand_id] = AnalogItem(
            cte_id=cand_id,
            name=qr["name"],
            category=qr["category"],
            cosine_score=qr["cosine_score"],
            char_match_score=char_score,
            combined_score=cs,
            source="semantic",
            match_details=details,
        )

    # Stage 4: extended search if < 3 results with prices
    cte_ids_with_prices = set()
    for cid in results:
        if contract_repo.get_prices_for_cte(cid).height > 0:
            cte_ids_with_prices.add(cid)

    if len(cte_ids_with_prices) < 3:
        extended = qdrant_repo.search(
            vector=vector,
            category=None,
            limit=100,
            score_threshold=0.80,
        )
        for qr in extended:
            cand_id = qr["cte_id"]
            if cand_id in results:
                continue
            cand_item = cte_repo.get(cand_id)
            char_score = 0.0
            details = {}
            if target_item and cand_item:
                char_score, details = match_score(
                    target_item["characteristics"],
                    cand_item["characteristics"],
                )
            cs = combined_score(qr["cosine_score"], char_score, "extended")
            results[cand_id] = AnalogItem(
                cte_id=cand_id,
                name=qr["name"],
                category=qr["category"],
                cosine_score=qr["cosine_score"],
                char_match_score=char_score,
                combined_score=cs,
                source="extended",
                match_details=details,
            )

    sorted_results = sorted(results.values(), key=lambda x: x.combined_score, reverse=True)
    return sorted_results[:20]
