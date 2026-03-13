"""API router for NMCC calculation and report generation."""

from fastapi import APIRouter
from fastapi.responses import StreamingResponse

from src.schemas.api import (
    NMCKCalculateRequest,
    NMCKCalculateResponse,
    NMCKReportRequest,
)
from src.services.nmck import calculate_nmck
from src.services.report import generate_nmck_report

router = APIRouter(prefix="/api/v1/nmck", tags=["NMCC"])


@router.post("/calculate", response_model=NMCKCalculateResponse)
async def nmck_calculate(request: NMCKCalculateRequest) -> NMCKCalculateResponse:
    """
    Calculate NMCC (НМЦК):

    1. Detect outliers via IsolationForest (sklearn) on ML Worker
    2. Compute mean, std, variation coefficient via Polars
    3. Flag manual review if variation coefficient > 33%
    """
    return await calculate_nmck(
        selected_prices=request.selected_prices,
        target_ste_id=request.target_ste_id,
        target_region=request.target_region,
    )


@router.post("/report")
async def nmck_report(request: NMCKReportRequest) -> StreamingResponse:
    """
    Generate a .docx report document for the NMCC calculation.
    """
    buffer = generate_nmck_report(request)

    return StreamingResponse(
        buffer,
        media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        headers={
            "Content-Disposition": f"attachment; filename=nmck_report_{request.target_ste_id}.docx"
        },
    )
