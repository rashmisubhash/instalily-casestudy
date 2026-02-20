"""
FastAPI Application for PartSelect Customer Support Agent

Endpoints:
- POST /chat: Main chat interface
- GET /health: Health check
- GET /metrics: System metrics
"""

import logging
import uuid
from datetime import datetime
from typing import Dict, List, Optional

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from app.agent.router import ApplianceAgent
from app.core.state import get_stats
from app.core.metrics import metrics_logger

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


# ============================================================================
# FASTAPI APP
# ============================================================================

app = FastAPI(
    title="PartSelect Customer Support Agent",
    description="AI-powered appliance parts assistant",
    version="1.0.0"
)

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # In production, specify exact origins
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ============================================================================
# GLOBAL INSTANCES
# ============================================================================

# Initialize agent
agent = ApplianceAgent()

# In-memory session storage (in production, use Redis)
sessions: Dict[str, Dict] = {}


# ============================================================================
# REQUEST/RESPONSE MODELS
# ============================================================================

class ChatMessage(BaseModel):
    """Individual chat message"""
    role: str = Field(..., description="'user' or 'assistant'")
    content: str


class ChatRequest(BaseModel):
    """Chat API request"""
    message: str = Field(..., description="User's message")
    conversation_id: Optional[str] = Field(None, description="Conversation ID for context")
    messages: Optional[List[ChatMessage]] = Field(None, description="Full conversation history")


class ChatResponse(BaseModel):
    """Chat API response"""
    conversation_id: str
    response: Dict
    timestamp: str


# ============================================================================
# SESSION MANAGEMENT
# ============================================================================

def get_or_create_session(conversation_id: Optional[str]) -> tuple[str, Dict]:
    """
    Get existing session or create new one
    
    Returns:
        (conversation_id, session_entities)
    """
    
    if conversation_id and conversation_id in sessions:
        return conversation_id, sessions[conversation_id]["entities"]
    
    # Create new session
    new_id = str(uuid.uuid4())
    sessions[new_id] = {
        "entities": {},
        "messages": [],
        "created_at": datetime.utcnow().isoformat()
    }
    
    return new_id, sessions[new_id]["entities"]


def update_session(
    conversation_id: str,
    user_message: str,
    agent_response: Dict
):
    """Update session with new messages"""
    
    if conversation_id not in sessions:
        return
    
    session = sessions[conversation_id]
    
    session["messages"].append({
        "role": "user",
        "content": user_message,
        "timestamp": datetime.utcnow().isoformat()
    })
    
    session["messages"].append({
        "role": "assistant",
        "content": agent_response,
        "timestamp": datetime.utcnow().isoformat()
    })
    
    # Keep only last 20 messages
    session["messages"] = session["messages"][-20:]


def build_conversation_summary(conversation_id: str) -> str:
    """Build summary of conversation for context"""
    
    if conversation_id not in sessions:
        return ""
    
    messages = sessions[conversation_id]["messages"]
    
    if not messages:
        return ""
    
    # Simple summary: last 3 exchanges
    recent = messages[-6:] if len(messages) >= 6 else messages
    
    summary_parts = []
    for msg in recent:
        role = msg["role"].capitalize()
        content = msg["content"]
        
        if content is None:
            content_str = "[No content]"
        elif isinstance(content, dict):
            content_str = (
                content.get("explanation")
                or content.get("message")
                or str(content)
            )
        else:
            content_str = str(content)

        content_str = content_str[:200]

        summary_parts.append(f"{role}: {content_str}")
    
    return "\n".join(summary_parts)


# ============================================================================
# ENDPOINTS
# ============================================================================

@app.post("/chat", response_model=ChatResponse)
async def chat(request: ChatRequest):
    """
    Main chat endpoint
    
    Handles:
    1. Part lookup
    2. Compatibility checks
    3. Symptom troubleshooting
    4. Installation help
    """
    
    try:
        # Get or create session
        conversation_id, session_entities = get_or_create_session(request.conversation_id)
        
        # Build conversation summary
        conversation_summary = build_conversation_summary(conversation_id)
        
        # Process query with agent
        logger.info(f"[CHAT] conversation_id={conversation_id}, message='{request.message}'")
        
        response = agent.handle_query(
            user_query=request.message,
            conversation_id=conversation_id,
            conversation_summary=conversation_summary,
            session_entities=session_entities
        )
        
        # Convert Pydantic model to dict
        response_dict = response.dict()
        
        # Update session
        update_session(conversation_id, request.message, response_dict)
        
        logger.info(f"[CHAT] Response type: {response_dict['type']}, confidence: {response_dict['confidence']}")
        
        return ChatResponse(
            conversation_id=conversation_id,
            response=response_dict,
            timestamp=datetime.utcnow().isoformat()
        )
        
    except Exception as e:
        logger.error(f"[CHAT ERROR] {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/health")
async def health_check():
    """Health check endpoint"""
    
    stats = get_stats()
    
    return {
        "status": "healthy",
        "timestamp": datetime.utcnow().isoformat(),
        "stats": stats
    }


@app.get("/metrics")
async def metrics():
    """System metrics endpoint"""
    
    stats = get_stats()
    
    return {
        "total_parts": stats["total_parts"],
        "total_models": stats["total_models"],
        "active_sessions": len(sessions),
        "total_conversations": sum(
            len(s["messages"]) for s in sessions.values()
        ),
        "timestamp": datetime.utcnow().isoformat()
    }


@app.get("/session/{conversation_id}")
async def get_session(conversation_id: str):
    """Get session details (for debugging)"""
    
    if conversation_id not in sessions:
        raise HTTPException(status_code=404, detail="Session not found")
    
    session = sessions[conversation_id]
    
    return {
        "conversation_id": conversation_id,
        "entities": session["entities"],
        "message_count": len(session["messages"]),
        "messages": session["messages"][-10:],  # Last 10 messages
        "created_at": session["created_at"]
    }


@app.delete("/session/{conversation_id}")
async def clear_session(conversation_id: str):
    """Clear session (reset conversation)"""
    
    if conversation_id in sessions:
        del sessions[conversation_id]
        return {"message": "Session cleared"}
    
    return {"message": "Session not found"}


@app.get("/metrics")
async def metrics():
    """Get system metrics"""
    
    stats = get_stats()
    
    return {
        "status": "healthy",
        "stats": stats,
        "active_sessions": len(sessions),
        "total_conversations": sum(len(s["messages"]) for s in sessions.values())
    }


@app.get("/analytics")
async def analytics():
    """
    Get detailed analytics about agent performance
    
    Returns confidence distribution, routing patterns, and performance metrics
    """
    
    try:
        analytics_data = metrics_logger.get_analytics(limit=1000)
        
        return {
            "status": "success",
            "analytics": analytics_data,
            "description": "Last 1000 queries analyzed"
        }
        
    except Exception as e:
        logger.error(f"[ANALYTICS ERROR] {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/debug/cache-stats")
async def cache_stats():
    """
    Get cache performance statistics
    
    Shows planner cache hit rate and efficiency
    """
    
    try:
        # Use GLOBAL agent instance (not a new one)
        global agent
        
        hits = agent.planner._cache_hits
        misses = agent.planner._cache_misses
        total = hits + misses
        
        return {
            "status": "success",
            "planner_cache": {
                "cache_size": len(agent.planner._cache),
                "max_size": 1000,
                "hits": hits,
                "misses": misses,
                "total_requests": total,
                "hit_rate_pct": round((hits / total * 100) if total > 0 else 0, 2),
                "memory_saved_pct": round((hits / total * 100) if total > 0 else 0, 2),
                "avg_time_saved_ms": 1200 if hits > 0 else 0  # Planner call is ~1200ms
            }
        }
        
    except Exception as e:
        logger.error(f"[CACHE STATS ERROR] {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/")
async def root():
    """Root endpoint"""
    
    return {
        "service": "PartSelect Customer Support Agent",
        "version": "1.0.0",
        "status": "running",
        "endpoints": {
            "chat": "POST /chat",
            "health": "GET /health",
            "metrics": "GET /metrics",
            "analytics": "GET /analytics",
            "cache_stats": "GET /debug/cache-stats"
        }
    }


# ============================================================================
# STARTUP/SHUTDOWN
# ============================================================================

@app.on_event("startup")
async def startup_event():
    """Run on startup"""
    
    logger.info("=" * 60)
    logger.info("🚀 PartSelect Customer Support Agent Starting...")
    logger.info("=" * 60)
    
    stats = get_stats()
    logger.info(f"✓ Loaded {stats['total_parts']} parts")
    logger.info(f"✓ Loaded {stats['total_models']} models")
    logger.info(f"✓ Agent initialized")
    logger.info("=" * 60)


@app.on_event("shutdown")
async def shutdown_event():
    """Run on shutdown"""
    
    logger.info("Shutting down...")
