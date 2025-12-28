from __future__ import annotations
from typing import List, Optional, Literal, Dict, Any
from pydantic import BaseModel, Field
from enum import Enum
from datetime import datetime
import uuid

# --- Enums for Taxonomy ---

class RiskLabel(str, Enum):
    SAFE = "safe"
    LOW_RISK = "low-risk"
    MODERATE_RISK = "moderate-risk"
    HIGH_RISK = "high-risk"
    SCAM_SUSPECTED = "scam-suspected"
    UNKNOWN = "unknown"

class RiskSubcategory(str, Enum):
    HEALTH_CLAIM = "health-claim"
    FINANCIAL_PROMISE = "financial-promise"
    BEFORE_AFTER = "before-after"
    CRYPTO = "crypto"
    GAMBLING = "gambling"
    URGENCY = "urgency"
    UNREALISTIC_DISCOUNT = "unrealistic-discount"
    FAKE_ENDORSEMENT = "fake-endorsement"
    OTHER = "other"

# --- Request Models ---

class HoverPayload(BaseModel):
    image_base64: Optional[str] = None
    image_url: Optional[str] = None
    page_url: Optional[str] = None
    ad_text: Optional[str] = None
    use_llm: bool = False
    sensitivity: float = 0.5  # 0.0 to 1.0

class AnalyzeRequest(HoverPayload):
    """Alias for HoverPayload for clarity in new API docs"""
    pass

# --- Component Models ---

class RuleTrigger(BaseModel):
    rule_id: str
    description: str
    severity: str  # low, medium, high

class SourceReputation(BaseModel):
    domain: Optional[str] = None
    https: bool = False
    domain_age_days: Optional[int] = None
    flags: List[str] = []

# --- Response Models ---

class EvidenceSpan(BaseModel):
    kind: str = "risky_phrase"  # "risky_phrase", "emotional_trigger", "policy_rule", "other"
    text: str
    start: int = -1
    end: int = -1
    reason: str = ""
    category: Optional[str] = None

class Evidence(BaseModel):
    risky_phrases: List[EvidenceSpan] = Field(default_factory=list)
    emotional_triggers: List[str] = Field(default_factory=list)

class AnalysisResult(BaseModel):
    request_id: str
    timestamp: str 
    source: str = "extension" 
    
    final_label: RiskLabel
    risk_score: float = 0.0
    subcategories: List[RiskSubcategory] = []
    
    brand_entities: List[str] = []
    sentiment: str = "neutral"
    emotions: List[str] = []
    
    evidence: Evidence = Field(default_factory=Evidence)
    rule_triggers: List[RuleTrigger] = []
    source_reputation: SourceReputation = Field(default_factory=SourceReputation)
    
    ocr_text: Optional[str] = None
    llm_used: bool = False
    cache_hit: bool = False
    
    error: Optional[Dict[str, Any]] = None
    
    # Backward compatibility with old classify/explain fields (merged view)
    explanation_text: Optional[str] = None 
    confidence: float = 0.0

class StatsResponse(BaseModel):
    total_analyses: int
    label_counts: Dict[str, int]
    confusion_matrix: Dict[str, int] # simple correct_count vs total_feedback

class FeedbackPayload(BaseModel):
    analysis_id: str
    user_label: RiskLabel
    is_correct: bool
    notes: Optional[str] = None
