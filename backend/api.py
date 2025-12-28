
from fastapi import APIRouter
from backend.schemas import HoverPayload
from backend.services.pipeline import run_analysis_pipeline

router = APIRouter()

@router.post("/analyze_hover")
async def analyze_hover(payload: HoverPayload):
    """
    Main analysis endpoint.
    Delegates to pipeline service.
    Returns:
      {
        "cached": bool,
        "result": { ... full report ... }
      }
    """
    return await run_analysis_pipeline(payload)
