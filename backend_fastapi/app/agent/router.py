"""Query router for intent resolution, guardrails, and handler dispatch."""

import re
import logging
import time
from concurrent.futures import ThreadPoolExecutor
from typing import Dict, Optional, Any

from app.core.state import state
from app.agent.planner import ClaudePlanner
from app.core.metrics import metrics_logger
from app.agent.handlers import AgentHandlers
from app.agent.models import AgentResponse

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)


class ApplianceAgent:
    """Stateful router that resolves and routes user requests."""
    
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

    def check_scope(self, user_query: str, resolved: Dict) -> tuple[bool, Optional[str]]:
        """
        Two-tier scope checking:
        1. Check LLM-extracted appliance intent (primary)
        2. Fast keyword check for obvious out-of-scope (secondary)
        
        Returns: (in_scope: bool, reason: Optional[str])
        """
        
        query_lower = user_query.lower()
        
        appliance = resolved.get("appliance")
        
        if appliance:
            appliance_lower = appliance.lower()
            if appliance_lower in self.VALID_APPLIANCES:
                logger.info(f"[SCOPE] In scope via LLM intent: {appliance}")
                return True, None
            else:
                logger.info(f"[SCOPE] Out of scope via LLM intent: {appliance}")
                return False, f"I can only help with refrigerator and dishwasher parts. For {appliance} issues, please contact a specialist."
        
        if resolved.get("part_id") or resolved.get("model_id"):
            logger.info("[SCOPE] In scope via part/model ID")
            return True, None
        
        for keyword in self.OUT_OF_SCOPE_KEYWORDS:
            pattern = r'\b' + re.escape(keyword) + r'\b'
            if re.search(pattern, query_lower):
                logger.info(f"[SCOPE] Out of scope (keyword): {keyword}")
                return False, f"I specialize in refrigerator and dishwasher parts only. For {keyword} repairs, please consult a qualified appliance technician or the manufacturer."
        
        if resolved.get("symptom"):
            logger.info("[SCOPE] Assumed in scope (symptom without appliance)")
            return True, None
        
        return True, None
    
    def check_topic_drift(self, session_entities: Dict, resolved: Dict) -> bool:
        """
        Detect if user switched appliances mid-conversation
        Returns: True if topic drift detected (should reset session)
        """
        
        session_appliance = session_entities.get("appliance", "").lower()
        current_appliance = resolved.get("appliance")  
        if current_appliance:
            current_appliance = current_appliance.lower()
        
        if session_appliance and current_appliance and session_appliance != current_appliance:
            logger.warning(f"[TOPIC_DRIFT] {session_appliance} → {current_appliance}")
            return True
        
        return False

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
            if self._is_low_signal_query(user_query):
                logger.info("[LOW_SIGNAL] Returning clarification prompt")
                response = AgentResponse(
                    type="clarification_needed",
                    confidence=0.2,
                    requires_clarification=True,
                    message="I can help with refrigerator or dishwasher parts. Share a part number, model number, or symptom.",
                    clarification_questions=[
                        "Do you have a part number (starts with PS)?",
                        "What model number are you working with?",
                        "What issue are you seeing?"
                    ]
                )
                latency = time.time() - start_time
                metrics_logger.log_query(
                    query=user_query,
                    response_type=response.type,
                    confidence=response.confidence,
                    latency=latency,
                    route="low_signal",
                    intent=None,
                    entities={"part_id": None, "model_id": None}
                )
                return response

            if self._is_obvious_non_domain_query(user_query):
                logger.info("[NON_DOMAIN] Returning scope clarification without planner call")
                response = AgentResponse(
                    type="clarification_needed",
                    confidence=0.2,
                    requires_clarification=True,
                    message="I specialize in refrigerator and dishwasher parts support. Share a part number, model number, or appliance symptom and I can help.",
                    clarification_questions=[
                        "Do you have a part number (starts with PS)?",
                        "What appliance model number are you working with?",
                        "What refrigerator or dishwasher issue are you seeing?"
                    ]
                )
                latency = time.time() - start_time
                metrics_logger.log_query(
                    query=user_query,
                    response_type=response.type,
                    confidence=response.confidence,
                    latency=latency,
                    route="non_domain",
                    intent=None,
                    entities={"part_id": None, "model_id": None}
                )
                return response

            # Extract deterministic candidates
            candidates = self.extract_candidates(user_query)
            logger.info(f"[CANDIDATES] {candidates}")

            # Planner
            fast_followup = self._is_followup_symptom_query(user_query, session_entities)
            planning_input = None
            if not fast_followup:
                planning_input = self._build_planning_input(
                    user_query,
                    conversation_summary,
                    session_entities
                )

            with ThreadPoolExecutor(max_workers=3) as executor:
                part_future = executor.submit(self._prefetch_part, candidates.get("part_id"))
                model_future = executor.submit(self._prefetch_model, candidates.get("model_id"))

                if fast_followup:
                    plan = self._build_followup_symptom_plan(session_entities)
                    logger.info(f"[PLANNER] Fast follow-up path: {plan}")
                else:
                    planner_future = executor.submit(self.planner.plan, planning_input)
                    plan = planner_future.result()
                    logger.info(f"[PLANNER] {plan}")

                prefetched = {
                    "part_data": part_future.result(),
                    "model_info": model_future.result()
                }
                logger.info(
                    "[PREFETCH] part_hit=%s, model_hit=%s",
                    bool(prefetched["part_data"]),
                    bool(prefetched["model_info"].get("exists"))
                )

            # Validate and resolve entities
            resolved = self.validate_and_resolve(
                plan=plan,
                candidates=candidates,
                session_entities=session_entities,
                user_query=user_query,
                prefetched=prefetched
            )
            logger.info(f"[RESOLVED] {resolved}")
            
            # Guardrail: scope check
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
            
            # Guardrail: topic drift check
            if self.check_topic_drift(session_entities, resolved):
                logger.warning("[TOPIC_DRIFT] Resetting session")
                session_entities.clear()

            # Compute confidence score
            confidence = self.compute_confidence(resolved, plan, candidates, session_entities)
            logger.info(f"[CONFIDENCE] {confidence:.3f}")

            # Merge into session state
            self.merge_state(session_entities, resolved)
            logger.info(f"[STATE] {session_entities}")

            # Route based on confidence and state
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
        
        # Log metrics
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
        session_entities: Dict,
        user_query: str,
        prefetched: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """Validate extracted entities against database"""
        intent = plan.get("intent")
        prefetched = prefetched or {}

        resolved = {
            "intent": intent,
            "part_id": None,
            "model_id": None,
            "symptom": (plan.get("query") or plan.get("symptom")) if intent == "symptom_troubleshoot" else None,
            "appliance": plan.get("appliance"),
            "brand": plan.get("brand"),
            "part_id_valid": False,
            "model_id_valid": False
        }

        use_session_part = self._should_reuse_session_part(user_query, intent)
        use_session_model = self._should_reuse_session_model(user_query, intent)

        candidate_part = (
            candidates.get("part_id") or 
            plan.get("part_id") or 
            (session_entities.get("part_id") if use_session_part else None)
        )
        
        if candidate_part:
            pid = candidate_part.upper()
            prefetch_part = prefetched.get("part_data")
            if prefetch_part and prefetch_part.get("part_id") == pid:
                resolved["part_id"] = pid
                resolved["part_id_valid"] = True
                logger.info(f"[VALID_PART] {pid} (prefetched)")
            elif pid.startswith("PS") and pid in state["part_id_map"]:
                resolved["part_id"] = pid
                resolved["part_id_valid"] = True
                logger.info(f"[VALID_PART] {pid}")

        candidate_model = (
            candidates.get("model_id") or 
            plan.get("model_id") or 
            (session_entities.get("model_id") if use_session_model else None)
        )
        
        if candidate_model:
            mid = candidate_model.upper()
            resolved["model_id"] = mid

            prefetch_model = prefetched.get("model_info", {})
            if prefetch_model.get("model_id") == mid:
                if prefetch_model.get("exists"):
                    resolved["model_id_valid"] = True
                    logger.info(f"[VALID_MODEL] {mid} (prefetched)")
                else:
                    logger.info(f"[UNVALIDATED_MODEL] {mid} (not in database)")
            elif mid in state["model_id_to_parts_map"]:
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
            # Partial credit for unvalidated model
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
        
        # Priority: valid part_id with install/lookup intent
        if part_id and resolved.get("part_id_valid") and intent in ["part_lookup", "install_help"]:
            logger.info(f"[ROUTER] Priority route: {intent} for part {part_id}")
            return self.handlers.handle_part_lookup(part_id, confidence, user_query)
        
        if confidence < self.confidence_threshold:
            if symptom and not model_id:
                return self.handlers.handle_model_required(
                    detected_info={
                        "symptom": symptom,
                        "appliance": resolved.get("appliance"),
                        "brand": resolved.get("brand")
                    },
                    confidence=max(confidence, 0.55)
                )

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
        
        if part_id and intent in ["part_lookup", "install_help"]:
            return self.handlers.handle_part_lookup(part_id, confidence, user_query)
        
        if intent == "compatibility_check" and part_id and model_id:
            if not resolved.get("model_id_valid"):
                return self.handlers.handle_compatibility_unvalidated(
                    part_id=part_id,
                    model_id=model_id,
                    resolved=resolved,
                    session_entities=session_entities,
                    confidence=confidence,
                    user_query=user_query
                )
            return self.handlers.handle_compatibility(
                model_id=model_id,
                part_id=part_id,
                confidence=confidence,
                user_query=user_query
            )
        
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
            
            if resolved.get("model_id_valid"):
                return self.handlers.handle_symptom_troubleshoot(
                    symptom=symptom,
                    model_id=model_id,
                    session_entities=session_entities,
                    confidence=confidence,
                    user_query=user_query
                )
            else:
                return self.handlers.handle_symptom_troubleshoot_unvalidated(
                    symptom=symptom,
                    model_id=model_id,
                    session_entities=session_entities,
                    confidence=max(confidence, 0.60),
                    user_query=user_query
                )
        
        if model_id and not symptom:
            prior_symptom = session_entities.get("last_symptom")
            if prior_symptom:
                logger.info("[ROUTER] Model-only follow-up with prior symptom context")
                if resolved.get("model_id_valid"):
                    return self.handlers.handle_symptom_troubleshoot(
                        symptom=prior_symptom,
                        model_id=model_id,
                        session_entities=session_entities,
                        confidence=confidence,
                        user_query=user_query
                    )
                return self.handlers.handle_symptom_troubleshoot_unvalidated(
                    symptom=prior_symptom,
                    model_id=model_id,
                    session_entities=session_entities,
                    confidence=max(confidence, 0.60),
                    user_query=user_query
                )
            return self.handlers.handle_issue_required(
                model_id=model_id,
                confidence=confidence
            )
        
        return self.handlers.handle_clarification_needed(
            resolved=resolved,
            session_entities=session_entities,
            confidence=confidence
        )
    def _build_planning_input(self, user_query, conversation_summary, session_entities):
        """Build context for LLM planner"""
        context_parts = []
        if conversation_summary:
            context_parts.append(f"Conversation summary:\n{conversation_summary}")
        if session_entities:
            context_parts.append(f"\nSession context:\n{session_entities}")
        context_parts.append(f"\nUser message:\n{user_query}")
        return "\n".join(context_parts)

    def _is_followup_symptom_query(self, user_query: str, session_entities: Dict) -> bool:
        """Detect fast-path follow-up asks for existing symptom context."""
        if not session_entities.get("last_symptom"):
            return False

        query = user_query.lower()
        followup_markers = [
            "step by step",
            "walk me through",
            "diagnostic checks",
            "next steps",
            "what should i check",
            "how do i fix"
        ]
        return any(marker in query for marker in followup_markers)

    def _build_followup_symptom_plan(self, session_entities: Dict) -> Dict[str, Any]:
        """Build deterministic plan for follow-up symptom turns."""
        return {
            "intent": "symptom_troubleshoot",
            "confidence": 0.9,
            "part_id": None,
            "model_id": session_entities.get("model_id"),
            "symptom": session_entities.get("last_symptom"),
            "appliance": session_entities.get("appliance"),
            "brand": session_entities.get("brand"),
            "query": session_entities.get("last_symptom"),
        }

    def _prefetch_part(self, part_id: Optional[str]) -> Optional[Dict[str, Any]]:
        """Prefetch part data from in-memory state for regex-detected part IDs."""
        if not part_id:
            return None
        return state["part_id_map"].get(part_id.upper())

    def _prefetch_model(self, model_id: Optional[str]) -> Dict[str, Any]:
        """Prefetch model existence info from in-memory state for regex-detected model IDs."""
        if not model_id:
            return {"model_id": None, "exists": False}

        mid = model_id.upper()
        return {
            "model_id": mid,
            "exists": mid in state["model_id_to_parts_map"]
        }

    def _should_reuse_session_part(self, user_query: str, intent: Optional[str]) -> bool:
        """Reuse part from session only on explicit references."""
        if intent == "symptom_troubleshoot":
            return False

        query = user_query.lower()
        patterns = [
            r"\bthis part\b",
            r"\bthat part\b",
            r"\bit\b",
            r"\bthe part\b",
            r"\bsame part\b"
        ]
        return any(re.search(p, query) for p in patterns)

    def _should_reuse_session_model(self, user_query: str, intent: Optional[str]) -> bool:
        """Reuse model from session only on explicit references."""
        if intent == "symptom_troubleshoot":
            return False

        query = user_query.lower()
        patterns = [
            r"\bthis model\b",
            r"\bthat model\b",
            r"\bmy model\b",
            r"\bsame model\b",
            r"\bwith it\b"
        ]
        return any(re.search(p, query) for p in patterns)

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

    def _is_low_signal_query(self, user_query: str) -> bool:
        """Detect low-information or nonsensical queries before expensive processing."""
        if not user_query or not user_query.strip():
            return True

        clean = user_query.strip()
        alnum_chars = re.findall(r"[A-Za-z0-9]", clean)
        if len(alnum_chars) < 3:
            return True

        # If there are no words and no IDs, it's likely noise.
        has_word = bool(re.search(r"[A-Za-z]{2,}", clean))
        has_id_like = bool(re.search(r"\b(PS\d{5,}|[A-Z0-9]{6,15})\b", clean.upper()))
        return not has_word and not has_id_like

    def _is_obvious_non_domain_query(self, user_query: str) -> bool:
        """Detect obvious general-knowledge questions that are outside product support scope."""
        if not user_query:
            return False

        clean = user_query.strip().lower()
        if not clean:
            return False

        # If the user gave a part/model ID, treat as in-domain and continue normal routing.
        if re.search(r"\bPS\d{5,}\b", user_query.upper()):
            return False
        for token in re.findall(r"\b[A-Z0-9]{6,15}\b", user_query.upper()):
            if not token.startswith("PS") and any(ch.isdigit() for ch in token):
                return False

        appliance_terms = {
            "refrigerator", "fridge", "dishwasher", "ice maker",
            "water filter", "door bin", "leak", "drain", "noisy", "not working", "install"
        }
        if any(term in clean for term in appliance_terms):
            return False

        general_markers = {
            "what is today's date", "what is the date", "today's date",
            "capital of", "who is", "what time", "weather", "tell me about"
        }
        return any(marker in clean for marker in general_markers)
