import uuid
from pathlib import Path
from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse

from src.api.schemas import (
    CreateSessionRequest, CreateSessionResponse,
    SessionResponse,
    ApproveAnalogsRequest, ApproveAnalogsResponse,
    ApprovePricesRequest, ApprovePricesResponse,
    ApproveCalculationRequest, ApproveCalculationResponse,
    GoBackRequest, CTESearchResult,
)
from src.pipeline.state import PipelineState, PriceRecord
from src.pipeline.nodes.search_analogs import search_analogs
from src.pipeline.nodes.fetch_prices import fetch_prices
from src.pipeline.nodes.filter_outliers import filter_outliers
from src.pipeline.nodes.calculate_nmcc import calculate_nmcc
from src.pipeline.nodes.generate_doc import generate_document
from src.dependencies import get_cte_repo, get_contract_repo, get_qdrant_repo, get_embedding_service

router = APIRouter(prefix="/api")

sessions: dict[str, PipelineState] = {}


def _get_session(session_id: str) -> PipelineState:
    if session_id not in sessions:
        raise HTTPException(404, "Session not found")
    return sessions[session_id]


@router.post("/sessions", response_model=CreateSessionResponse)
def create_session(req: CreateSessionRequest):
    session_id = str(uuid.uuid4())

    analogs = search_analogs(
        target_cte_id=req.target_cte_id,
        target_cte_name=req.target_cte_name,
        cte_repo=get_cte_repo(),
        contract_repo=get_contract_repo(),
        qdrant_repo=get_qdrant_repo(),
        embedding_service=get_embedding_service(),
    )

    state = PipelineState(
        session_id=session_id,
        target_cte_id=req.target_cte_id,
        target_cte_name=req.target_cte_name,
        target_quantity=req.target_quantity,
        target_unit=req.target_unit,
        target_region=req.target_region,
        found_analogs=analogs,
        current_step="wait_analog_approval",
    )
    sessions[session_id] = state

    return CreateSessionResponse(
        session_id=session_id,
        current_step=state.current_step,
        found_analogs=analogs,
    )


@router.get("/sessions/{session_id}", response_model=SessionResponse)
def get_session(session_id: str):
    state = _get_session(session_id)
    return SessionResponse(**state.model_dump())


@router.post("/sessions/{session_id}/approve-analogs", response_model=ApproveAnalogsResponse)
def approve_analogs(session_id: str, req: ApproveAnalogsRequest):
    state = _get_session(session_id)

    state.user_approved_analogs = [
        a for a in state.found_analogs if a.cte_id in req.approved_cte_ids
    ]

    prices, region_fallback = fetch_prices(
        approved_cte_ids=req.approved_cte_ids,
        target_region=state.target_region,
        target_unit=state.target_unit,
        contract_repo=get_contract_repo(),
    )
    state.all_prices = prices
    state.region_fallback_used = region_fallback

    valid, outliers, justification = filter_outliers(prices)
    state.valid_prices = valid
    state.outlier_prices = outliers
    state.outlier_justification = justification
    state.current_step = "wait_price_approval"

    return ApproveAnalogsResponse(
        current_step=state.current_step,
        all_prices=state.all_prices,
        valid_prices=state.valid_prices,
        outlier_prices=state.outlier_prices,
        outlier_justification=state.outlier_justification,
        region_fallback_used=state.region_fallback_used,
    )


@router.post("/sessions/{session_id}/approve-prices", response_model=ApprovePricesResponse)
def approve_prices(session_id: str, req: ApprovePricesRequest):
    state = _get_session(session_id)

    approved = [state.valid_prices[i] for i in req.approved_price_indices if i < len(state.valid_prices)]

    for mp in req.manual_prices:
        approved.append(PriceRecord(
            cte_id=0,
            cte_name=mp.source_description,
            price_original=mp.price,
            price_adjusted=mp.price,
            kd=1.0,
            date="",
            region=state.target_region or "",
            contract_id=0,
            vat_rate="",
            quantity=0,
            unit=state.target_unit,
            source="manual",
        ))

    state.user_approved_prices = approved
    adjusted_prices = [p.price_adjusted for p in approved]
    result = calculate_nmcc(adjusted_prices, state.target_quantity)
    state.nmcc_result = result
    state.current_step = "wait_calc_approval"

    return ApprovePricesResponse(
        current_step=state.current_step,
        nmcc_result=result,
    )


@router.post("/sessions/{session_id}/approve-calculation", response_model=ApproveCalculationResponse)
def approve_calculation(session_id: str, req: ApproveCalculationRequest):
    state = _get_session(session_id)

    if not req.approved:
        state.current_step = "wait_price_approval"
        return ApproveCalculationResponse(current_step=state.current_step)

    template_path = Path("src/document/template.docx")
    output_dir = Path("output")

    if template_path.exists():
        doc_path = generate_document(state, template_path, output_dir)
        state.document_path = doc_path
    state.current_step = "done"

    return ApproveCalculationResponse(
        current_step=state.current_step,
        document_path=state.document_path,
    )


@router.post("/sessions/{session_id}/go-back")
def go_back(session_id: str, req: GoBackRequest):
    state = _get_session(session_id)
    if req.target_step == "analogs":
        state.current_step = "wait_analog_approval"
    elif req.target_step == "prices":
        state.current_step = "wait_price_approval"
    return {"current_step": state.current_step}


@router.get("/sessions/{session_id}/document")
def download_document(session_id: str):
    state = _get_session(session_id)
    if not state.document_path:
        raise HTTPException(404, "Document not generated yet")
    return FileResponse(state.document_path, filename=f"nmcc_{session_id}.docx")


@router.get("/cte/search", response_model=list[CTESearchResult])
def search_cte(q: str, limit: int = 10):
    results = get_cte_repo().search_by_name(q, limit=limit)
    return [
        CTESearchResult(
            cte_id=r["cte_id"],
            name=r["name"],
            category=r["category"],
            manufacturer=r["manufacturer"],
        )
        for r in results
    ]


@router.get("/regions", response_model=list[str])
def get_regions():
    return get_contract_repo().get_regions()
