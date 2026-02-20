from pydantic import BaseModel, Field
from typing import Dict, List, Optional, Any, Literal


# ============================================================================
# STRUCTURED RESPONSE MODELS
# ============================================================================

class PartInfo(BaseModel):
    """Structured part information"""
    part_id: str
    title: str
    brand: str
    price: str
    description: Optional[str] = None
    installation_difficulty: Optional[str] = None
    installation_time: Optional[str] = None
    video_url: Optional[str] = None
    url: str
    symptoms: List[str] = Field(default_factory=list)
    rating: Optional[float] = None
    relevance_score: Optional[float] = None
    ranking_factors: Optional[Dict[str, float]] = None


class AgentResponse(BaseModel):
    """Unified response structure for all agent interactions"""
    type: Literal[
        "part_lookup",
        "compatibility", 
        "symptom_solution",
        "model_required",
        "issue_required",
        "clarification_needed"
    ]
    confidence: float = Field(ge=0.0, le=1.0)
    requires_clarification: bool
    
    # Response content
    message: Optional[str] = None
    explanation: Optional[str] = None
    
    # Part-specific data
    part: Optional[PartInfo] = None
    recommended_parts: List[PartInfo] = Field(default_factory=list)
    alternative_parts: List[PartInfo] = Field(default_factory=list)
    
    # Compatibility data
    model_id: Optional[str] = None
    compatible: Optional[bool] = None
    
    # Symptom troubleshooting
    symptom: Optional[str] = None
    diagnostic_steps: List[str] = Field(default_factory=list)
    
    # Clarification
    clarification_questions: List[str] = Field(default_factory=list)
    clarification_type: Optional[str] = None
    detected_info: Optional[Dict[str, Any]] = None
    helpful_tips: List[str] = Field(default_factory=list)
    
    # Related information
    related_parts: List[PartInfo] = Field(default_factory=list)
    
    class Config:
        json_encoders = {
            float: lambda v: round(v, 3)
        }
        protected_namespaces = ()