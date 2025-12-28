
# Configuration constants for AdAware AI Backend
import os
import logging

logger = logging.getLogger("adaware.config")

# Server settings
API_TITLE = "AdAware AI - Debug API"
HOST = "127.0.0.1"
PORT = 8000

# OpenAI Settings
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")
OPENAI_MODEL = os.getenv("AD_AWARE_LLM_MODEL", "gpt-4o")
OPENAI_VISION_MODEL = os.getenv("AD_AWARE_VISION_MODEL", "gpt-4o")

# Feature flags
ENABLE_LLM = bool(OPENAI_API_KEY)
ENABLE_VISION = bool(OPENAI_API_KEY)

# Offline / Hugging Face Settings
ADAWARE_HF_OFFLINE = bool(os.getenv("ADAWARE_HF_OFFLINE", "").lower() in ("true", "1", "yes"))
ADAWARE_DISABLE_NLP = bool(os.getenv("ADAWARE_DISABLE_NLP", "").lower() in ("true", "1", "yes"))
ADAWARE_DISABLE_CLIP = bool(os.getenv("ADAWARE_DISABLE_CLIP", "").lower() in ("true", "1", "yes"))

# Auto-configure HF environment if offline mode requested
if ADAWARE_HF_OFFLINE:
    os.environ["HF_HUB_OFFLINE"] = "1"
    os.environ["TRANSFORMERS_OFFLINE"] = "1"


def validate_config():
    """Validate configuration on startup and log warnings."""
    if not OPENAI_API_KEY:
        logger.warning("OPENAI_API_KEY not set. LLM and Vision features will be disabled.")
    else:
        logger.info("OpenAI configured with model: %s", OPENAI_MODEL)
    
    if ADAWARE_HF_OFFLINE:
        logger.info("Running in Offline Mode for Hugging Face models.")
    if ADAWARE_DISABLE_NLP:
        logger.info("NLP features disabled by config.")
    if ADAWARE_DISABLE_CLIP:
        logger.info("CLIP features disabled by config.")
        
    return True
