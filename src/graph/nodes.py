"""LangGraph nodes for the NMCK pipeline with human-in-the-loop interrupts."""

import logging


import polars as pl
from langgraph.graph import END, START, StateGraph
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.types import interrupt

from src.graph.state import PipelineState
from src.data_access.contract_repo import ContractRepository
from src.ml.stats import analyze_prices
from src.services.nmck_service import calculate_nmck
from src.services.search_service import rank_search_results
from src.services.document_service import generate_nmck_document
from src.config import settings

logger = logging.getLogger(__name__)

# ── Global references set during app lifespan ──
_embedder = None
_cte_repo = None


def set_dependencies(embedder, cte_repo):
    """Set global references for embedder and CTE repo (called during lifespan)."""
    global _embedder, _cte_repo
    _embedder = embedder
    _cte_repo = cte_repo


def perform_search(state: PipelineState) -> PipelineState:
    """
    Search for analog CTE items using hybrid search:
    1. Embed the user query
    2. Search Qdrant with optional category filter
    3. Rank by combined cosine + attribute overlap
    """
    target_name = state["target_cte_name"]
    category = state.get("target_category")

    # Bypass if known CTE provided (skip vector search)
    if state.get("is_known_cte"):
        logger.info("Known CTE provided, skipping vector search for '%s'", target_name)
        return state

    logger.info("Searching analogs for: '%s' (category=%s)", target_name, category)

    # Embed the query
    query_text = target_name
    if category:
        query_text = f"{target_name} | {category}"

    query_vector = _embedder.encode_single(query_text)

    # Search Qdrant (with category filter if provided)
    raw_results = _cte_repo.search(
        query_vector=query_vector,
        category=category,
        limit=settings.search_top_k,
        score_threshold=settings.search_score_threshold,
    )

    logger.info("Qdrant returned %d raw results", len(raw_results))

    # If category filter returned too few results, try without filter
    if len(raw_results) < 3 and category:
        logger.info("Too few results with category filter, retrying without filter")
        raw_results_no_filter = _cte_repo.search(
            query_vector=query_vector,
            category=None,
            limit=settings.search_top_k,
            score_threshold=settings.search_score_threshold,
        )
        # Merge, preferring filtered results
        seen_ids = {r["cte_id"] for r in raw_results}
        for r in raw_results_no_filter:
            if r["cte_id"] not in seen_ids:
                raw_results.append(r)
                seen_ids.add(r["cte_id"])

    # Rank results with attribute overlap and keyword boost
    ranked = rank_search_results(
        raw_results=raw_results,
        query_text=target_name,
        query_category=category,
        limit=settings.search_result_limit,
    )

    state["retrieved_analogs"] = ranked
    state["current_step"] = "analogs_found"
    return state


def wait_for_analogs(state: PipelineState) -> PipelineState:
    """Dedicated node for human-in-the-loop analog approval."""

    ranked = state.get("retrieved_analogs", [])

    # This node should not be reached if is_known_cte is True due to conditional edge,
    # but we keep a safeguard check.
    if state.get("is_known_cte"):
        return state

    # Interrupt for user to review analogs
    user_decision = interrupt({
        "type": "analog_approval",
        "message": f"Анализ завершен. Найдено {len(ranked)} позиций, соответствующих критериям поиска. Выберите аналоги для дальнейшего сбора цен.",
        "analogs": ranked,
    })

    # User provides approved analog IDs
    approved_ids = user_decision.get("approved_analog_ids", [])
    manual_ids = user_decision.get("manual_cte_ids", [])

    # Filter approved analogs
    approved = [a for a in ranked if a["cte_id"] in approved_ids]

    # Add manually specified CTE IDs
    for mid in manual_ids:
        item = _cte_repo.get_item_by_id(mid)
        if item:
            approved.append({
                "cte_id": item["Идентификатор СТЕ"],
                "name": item["Наименование СТЕ"],
                "category": item.get("Категория", ""),
                "manufacturer": item.get("Производитель", ""),
                "attributes": item.get("_attributes", {}),
                "cosine_score": 0.0,
                "attribute_overlap": 0.0,
                "final_score": 0.0,
                "match_reason": "Добавлено вручную пользователем",
            })

    state["user_approved_analogs"] = approved
    state["manual_prices_from_analogs"] = user_decision.get("manual_prices", [])
    state["unit_filter"] = user_decision.get("units")
    state["current_step"] = "analogs_approved"
    return state


# ── Node: process_prices ──


def process_prices(state: PipelineState) -> PipelineState:
    """
    Fetch and filter prices for approved analogs:
    1. Get CTE IDs from approved analogs
    2. Query contracts via Polars (filter by CTE ID, region, date)
    3. Add time weights
    4. Run IsolationForest outlier detection
    5. Interrupt for user to review prices
    """
    approved_analogs = state.get("user_approved_analogs", [])
    manual_from_analogs = state.get("manual_prices_from_analogs", [])
    region = state.get("region_filter")

    if not approved_analogs and not manual_from_analogs:
        state["error"] = "Нет одобренных аналогов или ручных цен"
        state["current_step"] = "error"
        return state

    cte_ids = [a["cte_id"] for a in approved_analogs]
    logger.info("Fetching prices for %d CTE IDs", len(cte_ids))

    units = state.get("unit_filter")
    
    # Get prices from contracts — with fallback tracking
    search_scope = "region"
    search_months = settings.price_months_back
    prices_df = pl.DataFrame(schema=ContractRepository._df.schema) if ContractRepository._df is not None else pl.DataFrame()

    if cte_ids:
        prices_df = ContractRepository.get_prices_for_ctes(
            cte_ids=cte_ids,
            region=region,
            months_back=settings.price_months_back,
            units=units,
        )

        if prices_df.height == 0 and region:
            logger.warning("No prices found, trying without region filter")
            search_scope = "all_regions"
            prices_df = ContractRepository.get_prices_for_ctes(
                cte_ids=cte_ids,
                region=None,
                months_back=settings.price_months_back,
                units=units,
            )
    else:
        search_scope = "manual_only"
        search_months = 0

    state["price_search_info"] = {
        "requested_region": region or "",
        "scope": search_scope,
        "months": search_months,
    }

    state["raw_prices"] = prices_df.to_dicts()

    # Add time weights
    prices_df = ContractRepository.add_time_weights(prices_df)

    # Run outlier detection
    analysis = analyze_prices(
        prices_df,
        price_col="Цена за единицу",
        max_cv=settings.max_coefficient_of_variation,
    )

    # Add manual prices from the analog stage to the pool of "valid prices" for review
    manual_from_analogs = state.get("manual_prices_from_analogs", [])
    for mp in manual_from_analogs:
        analysis.valid_prices.append({
            "Наименование позиции СТЕ": mp.get("name", "Ручной ввод"),
            "Цена за единицу": mp.get("price", 0),
            "Регион заказчика": mp.get("region") or "",
            "Дата заключения контракта": None,
            "Идентификатор контракта": 0,
            "Идентификатор СТЕ по контракту": 0,
            "Количество": 1.0,
            "Единица измерения": "шт",
            "Способ закупки": "Ручной ввод",
            "time_weight": 1.0,
            "_source": "manual",
        })

    # Re-calculate statistics including manual prices for the UI
    if analysis.valid_prices:
        all_prices = [p["Цена за единицу"] for p in analysis.valid_prices]
        all_weights = [p.get("time_weight", 1.0) for p in analysis.valid_prices]
        
        valid_df = pl.DataFrame(analysis.valid_prices)
        analysis.median = float(valid_df.select(pl.col("Цена за единицу").median()).item() or 0)
        analysis.mean = float(valid_df.select(pl.col("Цена за единицу").mean()).item() or 0)
        std_val = float(valid_df.select(pl.col("Цена за единицу").std()).item() or 0)
        
        analysis.coefficient_of_variation = (std_val / analysis.mean * 100) if analysis.mean > 0 else 0.0
        analysis.is_homogeneous = analysis.coefficient_of_variation <= settings.max_coefficient_of_variation
        
        # Weighted average
        weighted_sum = sum(p * w for p, w in zip(all_prices, all_weights))
        weight_sum = sum(all_weights)
        analysis.weighted_average = weighted_sum / weight_sum if weight_sum > 0 else analysis.mean

    state["filtered_prices"] = analysis.valid_prices
    state["outlier_prices"] = analysis.outlier_prices
    state["current_step"] = "prices_filtered"

    # Interrupt for user to review prices
    user_decision = interrupt({
        "type": "price_approval",
        "message": f"Сбор цен завершен. Успешно обработано {len(analysis.valid_prices)} записей. Коэффициент вариации: {analysis.coefficient_of_variation:.1f}%. Требуется утверждение выборки.",
        "filtered_prices": analysis.valid_prices,
        "outlier_prices": analysis.outlier_prices,
        "search_info": state["price_search_info"],
        "statistics": {
            "median": analysis.median,
            "mean": analysis.mean,
            "weighted_average": analysis.weighted_average,
            "coefficient_of_variation": analysis.coefficient_of_variation,
            "is_homogeneous": analysis.is_homogeneous,
        },
    })

    # User provides approved price indices and optional manual prices
    approved_indices = user_decision.get("approved_price_indices", list(range(len(analysis.valid_prices))))
    manual_prices = user_decision.get("manual_prices", [])

    # Filter approved prices
    approved_prices = [analysis.valid_prices[i] for i in approved_indices if i < len(analysis.valid_prices)]

    # Add manual prices
    for mp in manual_prices:
        approved_prices.append({
            "Наименование позиции СТЕ": mp.get("name", "Ручной ввод"),
            "Цена за единицу": mp.get("price", 0),
            "Регион заказчика": mp.get("region") or "",
            "Дата заключения контракта": None,
            "Идентификатор контракта": 0,
            "Идентификатор СТЕ по контракту": 0,
            "Количество": 1.0,
            "Единица измерения": "шт",
            "Способ закупки": "Ручной ввод",
            "time_weight": 1.0,
            "_source": "manual",
        })

    state["user_approved_prices"] = approved_prices
    state["current_step"] = "prices_approved"
    return state


# ── Node: calculate_nmcc ──


def calculate_nmcc_node(state: PipelineState) -> PipelineState:
    """Calculate NMCK from approved prices."""
    approved_prices = state.get("user_approved_prices", [])
    quantity = state.get("quantity", 1.0)
    inflation = state.get("inflation_coefficient", 1.0)

    if not approved_prices:
        state["error"] = "Нет одобренных цен для расчёта"
        state["current_step"] = "error"
        return state

    # Create DataFrame from approved prices for analysis
    df = pl.DataFrame(approved_prices)

    analysis = analyze_prices(
        df,
        price_col="Цена за единицу",
        max_cv=settings.max_coefficient_of_variation,
    )

    result = calculate_nmck(
        analysis=analysis,
        quantity=quantity,
        inflation_coefficient=inflation,
        max_cv=settings.max_coefficient_of_variation,
    )

    state["weighted_average_price"] = result.weighted_average_price
    state["median_price"] = result.median_price
    state["coefficient_of_variation"] = result.coefficient_of_variation
    state["is_homogeneous"] = result.is_homogeneous
    state["nmck_per_unit"] = result.nmck_per_unit
    state["total_nmck"] = result.total_nmck
    state["price_range_min"] = result.price_range_min
    state["price_range_max"] = result.price_range_max
    state["justification"] = result.justification or []
    state["current_step"] = "nmcc_calculated"

    return state


# ── Node: generate_document ──


def generate_document_node(state: PipelineState) -> PipelineState:
    """Generate the .docx justification document."""
    session_id = state.get("session_id", "unknown")

    calc_data = {
        "weighted_average_price": state.get("weighted_average_price", 0),
        "median_price": state.get("median_price", 0),
        "coefficient_of_variation": state.get("coefficient_of_variation", 0),
        "is_homogeneous": state.get("is_homogeneous", True),
        "nmck_per_unit": state.get("nmck_per_unit", 0),
        "total_nmck": state.get("total_nmck", 0),
        "price_range_min": state.get("price_range_min", 0),
        "price_range_max": state.get("price_range_max", 0),
        "num_prices_used": len(state.get("user_approved_prices", [])),
    }

    doc_path = generate_nmck_document(
        output_dir=settings.output_dir,
        session_id=session_id,
        target_name=state.get("target_cte_name", ""),
        analogs=state.get("user_approved_analogs", []),
        prices=state.get("user_approved_prices", []),
        outliers=state.get("outlier_prices", []),
        calculation=calc_data,
        justification=state.get("justification", []),
        quantity=state.get("quantity", 1.0),
        region=state.get("region_filter"),
        unit=state.get("unit_filter"),
    )

    state["document_path"] = doc_path
    state["current_step"] = "document_generated"
    return state


def route_after_search(state: PipelineState):
    """Route to price processing if CTE is known, otherwise wait for user approval."""
    if state.get("is_known_cte"):
        return "known"
    return "unknown"


# ── Graph Builder ──


def build_graph(checkpointer=None):
    """Build and compile the LangGraph state machine."""
    builder = StateGraph(PipelineState)

    builder.add_node("perform_search", perform_search)
    builder.add_node("wait_for_analogs", wait_for_analogs)
    builder.add_node("process_prices", process_prices)
    builder.add_node("calculate_nmcc", calculate_nmcc_node)
    builder.add_node("generate_document", generate_document_node)

    builder.add_edge(START, "perform_search")
    
    # Conditional transition: if known CTE, skip to price processing
    builder.add_conditional_edges(
        "perform_search",
        route_after_search,
        {
            "known": "process_prices",
            "unknown": "wait_for_analogs"
        }
    )
    
    builder.add_edge("wait_for_analogs", "process_prices")
    builder.add_edge("process_prices", "calculate_nmcc")
    builder.add_edge("calculate_nmcc", "generate_document")
    builder.add_edge("generate_document", END)

    if checkpointer is None:
        checkpointer = InMemorySaver()

    graph = builder.compile(checkpointer=checkpointer)

    logger.info("LangGraph pipeline compiled with %d nodes", 5)
    return graph
