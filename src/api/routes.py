"""FastAPI routes for the NMCK pipeline."""

import logging
import uuid

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse
from langgraph.types import Command

from src.models.schemas import (
    AnalogApprovalRequest,
    CalculationResponse,
    NMCKResult,
    PriceApprovalRequest,
    PricesResponse,
    RecalculateRequest,
    RegionPricesResponse,
    RegionPriceStat,
    SearchResponse,
    SessionStartRequest,
    SessionStatus,
    AnalogResult,
    PriceResult,
    CreatePurchaseRequest,
    CreatePurchaseResponse,
    PurchaseListResponse,
    PurchaseSummary,
    CalculationSummary,
    ItemSummary,
    PurchaseSummaryBoard,
    CTESearchResultItem,
    CTEPriceInfo,
    CTEPriceAnalytics,
)
from src.data_access.history_repo import HistoryRepository
from src.services.num_to_words_ru import number_to_words_ru

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api", tags=["NMCK Pipeline"])

# Global graph reference (set during lifespan)
_graph = None


def set_graph(graph):
    global _graph
    _graph = graph


def _get_config(session_id: str) -> dict:
    return {"configurable": {"thread_id": session_id}}


# ── Session management ──


@router.post("/session/start", response_model=SessionStatus)
async def start_session(request: SessionStartRequest):
    """
    Start a new NMCK calculation session.
    This triggers analog search and pauses at the first interrupt.
    """
    session_id = str(uuid.uuid4())[:8]
    config = _get_config(session_id)

    # Prepare initial state
    target_cte_name = request.cte_name
    target_category = request.category
    user_approved_analogs = []
    current_step = "init"

    is_known_cte = False

    # If cte_id is provided, bypass search and go straight to price processing
    if request.cte_id:
        import src.graph.nodes as nodes
        item = nodes._cte_repo.get_item_by_id(request.cte_id)
        if item:
            logger.info("Session %s: direct start with CTE ID %d", session_id, request.cte_id)
            is_known_cte = True
            user_approved_analogs = [{
                "cte_id": item["Идентификатор СТЕ"],
                "name": item["Наименование СТЕ"],
                "category": item.get("Категория", ""),
                "manufacturer": item.get("Производитель", ""),
                "attributes": item.get("_attributes", {}),
                "cosine_score": 1.0,  # Max score as it's an exact match
                "attribute_overlap": 1.0,
                "final_score": 1.0,
                "match_reason": "Выбрано пользователем напрямую",
            }]
            # Update names if they were generic/empty
            if not target_cte_name or target_cte_name == "Search":
                target_cte_name = item["Наименование СТЕ"]
            if not target_category:
                target_category = item.get("Категория")
            current_step = "analogs_approved"
        else:
            logger.warning("Session %s: CTE ID %d not found, falling back to search", session_id, request.cte_id)

    initial_state = {
        "session_id": session_id,
        "target_cte_name": target_cte_name,
        "target_category": target_category,
        "region_filter": request.region,
        "quantity": request.quantity,
        "inflation_coefficient": 1.0,
        "retrieved_analogs": [],
        "user_approved_analogs": user_approved_analogs,
        "raw_prices": [],
        "filtered_prices": [],
        "outlier_prices": [],
        "user_approved_prices": [],
        "justification": [],
        "current_step": current_step,
        "is_known_cte": is_known_cte,
        "error": None,
    }

    logger.info(
        "Starting session %s for '%s' (category=%s, region=%s, cte_id=%s)",
        session_id,
        target_cte_name,
        target_category,
        request.region,
        request.cte_id,
    )

    # Invoke graph — will run search_analogs OR skip to process_prices if user_approved_analogs is set
    result = _graph.invoke(initial_state, config)

    # Track in history if purchase_id provided
    if request.purchase_id:
        try:
            HistoryRepository.create_calculation(
                purchase_id=request.purchase_id,
                session_id=session_id,
                cte_name=target_cte_name,
                cte_category=target_category or "",
                cte_id=request.cte_id or 0,
            )
        except Exception as e:
            logger.warning("Failed to save calculation to history: %s", e)

    # Check for interrupt (analog approval)
    interrupts = result.get("__interrupt__", [])
    if interrupts:
        return SessionStatus(
            session_id=session_id,
            current_step="waiting_for_analog_approval",
        )

    return SessionStatus(
        session_id=session_id,
        current_step=result.get("current_step", "unknown"),
        error=result.get("error"),
    )


@router.get("/session/{session_id}/status", response_model=SessionStatus)
async def get_session_status(session_id: str):
    """Get current status of a session."""
    config = _get_config(session_id)
    try:
        state = _graph.get_state(config)
        values = state.values
        next_nodes = state.next

        step = values.get("current_step", "unknown")
        if next_nodes:
            # Handle user interaction steps
            node = next_nodes[0]
            if node == "wait_for_analogs":
                step = "waiting_for_analog_approval"
            elif node == "process_prices":
                step = "waiting_for_price_approval"
            else:
                step = f"waiting_at_{node}"

        return SessionStatus(
            session_id=session_id,
            current_step=step,
            error=values.get("error"),
        )
    except Exception as e:
        raise HTTPException(status_code=404, detail=f"Session not found: {e}")


# ── Analog Search & Approval ──


@router.get("/session/{session_id}/analogs", response_model=SearchResponse)
async def get_analogs(session_id: str):
    """Get found analogs for review."""
    config = _get_config(session_id)
    try:
        state = _graph.get_state(config)
        values = state.values
        analogs_raw = values.get("retrieved_analogs", [])

        from src.data_access.contract_repo import ContractRepository
        cte_ids = [a.get("cte_id", 0) for a in analogs_raw]
        cte_units_map = ContractRepository.get_units_by_cte(cte_ids)
        cte_stats_map = ContractRepository.get_analog_stats(cte_ids)
        all_units = set()

        analogs = []
        for a in analogs_raw:
            c_id = a.get("cte_id", 0)
            u_list = cte_units_map.get(c_id, [])
            stats = cte_stats_map.get(c_id, {})
            all_units.update(u_list)

            analogs.append(AnalogResult(
                cte_id=c_id,
                name=a.get("name", ""),
                category=a.get("category", ""),
                manufacturer=a.get("manufacturer", ""),
                attributes=a.get("attributes", {}),
                cosine_score=a.get("cosine_score", 0.0),
                attribute_overlap=a.get("attribute_overlap", 0.0),
                final_score=a.get("final_score", 0.0),
                match_reason=a.get("match_reason", ""),
                available_units=u_list,
                contract_count=stats.get("contract_count", 0),
                regions=stats.get("regions", []),
                unique_suppliers=stats.get("unique_suppliers", 0),
            ))

        # Sort by final_score descending
        analogs.sort(key=lambda a: a.final_score, reverse=True)

        return SearchResponse(
            session_id=session_id,
            analogs=analogs,
            total_found=len(analogs),
            available_units=sorted(list(all_units)),
        )
    except Exception as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.get("/cte/{cte_id}/check")
async def check_cte(cte_id: int):
    """Quick check if a CTE ID exists in the catalog."""
    import src.graph.nodes as nodes
    item = nodes._cte_repo.get_item_by_id(cte_id)
    if item:
        return {"exists": True, "name": item["Наименование СТЕ"]}
    return {"exists": False, "name": None}


@router.get("/cte/search")
async def search_cte(q: str = "", limit: int = 20):
    """Search CTE catalog by ID (exact) or by name (vector search)."""
    import src.graph.nodes as nodes
    repo = nodes._cte_repo
    if not repo:
        raise HTTPException(status_code=503, detail="CTE repo not initialized")

    query = q.strip()
    if not query:
        return {"results": []}

    results: list[CTESearchResultItem] = []

    # 1. Exact ID match
    try:
        cte_id = int(query)
        item = repo.get_item_by_id(cte_id)
        if item:
            results.append(_cte_to_search_item(item))
    except ValueError:
        pass

    # 2. Vector search for text queries (or if ID not found)
    if not results:
        embedder = nodes._embedder
        if not embedder:
            raise HTTPException(status_code=503, detail="Embedder not initialized")
        try:
            vector = embedder.encode_single(query)
            hits = repo.search(query_vector=vector, limit=limit, score_threshold=0.3)
            for h in hits:
                results.append(CTESearchResultItem(
                    id=h["cte_id"],
                    name=h.get("name", ""),
                    category=h.get("category", ""),
                    manufacturer=h.get("manufacturer", ""),
                    characteristics=[[k, v] for k, v in h.get("attributes", {}).items()],
                    cosine_score=h.get("cosine_score"),
                ))
        except Exception as e:
            logger.warning("Vector search failed: %s", e)

    # 3. Enrich with contract stats
    if results:
        from src.data_access.contract_repo import ContractRepository
        cte_ids = [r.id for r in results]
        stats_map = ContractRepository.get_analog_stats(cte_ids)
        for r in results:
            stats = stats_map.get(r.id, {})
            r.contract_count = stats.get("contract_count", 0)
            r.regions = stats.get("regions", [])
            r.unique_suppliers = stats.get("unique_suppliers", 0)

    return {"results": [r.model_dump() for r in results]}


def _cte_to_search_item(item: dict) -> CTESearchResultItem:
    attrs = item.get("_attributes", {})
    return CTESearchResultItem(
        id=item["Идентификатор СТЕ"],
        name=item["Наименование СТЕ"],
        category=item.get("Категория", ""),
        manufacturer=item.get("Производитель", ""),
        characteristics=[[k, v] for k, v in attrs.items()],
    )


@router.get("/cte/{cte_id}/prices", response_model=CTEPriceAnalytics)
async def get_cte_prices(cte_id: int, region: str | None = None, months: int = 12):
    """Price analytics for a specific CTE without session."""
    import src.graph.nodes as nodes
    from src.data_access.contract_repo import ContractRepository

    repo = nodes._cte_repo
    if not repo:
        raise HTTPException(status_code=503, detail="CTE repo not initialized")

    item = repo.get_item_by_id(cte_id)
    if not item:
        raise HTTPException(status_code=404, detail="CTE not found")

    cte_name = item["Наименование СТЕ"]

    # Get prices
    df = ContractRepository.get_prices_for_ctes([cte_id], region=region, months_back=months)
    prices: list[CTEPriceInfo] = []
    avg_price = 0.0
    median_price = 0.0
    min_price = 0.0
    max_price = 0.0

    if len(df) > 0:
        for row in df.iter_rows(named=True):
            date_val = row.get("Дата заключения контракта", "")
            if hasattr(date_val, "isoformat"):
                date_val = date_val.isoformat()
            prices.append(CTEPriceInfo(
                date=str(date_val) if date_val else "",
                price=row.get("Цена за единицу", 0) or 0,
                quantity=row.get("Количество", 1) or 1,
                unit=row.get("Единица измерения", "") or "",
                region=row.get("Регион заказчика", "") or "",
                supplier_inn=row.get("ИНН поставщика", 0) or 0,
                contract_id=row.get("Идентификатор контракта", 0) or 0,
                procurement_method=row.get("Способ закупки", "") or "",
            ))

        price_vals = [p.price for p in prices if p.price > 0]
        if price_vals:
            avg_price = sum(price_vals) / len(price_vals)
            sorted_prices = sorted(price_vals)
            n = len(sorted_prices)
            median_price = (sorted_prices[n // 2] + sorted_prices[(n - 1) // 2]) / 2
            min_price = sorted_prices[0]
            max_price = sorted_prices[-1]

    # Region stats
    raw_region_stats = ContractRepository.get_region_price_stats([cte_id], months_back=months)
    region_stats = [RegionPriceStat(**s) for s in raw_region_stats]

    # Units
    units_map = ContractRepository.get_units_by_cte([cte_id])
    available_units = units_map.get(cte_id, [])

    return CTEPriceAnalytics(
        cte_id=cte_id,
        cte_name=cte_name,
        prices=prices,
        avg_price=avg_price,
        median_price=median_price,
        min_price=min_price,
        max_price=max_price,
        total_contracts=len(prices),
        region_stats=region_stats,
        available_units=available_units,
    )


@router.post("/session/{session_id}/analogs/approve", response_model=SessionStatus)
async def approve_analogs(session_id: str, request: AnalogApprovalRequest):
    """
    Approve analog selection and resume the pipeline.
    This will trigger price processing and pause at the next interrupt.
    """
    config = _get_config(session_id)

    resume_data = {
        "approved_analog_ids": request.approved_analog_ids,
        "manual_cte_ids": request.manual_cte_ids,
        "units": request.units,
        "manual_prices": [mp.model_dump() for mp in request.manual_prices] if request.manual_prices else [],
    }

    logger.info(
        "Session %s: approving %d analogs (+%d manual)",
        session_id,
        len(request.approved_analog_ids),
        len(request.manual_cte_ids),
    )

    result = _graph.invoke(Command(resume=resume_data), config)

    # Save decisions to history
    try:
        HistoryRepository.save_decisions(session_id, {
            "approved_analog_ids": request.approved_analog_ids,
            "manual_cte_ids": request.manual_cte_ids,
            "selected_units": request.units or [],
        })
        HistoryRepository.update_step(session_id, "analogs_approved")
    except Exception as e:
        logger.warning("Failed to save analog decisions to history: %s", e)

    interrupts = result.get("__interrupt__", [])
    if interrupts:
        return SessionStatus(
            session_id=session_id,
            current_step="waiting_for_price_approval",
        )

    return SessionStatus(
        session_id=session_id,
        current_step=result.get("current_step", "unknown"),
        error=result.get("error"),
    )


@router.post("/session/{session_id}/analogs/reapprove", response_model=SessionStatus)
async def reapprove_analogs(session_id: str, request: AnalogApprovalRequest):
    """
    Re-approve analog selection and force the pipeline to rerun price processing.
    """
    config = _get_config(session_id)
    try:
        state = _graph.get_state(config)
        values = state.values
        ranked = values.get("retrieved_analogs", [])
        
        approved_ids = request.approved_analog_ids
        manual_ids = request.manual_cte_ids
        
        approved = [a for a in ranked if a["cte_id"] in approved_ids]
        
        import src.graph.nodes as nodes
        
        for mid in manual_ids:
            item = nodes._cte_repo.get_item_by_id(mid)
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
                
        state_update = {
            "user_approved_analogs": approved,
            "raw_prices": [],
            "filtered_prices": [],
            "outlier_prices": [],
            "user_approved_prices": [],
            "current_step": "analogs_approved",
            "error": None,
            "unit_filter": request.units,
            "manual_prices_from_analogs": [mp.model_dump() for mp in request.manual_prices] if request.manual_prices else [],
        }
        
        logger.info(
            "Session %s: RE-approving %d analogs (+%d manual), rewinding to wait_for_analogs",
            session_id,
            len(approved_ids),
            len(manual_ids),
        )
        
        _graph.update_state(config, state_update, as_node="wait_for_analogs")
        result = _graph.invoke(None, config)
        
        interrupts = result.get("__interrupt__", [])
        if interrupts:
            return SessionStatus(
                session_id=session_id,
                current_step="waiting_for_price_approval",
            )
            
        return SessionStatus(
            session_id=session_id,
            current_step=result.get("current_step", "unknown"),
            error=result.get("error"),
        )
    except Exception as e:
        logger.error("Error in reapprove_analogs: %s", e)
        raise HTTPException(status_code=500, detail=str(e))

# ── Price Review & Approval ──


@router.get("/session/{session_id}/prices", response_model=PricesResponse)
async def get_prices(session_id: str):
    """Get filtered prices for review."""
    config = _get_config(session_id)
    try:
        state = _graph.get_state(config)
        values = state.values

        filtered = values.get("filtered_prices", [])
        outliers = values.get("outlier_prices", [])

        # If interrupted, state hasn't been committed yet; extract from interrupt payload
        raw_info = values.get("price_search_info")
        tasks = getattr(state, "tasks", [])
        if tasks and tasks[0].interrupts:
            interrupt_val = tasks[0].interrupts[0].value
            if isinstance(interrupt_val, dict) and interrupt_val.get("type") == "price_approval":
                if not filtered:
                    filtered = interrupt_val.get("filtered_prices", [])
                    outliers = interrupt_val.get("outlier_prices", [])
                if not raw_info:
                    raw_info = interrupt_val.get("search_info")

        def _to_price_result(p: dict, idx: int, is_outlier: bool = False) -> PriceResult:
            date_val = p.get("Дата заключения контракта", "")
            if hasattr(date_val, "isoformat"):
                date_val = date_val.isoformat()
            return PriceResult(
                index=idx,
                cte_id=p.get("Идентификатор СТЕ по контракту") or 0,
                cte_name=p.get("Наименование позиции СТЕ") or "",
                price=p.get("Цена за единицу") or 0,
                quantity=p.get("Количество") or 1,
                unit=p.get("Единица измерения") or "шт",
                region=p.get("Регион заказчика") or "",
                contract_date=str(date_val) if date_val is not None else "",
                contract_id=p.get("Идентификатор контракта") or 0,
                procurement_method=p.get("Способ закупки") or "",
                is_outlier=is_outlier,
                outlier_reason=p.get("_outlier_reason", None),
                time_weight=p.get("time_weight", 1.0),
            )

        from src.models.schemas import PriceSearchInfo
        search_info = PriceSearchInfo(**raw_info) if raw_info else None

        return PricesResponse(
            session_id=session_id,
            filtered_prices=[_to_price_result(p, i) for i, p in enumerate(filtered)],
            outlier_prices=[_to_price_result(p, i + len(filtered), True) for i, p in enumerate(outliers)],
            total_found=len(filtered) + len(outliers),
            search_info=search_info,
        )
    except Exception as e:
        logger.error("Error in get_prices for session %s: %s", session_id, e, exc_info=True)
        raise HTTPException(status_code=404, detail=str(e))


@router.get("/session/{session_id}/region-prices", response_model=RegionPricesResponse)
async def get_region_prices(session_id: str):
    """Get average prices aggregated by region for the heatmap."""
    config = _get_config(session_id)
    try:
        state = _graph.get_state(config)
        values = state.values

        approved = values.get("user_approved_analogs", [])
        if not approved:
            approved = values.get("retrieved_analogs", [])

        cte_ids = [a.get("cte_id", 0) for a in approved if a.get("cte_id")]
        if not cte_ids:
            return RegionPricesResponse(
                session_id=session_id, stats=[], overall_avg=0, overall_min=0, overall_max=0
            )

        from src.data_access.contract_repo import ContractRepository

        units = values.get("unit_filter")
        raw_stats = ContractRepository.get_region_price_stats(cte_ids, units=units)

        if not raw_stats:
            return RegionPricesResponse(
                session_id=session_id, stats=[], overall_avg=0, overall_min=0, overall_max=0
            )

        stats = [RegionPriceStat(**s) for s in raw_stats]
        avg_prices = [s.avg_price for s in stats]
        overall_avg = sum(avg_prices) / len(avg_prices)
        overall_min = min(avg_prices)
        overall_max = max(avg_prices)

        return RegionPricesResponse(
            session_id=session_id,
            stats=stats,
            overall_avg=overall_avg,
            overall_min=overall_min,
            overall_max=overall_max,
        )
    except Exception as e:
        logger.error("Error in get_region_prices for session %s: %s", session_id, e, exc_info=True)
        raise HTTPException(status_code=404, detail=str(e))


@router.post("/session/{session_id}/prices/approve", response_model=SessionStatus)
async def approve_prices(session_id: str, request: PriceApprovalRequest):
    """
    Approve price selection and resume the pipeline.
    This triggers NMCK calculation and document generation.
    """
    config = _get_config(session_id)

    resume_data = {
        "approved_price_indices": request.approved_price_indices,
        "manual_prices": [mp.model_dump() for mp in request.manual_prices],
    }

    logger.info(
        "Session %s: approving %d prices (+%d manual)",
        session_id,
        len(request.approved_price_indices),
        len(request.manual_prices),
    )

    result = _graph.invoke(Command(resume=resume_data), config)

    # Save decisions and complete calculation in history
    try:
        HistoryRepository.save_decisions(session_id, {
            "approved_price_indices": request.approved_price_indices,
        })
        step = result.get("current_step", "")
        if step == "document_generated":
            state = _graph.get_state(config)
            vals = state.values
            HistoryRepository.complete_calculation(session_id, {
                "nmck_per_unit": vals.get("nmck_per_unit"),
                "total_nmck": vals.get("total_nmck"),
                "coefficient_of_variation": vals.get("coefficient_of_variation"),
                "is_homogeneous": vals.get("is_homogeneous"),
                "median_price": vals.get("median_price"),
                "weighted_average_price": vals.get("weighted_average_price"),
                "price_range_min": vals.get("price_range_min"),
                "price_range_max": vals.get("price_range_max"),
                "num_prices_used": len(vals.get("user_approved_prices", [])),
                "document_path": vals.get("document_path"),
            })
        else:
            HistoryRepository.update_step(session_id, step)
    except Exception as e:
        logger.warning("Failed to save price decisions to history: %s", e)

    return SessionStatus(
        session_id=session_id,
        current_step=result.get("current_step", "document_generated"),
        error=result.get("error"),
    )


# ── Calculation & Document ──


@router.get("/session/{session_id}/calculation", response_model=CalculationResponse)
async def get_calculation(session_id: str):
    """Get NMCK calculation result with justification."""
    config = _get_config(session_id)
    try:
        state = _graph.get_state(config)
        values = state.values

        result = NMCKResult(
            weighted_average_price=values.get("weighted_average_price", 0),
            median_price=values.get("median_price", 0),
            coefficient_of_variation=values.get("coefficient_of_variation", 0),
            is_homogeneous=values.get("is_homogeneous", True),
            nmck_per_unit=values.get("nmck_per_unit", 0),
            total_nmck=values.get("total_nmck", 0),
            price_range_min=values.get("price_range_min", 0),
            price_range_max=values.get("price_range_max", 0),
            num_prices_used=len(values.get("user_approved_prices", [])),
            justification=values.get("justification", []),
        )

        return CalculationResponse(session_id=session_id, result=result)
    except Exception as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.get("/session/{session_id}/document")
async def get_document(session_id: str):
    """Download the generated .docx justification document."""
    config = _get_config(session_id)
    try:
        state = _graph.get_state(config)
        values = state.values
        doc_path = values.get("document_path")

        if not doc_path:
            raise HTTPException(
                status_code=400,
                detail="Document not yet generated. Complete the pipeline first.",
            )

        return FileResponse(
            path=doc_path,
            filename=f"nmck_justification_{session_id}.docx",
            media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        )
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.post("/session/{session_id}/recalculate", response_model=CalculationResponse)
async def recalculate(session_id: str, request: RecalculateRequest):
    """Recalculate NMCK with different parameters (without re-running search)."""
    config = _get_config(session_id)
    try:
        state = _graph.get_state(config)
        values = state.values

        approved_prices = values.get("user_approved_prices", [])
        if not approved_prices:
            raise HTTPException(status_code=400, detail="No approved prices found")

        import polars as pl
        from src.ml.stats import analyze_prices as _analyze
        from src.services.nmck_service import calculate_nmck as _calc

        df = pl.DataFrame(approved_prices)
        analysis = _analyze(df, price_col="Цена за единицу")
        quantity = request.quantity or values.get("quantity", 1.0)

        result = _calc(
            analysis=analysis,
            quantity=quantity,
            inflation_coefficient=request.inflation_coefficient,
        )

        nmck_result = NMCKResult(
            weighted_average_price=result.weighted_average_price,
            median_price=result.median_price,
            coefficient_of_variation=result.coefficient_of_variation,
            is_homogeneous=result.is_homogeneous,
            nmck_per_unit=result.nmck_per_unit,
            total_nmck=result.total_nmck,
            price_range_min=result.price_range_min,
            price_range_max=result.price_range_max,
            num_prices_used=result.num_prices_used,
            justification=result.justification or [],
        )

        return CalculationResponse(session_id=session_id, result=nmck_result)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ── History ──


def _purchase_to_model(p: dict) -> PurchaseSummary:
    calcs = [
        CalculationSummary(
            id=c["id"],
            session_id=c["session_id"],
            cte_name=c["cte_name"],
            cte_category=c.get("cte_category", ""),
            cte_id=c.get("cte_id", 0),
            status=c["status"],
            current_step=c.get("current_step", ""),
            nmck_per_unit=c.get("nmck_per_unit"),
            total_nmck=c.get("total_nmck"),
            coefficient_of_variation=c.get("coefficient_of_variation"),
            is_homogeneous=c.get("is_homogeneous"),
            num_prices_used=c.get("num_prices_used"),
            document_path=c.get("document_path"),
            approved_analog_ids=c.get("approved_analog_ids", []),
            selected_units=c.get("selected_units", []),
            created_at=c.get("created_at", ""),
            completed_at=c.get("completed_at"),
        )
        for c in p.get("calculations", [])
    ]
    return PurchaseSummary(
        id=p["id"],
        created_at=p.get("created_at", ""),
        region=p.get("region", ""),
        status=p.get("status", "in_progress"),
        total_nmck=p.get("total_nmck", 0),
        items_count=p.get("items_count", 0),
        completed_count=p.get("completed_count", 0),
        calculations=calcs,
    )


@router.post("/history", response_model=CreatePurchaseResponse)
async def create_purchase(request: CreatePurchaseRequest):
    """Create a new purchase record for tracking calculation history."""
    pid = HistoryRepository.create_purchase(
        region=request.region,
        items_count=len(request.items),
    )
    return CreatePurchaseResponse(purchase_id=pid)


@router.get("/history", response_model=PurchaseListResponse)
async def list_purchases(limit: int = 50, offset: int = 0, status: str | None = None):
    """List purchases with their calculations."""
    purchases, total = HistoryRepository.list_purchases(limit, offset, status)
    return PurchaseListResponse(
        purchases=[_purchase_to_model(p) for p in purchases],
        total=total,
    )


@router.get("/history/recent", response_model=PurchaseListResponse)
async def recent_purchases(limit: int = 3):
    """Get recent purchases for the create page."""
    purchases = HistoryRepository.get_recent(limit)
    return PurchaseListResponse(
        purchases=[_purchase_to_model(p) for p in purchases],
        total=len(purchases),
    )


@router.get("/history/{purchase_id}", response_model=PurchaseSummary)
async def get_purchase(purchase_id: int):
    """Get a single purchase with calculations."""
    p = HistoryRepository.get_purchase(purchase_id)
    if not p:
        raise HTTPException(status_code=404, detail="Purchase not found")
    return _purchase_to_model(p)


@router.delete("/history/{purchase_id}")
async def delete_purchase(purchase_id: int):
    """Delete a purchase and its calculations."""
    deleted = HistoryRepository.delete_purchase(purchase_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Purchase not found")
    return {"ok": True}


# ── Purchase Summary & Consolidated Document ──


@router.get("/purchase/{purchase_id}/summary", response_model=PurchaseSummaryBoard)
async def get_purchase_summary(purchase_id: int):
    """Aggregated summary board for a completed purchase."""
    p = HistoryRepository.get_purchase(purchase_id)
    if not p:
        raise HTTPException(status_code=404, detail="Purchase not found")

    calcs = p.get("calculations", [])
    completed = [c for c in calcs if c["status"] == "completed"]

    items: list[ItemSummary] = []
    for c in completed:
        # Get quantity/unit from LangGraph state
        qty = 1.0
        unit = None
        try:
            config = _get_config(c["session_id"])
            state = _graph.get_state(config)
            vals = state.values
            qty = vals.get("quantity", 1.0)
            unit_val = vals.get("unit_filter")
            if isinstance(unit_val, list) and unit_val:
                unit = unit_val[0]
            elif isinstance(unit_val, str):
                unit = unit_val
        except Exception:
            pass

        items.append(ItemSummary(
            session_id=c["session_id"],
            cte_name=c["cte_name"],
            quantity=qty,
            unit=unit,
            nmck_per_unit=c.get("nmck_per_unit") or 0,
            total_nmck=c.get("total_nmck") or 0,
            coefficient_of_variation=c.get("coefficient_of_variation") or 0,
            is_homogeneous=bool(c.get("is_homogeneous")),
            num_prices_used=c.get("num_prices_used") or 0,
            median_price=c.get("median_price") or 0,
            weighted_average_price=c.get("weighted_average_price") or 0,
        ))

    grand_total = sum(it.total_nmck for it in items)
    cvs = [it.coefficient_of_variation for it in items if it.coefficient_of_variation > 0]

    return PurchaseSummaryBoard(
        purchase_id=purchase_id,
        region=p.get("region", ""),
        items_count=p.get("items_count", 0),
        completed_count=len(completed),
        grand_total_nmck=grand_total,
        grand_total_nmck_words=number_to_words_ru(grand_total),
        items=items,
        any_non_homogeneous=any(not it.is_homogeneous for it in items),
        average_cv=sum(cvs) / len(cvs) if cvs else 0,
    )


@router.get("/purchase/{purchase_id}/consolidated-document")
async def get_consolidated_document(purchase_id: int):
    """Generate and return a single .docx covering all items in a purchase."""
    p = HistoryRepository.get_purchase(purchase_id)
    if not p:
        raise HTTPException(status_code=404, detail="Purchase not found")

    calcs = [c for c in p.get("calculations", []) if c["status"] == "completed"]
    if not calcs:
        raise HTTPException(status_code=400, detail="No completed calculations")

    # Collect full state for each item from LangGraph
    doc_items = []
    for c in calcs:
        config = _get_config(c["session_id"])
        try:
            state = _graph.get_state(config)
            vals = state.values
        except Exception as e:
            raise HTTPException(
                status_code=500,
                detail=f"Cannot retrieve state for session {c['session_id']}: {e}",
            )

        unit_val = vals.get("unit_filter")
        unit = None
        if isinstance(unit_val, list) and unit_val:
            unit = unit_val[0]
        elif isinstance(unit_val, str):
            unit = unit_val

        doc_items.append({
            "target_name": vals.get("target_cte_name", c["cte_name"]),
            "analogs": vals.get("user_approved_analogs", []),
            "prices": vals.get("user_approved_prices", []),
            "outliers": vals.get("outlier_prices", []),
            "calculation": {
                "weighted_average_price": vals.get("weighted_average_price", 0),
                "median_price": vals.get("median_price", 0),
                "coefficient_of_variation": vals.get("coefficient_of_variation", 0),
                "is_homogeneous": vals.get("is_homogeneous", True),
                "nmck_per_unit": vals.get("nmck_per_unit", 0),
                "total_nmck": vals.get("total_nmck", 0),
            },
            "quantity": vals.get("quantity", 1.0),
            "unit": unit,
            "justification": vals.get("justification", []),
        })

    from src.services.document_service import generate_consolidated_document
    from src.config import settings

    doc_path = generate_consolidated_document(
        output_dir=settings.output_dir,
        purchase_id=purchase_id,
        region=p.get("region"),
        items=doc_items,
    )

    return FileResponse(
        path=doc_path,
        filename=f"nmck_consolidated_{purchase_id}.docx",
        media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    )
