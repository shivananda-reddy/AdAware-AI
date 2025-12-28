
from typing import List, Optional
import os
from fastapi import APIRouter, HTTPException, Query, Response
from backend.schemas import HoverPayload, AnalysisResult, FeedbackPayload, StatsResponse, ExportRequest
from backend.services.pipeline import run_analysis_pipeline
from backend.services import storage
from backend.services.pdf_export import generate_pdf_bytes

router = APIRouter()

@router.get("/health")
async def health_check():
    """Health check endpoint for extension/dashboard."""
    openai_configured = bool(os.getenv("OPENAI_API_KEY"))
    return {
        "status": "ok",
        "openai_configured": openai_configured
    }

@router.post("/analyze_hover", response_model=AnalysisResult)
async def analyze_hover(payload: HoverPayload):
    """
    Main analysis endpoint.
    Delegates to pipeline service.
    """
    return await run_analysis_pipeline(payload)

@router.get("/api/v1/history", response_model=List[AnalysisResult])
async def get_history(limit: int = 50):
    return storage.get_history(limit)

@router.get("/api/v1/history/{id}", response_model=AnalysisResult)
async def get_history_detail(id: str):
    res = storage.get_analysis_by_id(id)
    if not res:
        raise HTTPException(status_code=404, detail="Analysis not found")
    return res

@router.post("/api/v1/feedback")
async def submit_feedback(payload: FeedbackPayload):
    storage.save_feedback(payload.analysis_id, payload.user_label.value, payload.is_correct, payload.notes)
    return {"status": "success"}

@router.get("/api/v1/stats", response_model=StatsResponse)
async def get_stats():
    # Helper to map storage result to pydantic model needed?
    # StatsResponse expects dict structure compatible with storage.get_stats()
    return storage.get_stats()

@router.post("/api/v1/export_pdf")
async def export_pdf(payload: ExportRequest):
    """Generate a PDF report. If analysis is not provided, run pipeline first."""
    # Prepare analysis dict
    analysis_dict = None
    try:
        if payload.analysis:
            analysis_dict = payload.analysis.model_dump()
        else:
            # Build HoverPayload from ExportRequest and run pipeline
            hover = HoverPayload(
                image_base64=payload.image_base64,
                image_url=payload.image_url,
                page_url=payload.page_url,
                ad_text=payload.ad_text,
                use_llm=payload.use_llm,
            )
            analysis_model = await run_analysis_pipeline(hover)
            analysis_dict = analysis_model.model_dump()
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Failed to prepare analysis: {e}")

    pdf_bytes = generate_pdf_bytes(
        analysis=analysis_dict,
        image_url=payload.image_url or analysis_dict.get("image_url"),
        image_base64=payload.image_base64 or analysis_dict.get("image_base64"),
    )
    if not pdf_bytes:
        # ReportLab not installed or another failure in PDF generation
        raise HTTPException(status_code=501, detail="PDF generation unavailable. Install reportlab.")

    # File name using label and timestamp if available
    label = analysis_dict.get("final_label", "report")
    ts = analysis_dict.get("timestamp", "")
    filename = f"adaware_report_{label}_{ts}.pdf".replace(" ", "_")

    headers = {
        "Content-Disposition": f"attachment; filename={filename}"
    }
    return Response(content=pdf_bytes, media_type="application/pdf", headers=headers)
