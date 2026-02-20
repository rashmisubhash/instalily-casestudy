"""Response handlers for routed agent actions."""
from app.agent.validators import ResponseValidator
import logging
from typing import Dict, List
from app.core.state import state
import re
from app.tools.part_tools import check_compatibility, vector_search
from app.agent.planner import ClaudePlanner
from app.agent.models import AgentResponse, PartInfo

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

class AgentHandlers:
    """All response handler methods"""
    
    def __init__(self):
        self.validator = ResponseValidator()
        self.planner = ClaudePlanner()
    
    def handle_part_lookup(self, part_id, confidence, user_query):
        """Handle part installation queries"""
        
        part_data = state["part_id_map"].get(part_id)
        if not part_data:
            return self._part_not_found(part_id)
        
        # Generate with LLM
        llm_response = self._generate_part_lookup_response(part_data, user_query)
        
        # Validate response
        if not self.validator.validate_part_lookup_response(llm_response, part_data):
            llm_response = self._fallback_part_response(part_data)
        
        # Build response
        part = self._build_part_info(part_data)
        related = self._get_related_parts(part_id)
        
        return AgentResponse(
            type="part_lookup",
            confidence=min(confidence + 0.05, 0.99),
            requires_clarification=False,
            part=part,
            explanation=llm_response.get("explanation"),
            diagnostic_steps=llm_response.get("installation_steps"),
            helpful_tips=llm_response.get("tips"),
            related_parts=related
        )
    
    def handle_compatibility(
        self, 
        model_id: str, 
        part_id: str, 
        confidence: float,
        user_query: str
    ) -> AgentResponse:
        """Check compatibility with LLM-generated explanation"""
        
        logger.info(f"[HANDLER] compatibility: {part_id} + {model_id}")
        
        compatible = check_compatibility(model_id, part_id)
        part_data = state["part_id_map"].get(part_id)
        
        llm_response = self._generate_compatibility_response(
            part_data=part_data,
            model_id=model_id,
            compatible=compatible,
            user_query=user_query
        )
        
        part = self._build_part_info(part_data) if part_data else None
        
        if compatible:
            return AgentResponse(
                type="compatibility",
                confidence=min(confidence + 0.15, 0.99),
                requires_clarification=False,
                model_id=model_id,
                part_id=part_id,
                compatible=True,
                part=part,
                explanation=llm_response.get("explanation", ""),
                helpful_tips=llm_response.get("tips", [])
            )
        else:
            alternatives = self._find_compatible_alternatives(model_id, part_id, limit=3)
            
            return AgentResponse(
                type="compatibility",
                confidence=confidence,
                requires_clarification=False,
                model_id=model_id,
                part_id=part_id,
                compatible=False,
                part=part,
                alternative_parts=alternatives,
                explanation=llm_response.get("explanation", ""),
                helpful_tips=llm_response.get("tips", [])
            )

    def handle_compatibility_unvalidated(
        self,
        part_id: str,
        model_id: str,
        resolved: Dict,
        session_entities: Dict,
        confidence: float,
        user_query: str
    ) -> AgentResponse:
        """
        Handle compatibility check when model is not in database.
        Return likely alternatives with a clear non-verified disclaimer.
        """
        logger.info(f"[HANDLER] compatibility_unvalidated: {part_id} + {model_id}")

        part_data = state["part_id_map"].get(part_id)
        part = self._build_part_info(part_data) if part_data else None

        query = user_query
        if part_data:
            query = f"{part_data.get('title', '')} {part_data.get('description', '')} {part_data.get('symptoms', '')}".strip()

        try:
            candidates = vector_search(query, top_k=8)
        except Exception as e:
            logger.error(f"[VECTOR_SEARCH_ERROR] compatibility_unvalidated failed: {e}")
            candidates = []

        alternatives = []
        for candidate in candidates:
            candidate_pid = candidate.get("part_id")
            if not candidate_pid or candidate_pid == part_id:
                continue

            candidate_data = state["part_id_map"].get(candidate_pid, candidate)
            alternatives.append(self._build_part_info(candidate_data))

            if len(alternatives) >= 3:
                break

        clarification_questions = [
            "Could you double-check the model number (letters and numbers)?",
            "If you share a corrected model number, I can confirm exact compatibility."
        ]

        if not alternatives:
            clarification_questions.append("I can also help you find the model tag location if needed.")

        return AgentResponse(
            type="compatibility",
            confidence=min(confidence, 0.7),
            requires_clarification=True,
            model_id=model_id,
            part_id=part_id,
            compatible=None,
            part=part,
            alternative_parts=alternatives,
            explanation=(
                f"I couldn't verify model {model_id} in our compatibility database, so I can't confirm whether "
                f"{part_id} is compatible yet. I shared 2-3 likely alternatives to help you continue while you verify the model."
            ),
            clarification_questions=clarification_questions,
            helpful_tips=[
                "Model numbers are usually inside the door frame or on a side/back sticker.",
                "Use the exact model number to avoid ordering incompatible parts."
            ]
        )

    def handle_symptom_troubleshoot(self, symptom, model_id, session_entities, confidence, user_query):
        """Diagnose symptom with validated model"""
        
        query = self._build_search_query(symptom, session_entities)
        
        # Vector search with error handling
        try:
            raw_results = vector_search(query, top_k=20)
        except Exception as e:
            raw_results = self._get_popular_parts(session_entities.get("appliance"))
        
        compatible_parts = self._filter_by_model(raw_results, model_id)
        ranked_parts = self._rerank_results(compatible_parts, symptom, model_id)
        
        # Generate with LLM
        try:
            llm_response = self._generate_diagnostic_response(
                symptom=symptom,
                model_id=model_id,
                recommended_parts=ranked_parts[:3],
                user_query=user_query
            )
        except Exception as e:
            logger.error(f"[LLM_GENERATION_ERROR] Diagnostic generation failed: {e}")
            llm_response = self._fallback_diagnostic_response()
        
        # Validate
        if not self.validator.validate_symptom_response(llm_response, ranked_parts):
            logger.warning("[VALIDATOR] Symptom response validation failed")
        
        symptom_confidence = self._compute_symptom_confidence(ranked_parts, confidence)
        
        return AgentResponse(
            type="symptom_solution",
            confidence=symptom_confidence,
            requires_clarification=symptom_confidence < 0.70,
            symptom=symptom,
            model_id=model_id,
            recommended_parts=[self._build_part_info(p) for p in ranked_parts[:3]],
            explanation=llm_response.get("explanation", ""),
            diagnostic_steps=llm_response.get("diagnostic_steps", []),
            helpful_tips=llm_response.get("tips", [])
        )
    
    def handle_symptom_troubleshoot_unvalidated(
        self,
        symptom: str,
        model_id: str,
        session_entities: Dict,
        confidence: float,
        user_query: str
    ) -> AgentResponse:
        """
        Graceful degradation: Handle symptom when model is not in database
        Search without model filtering, provide general recommendations with warning
        """
        
        logger.info(f"[HANDLER] symptom_troubleshoot_unvalidated: '{symptom}' + model {model_id} (not in DB)")
        
        query = self._build_search_query(symptom, session_entities)
        
        try:
            raw_results = vector_search(query, top_k=10)
        except Exception as e:
            logger.error(f"[VECTOR_SEARCH_ERROR] Primary search failed: {e}")
            raw_results = []
        
        if not raw_results:
            appliance = session_entities.get("appliance", "refrigerator")
            logger.warning(f"[FALLBACK] No results for '{query}', trying broader search for {appliance}")
            
            try:
                broad_query = f"{appliance} common parts"
                raw_results = vector_search(broad_query, top_k=10)
            except Exception as e:
                logger.error(f"[VECTOR_SEARCH_ERROR] Fallback search failed: {e}")
                raw_results = []
        
        if not raw_results:
            logger.warning("[FALLBACK] Using popular parts as last resort")
            raw_results = self._get_popular_parts(session_entities.get("appliance", "refrigerator"))
        
        if not raw_results:
            return AgentResponse(
                type="clarification_needed",
                confidence=confidence,
                requires_clarification=True,
                message=f"I couldn't find parts for '{symptom}' in our database.",
                clarification_questions=[
                    "Could you describe the problem in more detail?",
                    "What specific behavior are you seeing?"
                ]
            )
        
        # Re-rank but without model filtering
        ranked_parts = self._rerank_results(raw_results, symptom, model_id)
        llm_response = self._generate_diagnostic_response(
            symptom=symptom,
            model_id=model_id,
            recommended_parts=ranked_parts[:3],
            user_query=user_query
        )
        
        # Build response with clear warning
        explanation = (
            f"Note: Model {model_id} is not in our database, so I cannot verify part compatibility.\n\n" +
            f"Here are parts that typically fix '{symptom}':\n\n" +
            llm_response.get("explanation", "")
        )
        
        return AgentResponse(
            type="symptom_solution",
            confidence=confidence,
            requires_clarification=False,
            symptom=symptom,
            model_id=model_id,
            recommended_parts=[self._build_part_info(p) for p in ranked_parts[:3]],
            explanation=explanation,
            diagnostic_steps=llm_response.get("diagnostic_steps", []),
            helpful_tips=[
                f"Verify part compatibility with model {model_id} before purchasing",
                "Check the product page for complete compatibility information",
                "Contact the manufacturer if unsure about compatibility"
            ] + llm_response.get("tips", [])
        )

    def _compute_symptom_confidence(self, ranked_parts: List[Dict], base_confidence: float) -> float:
        """Compute confidence for symptom troubleshooting"""
        if not ranked_parts:
            return 0.3
        
        top_score = ranked_parts[0].get("relevance_score", 0.5)
        
        if len(ranked_parts) >= 2:
            second_score = ranked_parts[1].get("relevance_score", 0.4)
            score_gap = top_score - second_score
        else:
            score_gap = 0.2
        
        confidence_boost = 0
        if top_score > 0.8:
            confidence_boost += 0.15
        elif top_score > 0.6:
            confidence_boost += 0.05
        
        if score_gap > 0.2:
            confidence_boost += 0.1
        
        return min(base_confidence + confidence_boost, 0.95)

    def handle_model_required(self, detected_info: Dict, confidence: float) -> AgentResponse:
        """Request model number"""
        
        logger.info(f"[HANDLER] model_required: {detected_info}")
        
        symptom = detected_info.get("symptom", "your issue")
        appliance = detected_info.get("appliance", "appliance")
        
        message = (
            f"I can help with {symptom}! To recommend the right parts, I need your {appliance} model number.\n\n"
            "Where to find it:\n"
            "- Inside the appliance door\n"
            "- On the back or side panel\n"
            "- Near the serial number plate"
        )
        
        return AgentResponse(
            type="model_required",
            confidence=confidence,
            requires_clarification=True,
            clarification_type="model_number",
            message=message,
            detected_info=detected_info,
            helpful_tips=[
                "Model numbers are usually 10-15 characters",
                "It may include both letters and numbers"
            ]
        )

    def handle_issue_required(self, model_id: str, confidence: float) -> AgentResponse:
        """Model provided but no symptom"""
        
        return AgentResponse(
            type="issue_required",
            confidence=confidence,
            requires_clarification=True,
            clarification_type="issue_description",
            model_id=model_id,
            message=f"Thanks! I've noted your model {model_id}. What issue are you experiencing?",
            clarification_questions=[
                "What's not working properly?",
                "What symptoms are you seeing?"
            ]
        )

    
    def handle_clarification_needed(
        self,
        resolved: Dict,
        session_entities: Dict,
        confidence: float
    ) -> AgentResponse:
        """Generic clarification"""
        
        logger.info(f"[HANDLER] clarification_needed: confidence={confidence}")
        
        questions = []
        message = "I want to help, but I need a bit more information:"
        
        if not resolved.get("part_id") and not resolved.get("symptom"):
            questions = [
                "Do you have a specific part number (starts with PS)?",
                "Or would you like help diagnosing an issue?",
                "What appliance are you working on?"
            ]
        elif resolved.get("symptom") and not resolved.get("model_id"):
            message = "To recommend the right parts, I need your appliance model number:"
            questions = [
                "What is your model number?",
                "It's usually on a sticker inside the appliance"
            ]
        else:
            questions = [
                "Could you rephrase your question?",
                "Are you looking for a specific part or troubleshooting help?"
            ]
        
        return AgentResponse(
            type="clarification_needed",
            confidence=confidence,
            requires_clarification=True,
            message=message,
            clarification_questions=questions,
            detected_info={
                "intent": resolved.get("intent"),
                "has_part": resolved.get("part_id") is not None,
                "has_model": resolved.get("model_id") is not None,
                "has_symptom": resolved.get("symptom") is not None
            }
        )

    def _generate_part_lookup_response(self, part_data: Dict, user_query: str) -> Dict:
        """Use Claude to generate helpful installation response"""
        
        prompt = f"""You are an expert appliance repair assistant. A customer asked: "{user_query}"

Part Information:
- Part ID: {part_data.get('part_id')}
- Title: {part_data.get('title')}
- Brand: {part_data.get('brand', 'Not specified')}
- Price: {part_data.get('price', 'Not specified')}
- Description: {part_data.get('description', 'Not available')}
- Installation Difficulty: {part_data.get('installation_difficulty', 'Not specified')}
- Installation Time: {part_data.get('installation_time', 'Not specified')}
- Video URL: {part_data.get('video_url', 'Not available')}

Generate a helpful response in JSON format:
{{
    "explanation": "2-3 sentences confirming the part and explaining what it is",
    "installation_steps": ["Step 1...", "Step 2...", "Step 3...", "Step 4...", "Step 5..."],
    "tips": ["Helpful tip 1", "Helpful tip 2"]
}}

Make the installation steps SPECIFIC to this part based on the description. If video is available, mention it as last step.
Keep it concise and practical for a homeowner."""

        try:
            response = self.planner._call_bedrock(prompt)
            parsed = self.planner._parse_response(response)
            return parsed
        except Exception as e:
            logger.error(f"[LLM_GENERATION_ERROR] {e}")
            return {
                "explanation": f"Part {part_data.get('part_id')} - {part_data.get('title')}.",
                "installation_steps": [
                    "Disconnect power to the appliance",
                    "Remove the old part",
                    "Install the new part according to instructions",
                    "Reconnect power and test"
                ],
                "tips": ["Refer to the product page for full details"]
            }

    
    def _generate_compatibility_response(
        self,
        part_data: Dict,
        model_id: str,
        compatible: bool,
        user_query: str
    ) -> Dict:
        """Generate compatibility explanation using Claude"""
        
        prompt = f"""Customer asked: "{user_query}"

Part: {part_data.get('part_id')} - {part_data.get('title')}
Model: {model_id}
Compatible: {compatible}

Generate JSON response:
{{
    "explanation": "Clear answer about compatibility (2-3 sentences)",
    "tips": ["Tip 1", "Tip 2"] 
}}

If compatible: Confirm it works and explain why it's a good fit.
If not compatible: Explain why not and what to look for in alternatives."""

        try:
            response = self.planner._call_bedrock(prompt)
            return self.planner._parse_response(response)
        except:
            return {
                "explanation": f"Part {part_data.get('part_id')} is {'compatible' if compatible else 'not compatible'} with model {model_id}.",
                "tips": []
            }

    def _generate_diagnostic_response(
        self,
        symptom: str,
        model_id: str,
        recommended_parts: List[Dict],
        user_query: str
    ) -> Dict:
        """Generate diagnostic response using Claude"""
        
        parts_context = "\n".join([
            f"- {p.get('part_id')}: {p.get('title')} (Score: {p.get('relevance_score', 'N/A')})\n  Description: {p.get('description', 'N/A')[:200]}"
            for p in recommended_parts
        ])
        
        prompt = f"""Customer asked: "{user_query}"

Symptom: {symptom}
Model: {model_id}

Top Recommended Parts:
{parts_context}

Generate JSON response:
{{
    "explanation": "2-3 sentences explaining the likely cause",
    "diagnostic_steps": ["Check 1...", "Check 2...", "Check 3...", "Check 4..."],
    "tips": ["Tip 1", "Tip 2"],
    "clarification_questions": ["Question 1?", "Question 2?"]
}}

Be specific based on the symptom and parts."""

        try:
            response = self.planner._call_bedrock(prompt)
            return self.planner._parse_response(response)
        except:
            return {
                "explanation": f"Based on '{symptom}', here are the most likely parts:",
                "diagnostic_steps": [
                    "Verify the issue is occurring consistently",
                    "Check for obvious signs of damage",
                    "Test the affected component"
                ],
                "tips": [],
                "clarification_questions": []
            }

    
    def _build_part_info(self, part_data: Dict) -> PartInfo:
        """Convert raw part data to structured PartInfo"""
        return PartInfo(
            part_id=part_data.get("part_id", ""),
            title=part_data.get("title", ""),
            brand=part_data.get("brand", ""),
            price=part_data.get("price", "N/A"),
            description=part_data.get("description"),
            installation_difficulty=part_data.get("installation_difficulty"),
            installation_time=part_data.get("installation_time"),
            video_url=part_data.get("video_url") if part_data.get("video_url") != "N/A" else None,
            url=part_data.get("url", ""),
            symptoms=part_data.get("symptoms", "").split("|") if part_data.get("symptoms") else [],
            rating=float(part_data.get("rating", 0)) if part_data.get("rating") and part_data.get("rating") != "N/A" else None
        )
    
    def _get_related_parts(self, part_id: str, limit: int = 3) -> List[PartInfo]:
        """Get related parts"""
        part_data = state["part_id_map"].get(part_id)
        if not part_data:
            return []
        
        related_parts_str = part_data.get("related_parts", "")
        if not related_parts_str or related_parts_str == "N/A":
            return []
        
        related = []
        parts_list = related_parts_str.split("|")
        
        for part_str in parts_list[:limit]:
            match = re.search(r'PS\d{5,}', part_str)
            if match:
                related_pid = match.group(0)
                related_data = state["part_id_map"].get(related_pid)
                if related_data:
                    related.append(self._build_part_info(related_data))
        
        return related

    def _filter_by_model(self, parts: List[Dict], model_id: str) -> List[Dict]:
        """Filter parts by model compatibility"""
        compatible_part_ids = set(state["model_id_to_parts_map"].get(model_id, []))
        
        if not compatible_part_ids:
            logger.warning(f"Model {model_id} not in database")
            return []
        
        filtered = [p for p in parts if p.get("part_id") in compatible_part_ids]
        logger.info(f"Filtered {len(parts)} → {len(filtered)} parts for model {model_id}")
        return filtered

    def _rerank_results(self, parts: List[Dict], symptom: str, model_id: str) -> List[Dict]:
        """Re-rank results using multi-factor scoring"""
        ranked = []
        symptom_keywords = set(symptom.lower().split())
        
        for part in parts:
            relevance_score = part.get("similarity_score", 0.5)
            
            part_symptoms = part.get("symptoms", "").lower()
            keyword_matches = sum(1 for kw in symptom_keywords if kw in part_symptoms)
            symptom_boost = min(keyword_matches * 0.1, 0.3)
            
            rating = part.get("rating", 3.0)
            if rating and rating != "N/A":
                try:
                    rating_val = float(rating)
                    popularity_boost = (rating_val - 3.0) * 0.05
                except:
                    popularity_boost = 0
            else:
                popularity_boost = 0
            
            price_str = part.get("price", "50")
            try:
                price = float(price_str.replace("$", "").replace(",", ""))
                price_penalty = -0.05 if price > 100 else 0
            except:
                price_penalty = 0
            
            final_score = relevance_score + symptom_boost + popularity_boost + price_penalty
            
            part_copy = part.copy()
            part_copy["relevance_score"] = round(final_score, 3)
            part_copy["ranking_factors"] = {
                "base_relevance": round(relevance_score, 3),
                "symptom_match": round(symptom_boost, 3),
                "popularity": round(popularity_boost, 3),
                "price_factor": round(price_penalty, 3)
            }
            ranked.append(part_copy)
        
        ranked.sort(key=lambda x: x["relevance_score"], reverse=True)
        return ranked

    def _get_popular_parts(self, appliance: str = "refrigerator", limit: int = 10) -> List[Dict]:
        """
        Fallback: Return most commonly needed parts for an appliance
        Used when vector search fails or returns no results
        """
        
        logger.info(f"[FALLBACK] Getting popular parts for {appliance}")
        
        # Get all parts
        all_parts = list(state["part_id_map"].values())
        
        # Filter by appliance type if possible
        filtered = []
        for part in all_parts:
            product_types = part.get("product_types", "").lower()
            if appliance.lower() in product_types:
                # Add artificial similarity score
                part_copy = part.copy()
                part_copy["similarity_score"] = 0.5  # Medium relevance
                filtered.append(part_copy)
        
        # If no appliance match, just return first N parts
        if not filtered:
            for part in all_parts[:limit]:
                part_copy = part.copy()
                part_copy["similarity_score"] = 0.4
                filtered.append(part_copy)
        
        # Sort by rating if available
        filtered.sort(key=lambda x: float(x.get("rating", 3.0)) if x.get("rating") and x.get("rating") != "N/A" else 3.0, reverse=True)
        
        return filtered[:limit]

    
    def _fallback_part_response(self, part_data):
        """Fallback when LLM fails validation"""
        return {
            "explanation": f"Part {part_data['part_id']} - {part_data['title']}",
            "installation_steps": [
                "Disconnect power",
                "Remove old part",
                "Install new part",
                "Test"
            ],
            "tips": ["Refer to manual"]
        }
    
    def _fallback_diagnostic_response(self):
        """Fallback when LLM fails"""
        return {
            "explanation": "Based on your symptom, here are recommended parts:",
            "diagnostic_steps": ["Verify issue", "Check for damage", "Test component"],
            "tips": []
        }

    def _part_not_found(self, part_id):
        return AgentResponse(
            type="clarification_needed",
            confidence=0.3,
            requires_clarification=True,
            message=f"Part {part_id} not found in database."
        )
    
    def _find_compatible_alternatives(self, model_id: str, original_part_id: str, limit: int = 3) -> List[PartInfo]:
        """Find alternative parts compatible with model"""
        original = state["part_id_map"].get(original_part_id, {})
        original_title = original.get("title", "")
        
        compatible_part_ids = state["model_id_to_parts_map"].get(model_id, [])
        if not compatible_part_ids:
            return []
        
        alternatives = []
        fallback_candidates = []
        for pid in compatible_part_ids[:20]:
            if pid == original_part_id:
                continue
            
            part_data = state["part_id_map"].get(pid)
            if not part_data:
                continue
            
            fallback_candidates.append(part_data)
            
            title = part_data.get("title", "")
            similarity = self._compute_title_similarity(original_title, title)
            
            if similarity > 0.3:
                part_info = self._build_part_info(part_data)
                part_info.relevance_score = similarity
                alternatives.append(part_info)
        
        alternatives.sort(key=lambda x: x.relevance_score or 0, reverse=True)
        if alternatives:
            return alternatives[:limit]
        
        # Fallback: return top compatible parts by rating when title similarity is low
        rated_fallback = []
        for part_data in fallback_candidates:
            part_info = self._build_part_info(part_data)
            part_info.relevance_score = 0.2
            rated_fallback.append(part_info)
        
        rated_fallback.sort(key=lambda p: p.rating if p.rating is not None else 0.0, reverse=True)
        return rated_fallback[:limit]
    
    def _build_search_query(self, symptom, session_entities):
        query_parts = [symptom]
        if session_entities.get("appliance"):
            query_parts.append(session_entities["appliance"])
        if session_entities.get("brand"):
            query_parts.append(session_entities["brand"])
        
        # Deduplicate repeated words to keep embeddings faster and cleaner.
        words = " ".join(query_parts).split()
        deduped = []
        seen = set()
        for word in words:
            normalized = word.lower()
            if normalized not in seen:
                deduped.append(word)
                seen.add(normalized)
        
        compact_query = " ".join(deduped)
        return compact_query[:180]

    def _compute_title_similarity(self, title1: str, title2: str) -> float:
        """Simple keyword-based similarity"""
        words1 = set(title1.lower().split())
        words2 = set(title2.lower().split())
        stop_words = {"and", "or", "the", "a", "an", "for", "with", "of"}
        words1 = words1 - stop_words
        words2 = words2 - stop_words
        
        if not words1 or not words2:
            return 0.0
        
        intersection = len(words1 & words2)
        union = len(words1 | words2)
        return intersection / union if union > 0 else 0.0
