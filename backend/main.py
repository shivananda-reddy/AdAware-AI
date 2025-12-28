
import sys
import os

# Allow running directly from backend/ folder or root
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from backend.core.config import API_TITLE, validate_config
from backend.core.logging_config import setup_logging
from backend.api import router as api_router
from backend.services import storage

LOG = setup_logging()

app = FastAPI(title=API_TITLE)

@app.on_event("startup")
def on_startup():
    LOG.info("=" * 60)
    LOG.info("AdAware AI Backend Starting...")
    LOG.info("=" * 60)
    
    validate_config()
    storage.init_db()
    
    # Pre-load ML models to avoid first-request delays
    LOG.info("Pre-loading ML models...")
    
    # Pre-load NLP models
    try:
        from backend.services import nlp
        nlp._get_sentiment_pipe()
        nlp._get_ner_pipe()
    except Exception as e:
        LOG.warning(f"NLP model pre-load had issues: {e}")
    
    # Pre-load CLIP model
    try:
        from backend.services import fusion
        fusion.get_clip_model()
        fusion.get_clip_processor()
    except Exception as e:
        LOG.warning(f"CLIP model pre-load had issues: {e}")
    
    LOG.info("=" * 60)
    LOG.info("AdAware AI Backend Ready!")
    LOG.info("=" * 60)

# Allow requests from local web dashboard (dev only)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:8501", "http://127.0.0.1:8501", "*"],  # '*' only for dev
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(api_router)

if __name__ == "__main__":
    import uvicorn
    # Use the string import path for reload to work
    uvicorn.run("backend.main:app", host="127.0.0.1", port=8000, reload=True)
