"""
Claude-based Planner for Intent Classification and Entity Extraction

Uses AWS Bedrock Claude to:
1. Classify user intent
2. Extract entities (part_id, model_id, symptom)
3. Return confidence score
"""

import json
import logging
import boto3
import hashlib
import re
from typing import Dict, Any

logger = logging.getLogger(__name__)


class ClaudePlanner:
    """
    LLM-based planner using AWS Bedrock Claude
    """
    
    def __init__(self, model_id: str = "anthropic.claude-3-haiku-20240307-v1:0"):
        """
        Initialize Bedrock client
        
        Args:
            model_id: Bedrock inference profile ID (default: Claude 3.5 Sonnet cross-region)
        """
        self.bedrock = boto3.client(
            service_name='bedrock-runtime',
            region_name='us-east-1'  # Change as needed
        )
        self.model_id = model_id
        
        # Simple in-memory cache for repeated queries
        self._cache = {}
        self._cache_hits = 0
        self._cache_misses = 0
        
        self.system_prompt = """You are an intent classifier for an appliance parts customer service agent.

Your job is to analyze user messages and extract:
1. **intent** - What the user wants to do
2. **entities** - Specific information mentioned
3. **confidence** - How confident you are (0.0 to 1.0)

## Intents:
- **part_lookup**: User wants info about a specific part
- **install_help**: User wants installation instructions
- **compatibility_check**: User wants to know if part works with their model
- **symptom_troubleshoot**: User describes a problem and needs diagnosis
- **general_question**: General question about appliances

## Entities to extract:
- **part_id**: Part number (format: PS followed by digits, e.g., PS11752778)
- **model_id**: Model number (alphanumeric, 6-15 characters)
- **symptom**: Problem description
- **appliance**: Type (refrigerator, dishwasher, etc.)
- **brand**: Manufacturer (Whirlpool, GE, etc.)

## Response Format (JSON):
{
    "intent": "intent_name",
    "confidence": 0.0-1.0,
    "part_id": "PS11752778" or null,
    "model_id": "WDT780SAEM1" or null,
    "symptom": "ice maker not working" or null,
    "appliance": "refrigerator" or null,
    "brand": "Whirlpool" or null,
    "query": "normalized user query"
}

## Examples:

User: "How do I install part PS11752778?"
{
    "intent": "install_help",
    "confidence": 0.95,
    "part_id": "PS11752778",
    "model_id": null,
    "symptom": null,
    "appliance": null,
    "brand": null,
    "query": "install PS11752778"
}

User: "Is this part compatible with my WDT780SAEM1?"
{
    "intent": "compatibility_check",
    "confidence": 0.90,
    "part_id": null,
    "model_id": "WDT780SAEM1",
    "symptom": null,
    "appliance": null,
    "brand": null,
    "query": "compatibility check WDT780SAEM1"
}

User: "My Whirlpool fridge ice maker isn't working"
{
    "intent": "symptom_troubleshoot",
    "confidence": 0.85,
    "part_id": null,
    "model_id": null,
    "symptom": "ice maker not working",
    "appliance": "refrigerator",
    "brand": "Whirlpool",
    "query": "Whirlpool refrigerator ice maker not working"
}

User: "It's leaking from the bottom"
{
    "intent": "symptom_troubleshoot",
    "confidence": 0.70,
    "part_id": null,
    "model_id": null,
    "symptom": "leaking from bottom",
    "appliance": null,
    "brand": null,
    "query": "leaking from bottom"
}

IMPORTANT:
- Return ONLY valid JSON, no markdown or explanations
- If uncertain, lower the confidence score
- Normalize text in "query" field for searching
- Extract ALL entities you can find
"""

    def plan(self, user_input: str) -> Dict[str, Any]:
        """
        Plan the response based on user input (with caching)
        
        Args:
            user_input: Raw user query with optional context
            
        Returns:
            Dict with intent, entities, and confidence
        """
        
        # Generate cache key from normalized input
        cache_key = hashlib.md5(user_input.lower().strip().encode()).hexdigest()
        
        # Check cache
        if cache_key in self._cache:
            self._cache_hits += 1
            logger.info(f"[PLANNER CACHE HIT] {self._cache_hits} hits, {self._cache_misses} misses")
            return self._cache[cache_key]
        
        self._cache_misses += 1
        
        try:
            # Call Claude via Bedrock
            response = self._call_bedrock(user_input, max_tokens=220)
            
            # Parse JSON response
            plan = self._parse_response(response)
            
            # Validate and clean
            plan = self._validate_plan(plan)
            
            logger.info(f"[PLANNER] Intent: {plan.get('intent')}, Confidence: {plan.get('confidence')}")
            
            # Store in cache (limit size to 1000 entries)
            if len(self._cache) < 1000:
                self._cache[cache_key] = plan
            
            return plan
            
        except ValueError as e:
            logger.warning(f"[PLANNER PARSE] {e}")
            return self._fallback_plan(user_input=user_input)
        except Exception as e:
            logger.error(f"[PLANNER ERROR] {str(e)}", exc_info=True)
            return self._fallback_plan(user_input=user_input)

    def _call_bedrock(self, user_input: str, max_tokens: int = 350) -> str:
        """Call AWS Bedrock Claude API"""
        
        body = json.dumps({
            "anthropic_version": "bedrock-2023-05-31",
            "max_tokens": max_tokens,
            "system": self.system_prompt,
            "messages": [
                {
                    "role": "user",
                    "content": user_input
                }
            ],
            "temperature": 0.0  # Deterministic for classification
        })
        
        response = self.bedrock.invoke_model(
            modelId=self.model_id,
            body=body
        )
        
        response_body = json.loads(response['body'].read())
        
        # Extract text from response
        content = response_body.get('content', [])
        if content and len(content) > 0:
            return content[0].get('text', '')
        
        raise ValueError("Empty response from Bedrock")

    def _parse_response(self, response_text: str) -> Dict[str, Any]:
        """Parse JSON response from Claude"""
        
        # Clean up response (remove markdown if present)
        cleaned = response_text.strip()
        
        # Remove markdown code blocks if present
        if cleaned.startswith('```'):
            # Find first { and last }
            start = cleaned.find('{')
            end = cleaned.rfind('}')
            if start != -1 and end != -1:
                cleaned = cleaned[start:end+1]
        else:
            # Extract JSON object even if followed by additional text
            start = cleaned.find('{')
            if start != -1:
                # Find matching closing brace
                brace_count = 0
                end = start
                for i in range(start, len(cleaned)):
                    if cleaned[i] == '{':
                        brace_count += 1
                    elif cleaned[i] == '}':
                        brace_count -= 1
                        if brace_count == 0:
                            end = i
                            break
                if end > start:
                    cleaned = cleaned[start:end+1]
        
        # Parse JSON
        try:
            return json.loads(cleaned)
        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse JSON: {cleaned}")
            raise ValueError(f"Invalid JSON response: {e}")

    def _validate_plan(self, plan: Dict[str, Any]) -> Dict[str, Any]:
        """Validate and clean the plan"""
        
        # Ensure required fields exist
        if "intent" not in plan:
            plan["intent"] = "general_question"
        
        if "confidence" not in plan:
            plan["confidence"] = 0.5
        else:
            # Clamp confidence between 0 and 1
            plan["confidence"] = max(0.0, min(1.0, float(plan["confidence"])))
        
        # Clean up None/"null" strings
        for key in ["part_id", "model_id", "symptom", "appliance", "brand", "query"]:
            if key not in plan:
                plan[key] = None
            elif plan[key] in ["null", "None", ""]:
                plan[key] = None
        
        # Normalize part_id and model_id to uppercase
        if plan.get("part_id"):
            plan["part_id"] = plan["part_id"].upper().strip()
        
        if plan.get("model_id"):
            plan["model_id"] = plan["model_id"].upper().strip()
        
        return plan

    def _fallback_plan(self, user_input: str = "") -> Dict[str, Any]:
        """Fallback plan when LLM fails"""

        clean = (user_input or "").strip().upper()
        part_match = re.search(r"\bPS\d{5,}\b", clean)
        model_match = re.search(r"\b[A-Z0-9]{6,15}\b", clean)
        model_id = None
        if model_match:
            candidate = model_match.group(0)
            if not candidate.startswith("PS") and not candidate.isalpha():
                model_id = candidate

        if part_match:
            return {
                "intent": "part_lookup",
                "confidence": 0.55,
                "part_id": part_match.group(0),
                "model_id": model_id,
                "symptom": None,
                "appliance": None,
                "brand": None,
                "query": user_input.lower().strip() if user_input else None
            }

        return {
            "intent": "general_question",
            "confidence": 0.3,
            "part_id": None,
            "model_id": model_id,
            "symptom": None,
            "appliance": None,
            "brand": None,
            "query": user_input.lower().strip() if user_input else None
        }
