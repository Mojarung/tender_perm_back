"""LangGraph nodes for the NMCK pipeline with human-in-the-loop interrupts."""

import logging
import uuid
from typing import Any

import polars as pl
from langgraph.graph import END, START, StateGraph
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.types import Command, interrupt

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
    target_name = state["target_cte_name"]
    ranked = state.get("retrieved_analogs", [])

    # Interrupt for user to review analogs
    user_decision = interrupt({
        "type": "analog_approval",
        "message": f"Найдено {len(ranked)} аналогов для '{target_name}'. Проверьте и одобрите.",
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
    state["unit_filter"] = user_decision.get("unit")
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
    region = state.get("region_filter")

    if not approved_analogs:
        state["error"] = "Нет одобренных аналогов"
        state["current_step"] = "error"
        return state

    cte_ids = [a["cte_id"] for a in approved_analogs]
    logger.info("Fetching prices for %d CTE IDs", len(cte_ids))

    unit = state.get("unit_filter")
    
    # Get prices from contracts
    prices_df = ContractRepository.get_prices_for_ctes(
        cte_ids=cte_ids,
        region=region,
        months_back=settings.price_months_back,
        unit=unit,
    )

    if prices_df.height == 0:
        logger.warning("No prices found, trying without region filter")
        prices_df = ContractRepository.get_prices_for_ctes(
            cte_ids=cte_ids,
            region=None,
            months_back=settings.price_months_back,
            unit=unit,
        )

    if prices_df.height == 0:
        logger.warning("Still no prices found, extending date range to 24 months")
        prices_df = ContractRepository.get_prices_for_ctes(
            cte_ids=cte_ids,
            region=None,
            months_back=24,
            unit=unit,
        )

    state["raw_prices"] = prices_df.to_dicts()

    # Add time weights
    prices_df = ContractRepository.add_time_weights(prices_df)

    # Run outlier detection
    analysis = analyze_prices(
        prices_df,
        price_col="Цена за единицу",
        max_cv=settings.max_coefficient_of_variation,
    )

    state["filtered_prices"] = analysis.valid_prices
    state["outlier_prices"] = analysis.outlier_prices
    state["current_step"] = "prices_filtered"

    # Interrupt for user to review prices
    user_decision = interrupt({
        "type": "price_approval",
        "message": f"Найдено {len(analysis.valid_prices)} цен ({len(analysis.outlier_prices)} выбросов исключено). CV={analysis.coefficient_of_variation:.1f}%",
        "filtered_prices": analysis.valid_prices,
        "outlier_prices": analysis.outlier_prices,
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
            "Регион заказчика": mp.get("region", ""),
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
        template_path=settings.template_path,
        output_dir=settings.output_dir,
        session_id=session_id,
        target_name=state.get("target_cte_name", ""),
        analogs=state.get("user_approved_analogs", []),
        prices=state.get("user_approved_prices", []),
        outliers=state.get("outlier_prices", []),
        calculation=calc_data,
        justification=state.get("justification", []),
    )

    state["document_path"] = doc_path
    state["current_step"] = "document_generated"
    return state


# ── Graph Builder ──


def build_graph():
    """Build and compile the LangGraph state machine."""
    builder = StateGraph(PipelineState)

    builder.add_node("perform_search", perform_search)
    builder.add_node("wait_for_analogs", wait_for_analogs)
    builder.add_node("process_prices", process_prices)
    builder.add_node("calculate_nmcc", calculate_nmcc_node)
    builder.add_node("generate_document", generate_document_node)

    builder.add_edge(START, "perform_search")
    builder.add_edge("perform_search", "wait_for_analogs")
    builder.add_edge("wait_for_analogs", "process_prices")
    builder.add_edge("process_prices", "calculate_nmcc")
    builder.add_edge("calculate_nmcc", "generate_document")
    builder.add_edge("generate_document", END)

    checkpointer = InMemorySaver()
    graph = builder.compile(checkpointer=checkpointer)

    logger.info("LangGraph pipeline compiled with %d nodes", 4)
    return graph
