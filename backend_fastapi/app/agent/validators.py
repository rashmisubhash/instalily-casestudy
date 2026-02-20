"""
Response Validators and Guardrails
"""
import logging

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)
from typing import Dict, List, Optional, Any, Literal
from app.core.state import state
import re

class ResponseValidator:
    """Validates LLM responses before returning to users"""
    
    @staticmethod
    def validate_llm_response(response: Dict, context: Dict) -> bool:
        """General LLM response validation"""
        
        # Check 1: No hallucinated part IDs
        mentioned_parts = re.findall(r'PS\d{5,}', str(response))
        for pid in mentioned_parts:
            if pid not in state["part_id_map"]:
                logger.error(f"[VALIDATOR] ❌ Hallucinated part: {pid}")
                return False
        
        # Check 2: Reasonable length
        explanation = response.get("explanation", "")
        if explanation and len(explanation) < 20:
            logger.warning("[VALIDATOR] ⚠️ Too short")
            return False
        
        logger.info("[VALIDATOR] ✓ Valid")
        return True
    
    @staticmethod
    def validate_part_lookup_response(response, part_data) -> bool:
        """Validate part lookup specific response"""
        steps = response.get("installation_steps", [])
        return 3 <= len(steps) <= 8
    
    @staticmethod
    def validate_symptom_response(response, recommended_parts) -> bool:
        """Validate symptom diagnosis response"""
        if not recommended_parts:
            return True
        
        response_text = str(response).lower()
        return any(p["part_id"].lower() in response_text for p in recommended_parts)


class ScopeGuardrails:
    """Enforces scope boundaries"""
    
    VALID_APPLIANCES = {"refrigerator", "dishwasher", "fridge"}
    OUT_OF_SCOPE_KEYWORDS = {
        "oven", "stove", "range", "microwave", "dryer",
        "washing machine", "clothes washer", "clothes dryer", "furnace", "hvac",
        "water heater", "garbage disposal", "air conditioner", "ac"
    }
    
    @classmethod
    def check_scope(cls, user_query, resolved) -> tuple[bool, Optional[str]]:
        """Check if query is in scope"""
        
        # Priority 1: LLM intent
        appliance = resolved.get("appliance")
        if appliance:
            if appliance.lower() in cls.VALID_APPLIANCES:
                return True, None
            return False, f"I can only help with refrigerator and dishwasher parts"
        
        # Priority 2: Part/Model IDs
        if resolved.get("part_id") or resolved.get("model_id"):
            return True, None
        
        # Priority 3: Keyword check
        for keyword in cls.OUT_OF_SCOPE_KEYWORDS:
            if re.search(r'\b' + re.escape(keyword) + r'\b', user_query.lower()):
                return False, f"I specialize in refrigerator and dishwasher parts only"
        
        return True, None
    
    @staticmethod
    def check_topic_drift(session_entities, resolved) -> bool:
        """Detect appliance change mid-conversation"""
        session_app = session_entities.get("appliance", "").lower()
        current_app = resolved.get("appliance", "").lower()
        
        return bool(session_app and current_app and session_app != current_app)