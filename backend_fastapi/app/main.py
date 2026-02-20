"""FastAPI service entrypoint for the PartSelect support agent."""

import logging
import uuid
from datetime import datetime, timezone
from contextlib import asynccontextmanager
from typing import Dict, List, Optional

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from app.agent.router import ApplianceAgent
from app.core.state import get_stats
from app.core.metrics import metrics_logger

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(_: FastAPI):
    """Application lifecycle hooks."""
    logger.info("=" * 60)
    logger.info("PartSelect Customer Support Agent Starting...")
    logger.info("=" * 60)
    stats = get_stats()
    logger.info(f"Loaded {stats['total_parts']} parts")
    logger.info(f"Loaded {stats['total_models']} models")
    logger.info("Agent initialized")
    logger.info("=" * 60)
    yield
    logger.info("Shutting down...")


app = FastAPI(
    title="PartSelect Customer Support Agent",
    description="AI-powered appliance parts assistant",
    version="1.0.0",
    lifespan=lifespan
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # In production, specify exact origins
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


agent = ApplianceAgent()
sessions: Dict[str, Dict] = {}

class ChatMessage(BaseModel):
    """Single chat message."""
    role: str = Field(..., description="'user' or 'assistant'")
    content: str


class ChatRequest(BaseModel):
    """Request payload for the chat endpoint."""
    message: str = Field(..., description="User's message")
    conversation_id: Optional[str] = Field(None, description="Conversation ID for context")
    messages: Optional[List[ChatMessage]] = Field(None, description="Full conversation history")


class ChatResponse(BaseModel):
    """Response payload for the chat endpoint."""
    conversation_id: str
    response: Dict
    timestamp: str


def get_or_create_session(conversation_id: Optional[str]) -> tuple[str, Dict]:
    """
    Get existing session or create new one
    
    Returns:
        (conversation_id, session_entities)
    """
    
    if conversation_id and conversation_id in sessions:
        return conversation_id, sessions[conversation_id]["entities"]
    
    new_id = str(uuid.uuid4())
    sessions[new_id] = {
        "entities": {},
        "messages": [],
        "created_at": datetime.now(timezone.utc).isoformat()
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
        "timestamp": datetime.now(timezone.utc).isoformat()
    })
    
    session["messages"].append({
        "role": "assistant",
        "content": agent_response,
        "timestamp": datetime.now(timezone.utc).isoformat()
    })
    
    session["messages"] = session["messages"][-20:]


def build_conversation_summary(conversation_id: str) -> str:
    """Build summary of conversation for context"""
    
    if conversation_id not in sessions:
        return ""
    
    messages = sessions[conversation_id]["messages"]
    
    if not messages:
        return ""
    
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


@app.post("/chat", response_model=ChatResponse)
async def chat(request: ChatRequest):
    """
    Main chat endpoint.
    """
    
    try:
        conversation_id, session_entities = get_or_create_session(request.conversation_id)
        conversation_summary = build_conversation_summary(conversation_id)
        logger.info(f"[CHAT] conversation_id={conversation_id}, message='{request.message}'")
        
        response = agent.handle_query(
            user_query=request.message,
            conversation_id=conversation_id,
            conversation_summary=conversation_summary,
            session_entities=session_entities
        )
        
        response_dict = response.model_dump()
        update_session(conversation_id, request.message, response_dict)
        
        logger.info(f"[CHAT] Response type: {response_dict['type']}, confidence: {response_dict['confidence']}")
        
        return ChatResponse(
            conversation_id=conversation_id,
            response=response_dict,
            timestamp=datetime.now(timezone.utc).isoformat()
        )
        
    except Exception as e:
        logger.error(f"[CHAT ERROR] {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/health")
async def health_check():
    """Return service health and loaded state summary."""
    
    stats = get_stats()
    
    return {
        "status": "healthy",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "stats": stats
    }


@app.get("/metrics")
async def metrics():
    """Return lightweight service metrics."""
    
    stats = get_stats()
    
    return {
        "total_parts": stats["total_parts"],
        "total_models": stats["total_models"],
        "active_sessions": len(sessions),
        "total_conversations": sum(
            len(s["messages"]) for s in sessions.values()
        ),
        "timestamp": datetime.now(timezone.utc).isoformat()
    }


@app.get("/session/{conversation_id}")
async def get_session(conversation_id: str):
    """Return session details for debugging."""
    
    if conversation_id not in sessions:
        raise HTTPException(status_code=404, detail="Session not found")
    
    session = sessions[conversation_id]
    
    return {
        "conversation_id": conversation_id,
        "entities": session["entities"],
        "message_count": len(session["messages"]),
        "messages": session["messages"][-10:],
        "created_at": session["created_at"]
    }


@app.delete("/session/{conversation_id}")
async def clear_session(conversation_id: str):
    """Clear a conversation session."""
    
    if conversation_id in sessions:
        del sessions[conversation_id]
        return {"message": "Session cleared"}
    
    return {"message": "Session not found"}


@app.get("/analytics")
async def analytics():
    """Return aggregated analytics from the metrics log."""
    
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
    """Return planner cache stats."""
    
    try:
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
