
from typing import List, Optional
from fastapi import APIRouter, HTTPException, Query
from backend.schemas import HoverPayload, AnalysisResult, FeedbackPayload, StatsResponse
from backend.services.pipeline import run_analysis_pipeline
from backend.services import storage

router = APIRouter()

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
