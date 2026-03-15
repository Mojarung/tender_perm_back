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
)

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

    initial_state = {
        "session_id": session_id,
        "target_cte_name": request.cte_name,
        "target_category": request.category,
        "region_filter": request.region,
        "quantity": request.quantity,
        "inflation_coefficient": 1.0,
        "retrieved_analogs": [],
        "user_approved_analogs": [],
        "raw_prices": [],
        "filtered_prices": [],
        "outlier_prices": [],
        "user_approved_prices": [],
        "justification": [],
        "current_step": "init",
        "error": None,
    }

    logger.info(
        "Starting session %s for '%s' (category=%s, region=%s)",
        session_id,
        request.cte_name,
        request.category,
        request.region,
    )

    # Invoke graph — will run search_analogs and hit the interrupt
    result = _graph.invoke(initial_state, config)

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

        # Sort: analogs with recent contracts first, then by score
        analogs.sort(key=lambda a: (a.contract_count > 0, a.contract_count, a.final_score), reverse=True)

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
async def search_cte(q: str = "", limit: int = 10):
    """Search CTE catalog by ID (exact) or by name/category (substring + vector)."""
    import src.graph.nodes as nodes
    repo = nodes._cte_repo
    if not repo:
        raise HTTPException(status_code=503, detail="CTE repo not initialized")

    query = q.strip()
    if not query:
        return {"results": []}

    # Exact ID match only
    try:
        cte_id = int(query)
        item = repo.get_item_by_id(cte_id)
        if item:
            return {"results": [_cte_to_dict(item)]}
    except ValueError:
        pass

    return {"results": []}


def _cte_to_dict(item: dict) -> dict:
    attrs = item.get("_attributes", {})
    return {
        "id": item["Идентификатор СТЕ"],
        "name": item["Наименование СТЕ"],
        "category": item.get("Категория", ""),
        "manufacturer": item.get("Производитель", ""),
        "characteristics": [[k, v] for k, v in attrs.items()],
    }


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
