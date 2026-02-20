"""
Complete Agent Router with LLM-Generated Responses, Guardrails, and Graceful Degradation

Architecture:
1. Extract candidates (regex)
2. Plan with Claude (intent + entities)
3. Validate against state
4. Check scope & topic drift (guardrails)
5. Compute confidence score
6. Retrieve relevant context (JSON + Vector Search)
7. Generate response using Claude with ALL context
8. Return structured JSON response

Key Principles:
- NO HARDCODED RESPONSES - Let LLM use the rich data we collected
- GRACEFUL DEGRADATION - Provide helpful answers even with unvalidated data
- SCOPE GUARDRAILS - Only refrigerator and dishwasher
"""

import re
import json
import logging
import time
from typing import Dict, List, Optional, Any, Literal
from pydantic import BaseModel, Field

from app.tools.part_tools import lookup_part, check_compatibility, vector_search
from app.core.state import state
from app.agent.planner import ClaudePlanner
from app.core.metrics import metrics_logger
from app.agent.handlers import AgentHandlers
from app.agent.models import AgentResponse, PartInfo

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)


# ============================================================================
# MAIN AGENT CLASS
# ============================================================================

class ApplianceAgent:
    """
    Intelligent routing agent with LLM-generated responses and guardrails
    """
    
    # Scope guardrails
    VALID_APPLIANCES = {"refrigerator", "dishwasher", "fridge"}
    OUT_OF_SCOPE_KEYWORDS = {
        "oven", "stove", "range", "microwave", "dryer", 
        "washing machine", "clothes washer", "clothes dryer", "furnace", "hvac",
        "water heater", "garbage disposal", "air conditioner", "ac"
    }

    def __init__(self):
        self.planner = ClaudePlanner()
        self.handlers = AgentHandlers()
        self.confidence_threshold = 0.55

    # ========================================================================
    # GUARDRAILS: SCOPE CHECKING
    # ========================================================================
    
    def check_scope(self, user_query: str, resolved: Dict) -> tuple[bool, Optional[str]]:
        """
        Two-tier scope checking:
        1. Check LLM-extracted appliance intent (primary)
        2. Fast keyword check for obvious out-of-scope (secondary)
        
        Returns: (in_scope: bool, reason: Optional[str])
        """
        
        query_lower = user_query.lower()
        
        # TIER 1 (HIGHEST PRIORITY): Check LLM-extracted appliance intent
        # This is the most accurate because it understands sentence meaning
        appliance = resolved.get("appliance")
        
        if appliance:
            # If LLM identified an appliance, use that
            appliance_lower = appliance.lower()
            if appliance_lower in self.VALID_APPLIANCES:
                logger.info(f"[SCOPE] In scope via LLM intent: {appliance}")
                return True, None  # ✓ Valid appliance
            else:
                logger.info(f"[SCOPE] Out of scope via LLM intent: {appliance}")
                return False, f"I can only help with refrigerator and dishwasher parts. For {appliance} issues, please contact a specialist."
        
        # TIER 2: If LLM didn't identify appliance, check for part_id or model_id
        # These indicate the user is definitely asking about parts
        if resolved.get("part_id") or resolved.get("model_id"):
            logger.info("[SCOPE] In scope via part/model ID")
            return True, None
        
        # TIER 3: Fast keyword check ONLY as a pre-filter
        # Only reject if keyword found AND no appliance intent
        for keyword in self.OUT_OF_SCOPE_KEYWORDS:
            pattern = r'\b' + re.escape(keyword) + r'\b'
            if re.search(pattern, query_lower):
                logger.info(f"[SCOPE] Out of scope (keyword): {keyword}")
                return False, f"I specialize in refrigerator and dishwasher parts only. For {keyword} repairs, please consult a qualified appliance technician or the manufacturer."
        
        # TIER 4: If symptom but no clear appliance, assume in-scope
        # (Could be fridge/dishwasher, user just hasn't specified yet)
        if resolved.get("symptom"):
            logger.info("[SCOPE] Assumed in scope (symptom without appliance)")
            return True, None
        
        # Default: In scope (let the conversation continue)
        return True, None
    
    def check_topic_drift(self, session_entities: Dict, resolved: Dict) -> bool:
        """
        Detect if user switched appliances mid-conversation
        Returns: True if topic drift detected (should reset session)
        """
        
        session_appliance = session_entities.get("appliance", "").lower()
        current_appliance = resolved.get("appliance")  
        if current_appliance:
            current_appliance = current_appliance.lower() # ✓ Normalize for comparison
        
        # If both specified and different → topic drift
        if session_appliance and current_appliance and session_appliance != current_appliance:
            logger.warning(f"[TOPIC_DRIFT] {session_appliance} → {current_appliance}")
            return True
        
        return False

    # ========================================================================
    # MAIN ENTRY POINT
    # ========================================================================

    def handle_query(
        self,
        user_query: str,
        conversation_id: str,
        conversation_summary: str,
        session_entities: dict
    ) -> AgentResponse:
        """Main orchestrator with guardrails and confidence tracking"""
        
        start_time = time.time()
        error_msg = None
        
        logger.info(f"[REQUEST] {user_query}")
        logger.info(f"[SESSION] {session_entities}")

        try:
            # 1️⃣ Extract deterministic candidates
            candidates = self.extract_candidates(user_query)
            logger.info(f"[CANDIDATES] {candidates}")

            # 2️⃣ Planner (LLM)
            planning_input = self._build_planning_input(
                user_query, 
                conversation_summary,
                session_entities
            )
            plan = self.planner.plan(planning_input)
            logger.info(f"[PLANNER] {plan}")

            # 3️⃣ Validate + Resolve entities
            resolved = self.validate_and_resolve(plan, candidates, session_entities)
            logger.info(f"[RESOLVED] {resolved}")
            
            # 🛡️ GUARDRAIL 1: Check scope
            in_scope, scope_message = self.check_scope(user_query, resolved)
            if not in_scope:
                logger.warning(f"[OUT_OF_SCOPE] {scope_message}")
                response = AgentResponse(
                    type="clarification_needed",
                    confidence=0.0,
                    requires_clarification=True,
                    message=scope_message,
                    clarification_questions=[
                        "Are you looking for refrigerator or dishwasher parts?",
                        "I specialize in these appliances only."
                    ]
                )
                
                # Log metrics
                latency = time.time() - start_time
                metrics_logger.log_query(
                    query=user_query,
                    response_type=response.type,
                    confidence=response.confidence,
                    latency=latency,
                    route="out_of_scope",
                    intent=resolved.get("intent"),
                    entities={"part_id": resolved.get("part_id"), "model_id": resolved.get("model_id")}
                )
                
                return response
            
            # 🛡️ GUARDRAIL 2: Check topic drift
            if self.check_topic_drift(session_entities, resolved):
                logger.warning("[TOPIC_DRIFT] Resetting session")
                session_entities.clear()

            # 4️⃣ Compute confidence score
            confidence = self.compute_confidence(resolved, plan, candidates, session_entities)
            logger.info(f"[CONFIDENCE] {confidence:.3f}")

            # 5️⃣ Merge into session state
            self.merge_state(session_entities, resolved)
            logger.info(f"[STATE] {session_entities}")

            # 6️⃣ Route based on confidence and state
            response = self.route(
                resolved=resolved,
                session_entities=session_entities,
                confidence=confidence,
                user_query=user_query
            )
            
            logger.info(f"[RESPONSE] type={response.type}, confidence={response.confidence}")
            
        except Exception as e:
            logger.error(f"[ERROR] {str(e)}", exc_info=True)
            error_msg = str(e)
            response = self._error_response(str(e))
        
        # 📊 Log metrics
        latency = time.time() - start_time
        metrics_logger.log_query(
            query=user_query,
            response_type=response.type,
            confidence=response.confidence,
            latency=latency,
            route=response.type,
            intent=plan.get("intent") if 'plan' in locals() else None,
            entities={
                "part_id": resolved.get("part_id") if 'resolved' in locals() else None,
                "model_id": resolved.get("model_id") if 'resolved' in locals() else None
            },
            error=error_msg
        )
        
        return response

    # ========================================================================
    # EXTRACTION & VALIDATION
    # ========================================================================

    def extract_candidates(self, text: str) -> Dict[str, Optional[str]]:
        """Extract part_id and model_id using regex patterns"""
        
        clean = text.strip().upper()

        part_match = re.search(r'\bPS\d{5,}\b', clean)
        model_match = re.search(r'\b[A-Z0-9]{6,15}\b', clean)
        
        part_id = None
        if part_match:
            part_id = part_match.group(0)
        
        model_id = None
        if model_match:
            candidate = model_match.group(0)
            if not candidate.startswith('PS') and not candidate.isalpha():
                model_id = candidate

        return {
            "part_id": part_id,
            "model_id": model_id
        }

    def validate_and_resolve(
        self, 
        plan: Dict, 
        candidates: Dict, 
        session_entities: Dict
    ) -> Dict[str, Any]:
        """Validate extracted entities against database"""
        
        resolved = {
            "intent": plan.get("intent"),
            "part_id": None,
            "model_id": None,
            "symptom": plan.get("query") or plan.get("symptom"),
            "appliance": plan.get("appliance"),
            "brand": plan.get("brand"),
            "part_id_valid": False,
            "model_id_valid": False
        }

        # Validate Part ID
        candidate_part = (
            candidates.get("part_id") or 
            plan.get("part_id") or 
            session_entities.get("part_id")
        )
        
        if candidate_part:
            pid = candidate_part.upper()
            if pid.startswith("PS") and pid in state["part_id_map"]:
                resolved["part_id"] = pid
                resolved["part_id_valid"] = True
                logger.info(f"[VALID_PART] {pid}")

        # Validate Model ID
        candidate_model = (
            candidates.get("model_id") or 
            plan.get("model_id") or 
            session_entities.get("model_id")
        )
        
        if candidate_model:
            mid = candidate_model.upper()
            resolved["model_id"] = mid
            
            if mid in state["model_id_to_parts_map"]:
                resolved["model_id_valid"] = True
                logger.info(f"[VALID_MODEL] {mid}")
            else:
                logger.info(f"[UNVALIDATED_MODEL] {mid} (not in database)")

        return resolved

    def compute_confidence(
        self, 
        resolved: Dict, 
        plan: Dict, 
        candidates: Dict,
        session_entities: Dict
    ) -> float:
        """Multi-factor confidence scoring with partial credit for unvalidated models"""
        
        score = 0.0
        
        # Regex matches
        if candidates.get("part_id") and resolved.get("part_id"):
            score += 0.1
        if candidates.get("model_id") and resolved.get("model_id"):
            score += 0.1
        
        # Database validation
        if resolved.get("part_id_valid"):
            score += 0.15
        
        if resolved.get("model_id_valid"):
            score += 0.15
        elif resolved.get("model_id"):
            # NEW: Partial credit for unvalidated model (half points)
            score += 0.08
        
        # LLM confidence
        llm_confidence = plan.get("confidence", 0.5)
        score += llm_confidence * 0.4
        
        # Session context
        if session_entities.get("model_id") and resolved.get("symptom"):
            score += 0.05
        if session_entities.get("last_symptom"):
            score += 0.05
        
        return min(score, 1.0)

    def merge_state(self, session_entities: Dict, resolved: Dict):
        """Update session with newly resolved entities"""
        
        if resolved.get("model_id"):
            session_entities["model_id"] = resolved["model_id"]
            session_entities["model_id_valid"] = resolved.get("model_id_valid", False)
        
        if resolved.get("part_id"):
            session_entities["part_id"] = resolved["part_id"]
        
        if resolved.get("symptom"):
            session_entities["last_symptom"] = resolved["symptom"]
        
        if resolved.get("appliance"):
            session_entities["appliance"] = resolved["appliance"]
        
        if resolved.get("brand"):
            session_entities["brand"] = resolved["brand"]

    # ========================================================================
    # ROUTING WITH GRACEFUL DEGRADATION
    # ========================================================================

    def route(
        self, 
        resolved: Dict, 
        session_entities: Dict,
        confidence: float,
        user_query: str
    ) -> AgentResponse:
        """Route to appropriate handler with graceful degradation"""
        
        intent = resolved.get("intent")
        part_id = resolved.get("part_id")
        model_id = resolved.get("model_id")
        symptom = resolved.get("symptom")
        
        # 🎯 PRIORITY: Valid part_id + install/lookup intent
        if part_id and resolved.get("part_id_valid") and intent in ["part_lookup", "install_help"]:
            logger.info(f"[ROUTER] Priority route: {intent} for part {part_id}")
            return self.handlers.handle_part_lookup(part_id, confidence, user_query)
        
        # === Low Confidence Fallback (but check for special cases first) ===
        if confidence < self.confidence_threshold:
            # SPECIAL CASE: Symptom + unvalidated model → try to help anyway
            if symptom and model_id and not resolved.get("model_id_valid"):
                logger.info(f"[ROUTER] Low confidence but have symptom + model → graceful degradation")
                return self.handlers.handle_symptom_troubleshoot_unvalidated(
                    symptom=symptom,
                    model_id=model_id,
                    session_entities=session_entities,
                    confidence=max(confidence, 0.60),
                    user_query=user_query
                )
            
            return self.handlers.handle_clarification_needed(
                resolved=resolved,
                session_entities=session_entities,
                confidence=confidence
            )
        
        # === Part Lookup / Installation ===
        if part_id and intent in ["part_lookup", "install_help"]:
            return self.handlers.handle_part_lookup(part_id, confidence, user_query)
        
        # === Compatibility Check ===
        if part_id and model_id:
            return self.handlers.handle_compatibility(
                model_id=model_id,
                part_id=part_id,
                confidence=confidence,
                user_query=user_query
            )
        
        # === Symptom Troubleshooting ===
        if symptom:
            if not model_id:
                return self.handlers.handle_model_required(
                    detected_info={
                        "symptom": symptom,
                        "appliance": resolved.get("appliance"),
                        "brand": resolved.get("brand")
                    },
                    confidence=confidence
                )
            
            # Check if model is validated
            if resolved.get("model_id_valid"):
                # Validated model → normal flow
                return self.handlers.handle_symptom_troubleshoot(
                    symptom=symptom,
                    model_id=model_id,
                    session_entities=session_entities,
                    confidence=confidence,
                    user_query=user_query
                )
            else:
                # Unvalidated model → graceful degradation
                return self.handlers.handle_symptom_troubleshoot_unvalidated(
                    symptom=symptom,
                    model_id=model_id,
                    session_entities=session_entities,
                    confidence=max(confidence, 0.60),
                    user_query=user_query
                )
        
        # === Model Only ===
        if model_id and not symptom:
            return self.handlers.handle_issue_required(
                model_id=model_id,
                confidence=confidence
            )
        
        # === Default Fallback ===
        return self.handlers.handle_clarification_needed(
            resolved=resolved,
            session_entities=session_entities,
            confidence=confidence
        )
    # ========================================================================
    # HELPER METHODS
    # ========================================================================

    def _build_planning_input(self, user_query, conversation_summary, session_entities):
        """Build context for LLM planner"""
        context_parts = []
        if conversation_summary:
            context_parts.append(f"Conversation summary:\n{conversation_summary}")
        if session_entities:
            context_parts.append(f"\nSession context:\n{session_entities}")
        context_parts.append(f"\nUser message:\n{user_query}")
        return "\n".join(context_parts)

    def _error_response(self, error_msg: str) -> AgentResponse:
        """Generate error response"""
        return AgentResponse(
            type="clarification_needed",
            confidence=0.0,
            requires_clarification=True,
            message="I encountered an issue processing your request. Could you try rephrasing?",
            clarification_questions=[
                "Do you have a part number or model number?",
                "What issue are you experiencing?"
            ]
        )