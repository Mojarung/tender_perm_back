from fastapi import APIRouter
from fastapi.responses import Response
from services.docx_generator import generate_nmcc_docx
from pydantic import BaseModel

class ReportRequest(BaseModel):
    nmcc_data: dict

router = APIRouter()

@router.post("/report")
async def create_report(payload: ReportRequest):
    docx_bytes = generate_nmcc_docx(payload.nmcc_data)
    
    headers = {
        'Content-Disposition': 'attachment; filename="Obosnovanie_NMCK.docx"'
    }
    
    return Response(content=docx_bytes, media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document", headers=headers)
