"""
Metrics Logger for Observability

Tracks:
- Query patterns
- Response times
- Confidence distributions
- Route distributions
- Error rates
"""

import json
import logging
from datetime import datetime
from typing import Dict, Any, Optional
from pathlib import Path

logger = logging.getLogger(__name__)


class MetricsLogger:
    """Simple metrics logger for production observability"""
    
    def __init__(self, log_file: str = "metrics.jsonl"):
        self.log_file = Path(log_file)
        self.log_file.parent.mkdir(parents=True, exist_ok=True)
    
    def log_query(
        self,
        query: str,
        response_type: str,
        confidence: float,
        latency: float,
        route: str,
        intent: Optional[str] = None,
        entities: Optional[Dict] = None,
        error: Optional[str] = None
    ):
        """Log a single query with metadata"""
        
        metrics = {
            "timestamp": datetime.utcnow().isoformat(),
            "query_length": len(query),
            "response_type": response_type,
            "confidence": round(confidence, 3),
            "latency_ms": round(latency * 1000, 2),
            "route": route,
            "intent": intent,
            "entities": entities or {},
            "error": error
        }
        
        # Write to file (one JSON object per line)
        try:
            with open(self.log_file, 'a') as f:
                f.write(json.dumps(metrics) + '\n')
        except Exception as e:
            logger.error(f"Failed to write metrics: {e}")
        
        # Also log to standard logger
        logger.info(f"[METRICS] {json.dumps(metrics)}")
    
    def get_analytics(self, limit: int = 1000) -> Dict[str, Any]:
        """
        Read recent metrics and compute analytics
        
        Returns aggregated statistics for monitoring
        """
        
        if not self.log_file.exists():
            return {
                "total_queries": 0,
                "confidence_distribution": {},
                "route_distribution": {},
                "avg_latency_ms": 0,
                "error_rate": 0
            }
        
        # Read last N lines
        metrics = []
        try:
            with open(self.log_file, 'r') as f:
                lines = f.readlines()
                for line in lines[-limit:]:
                    try:
                        metrics.append(json.loads(line.strip()))
                    except json.JSONDecodeError:
                        continue
        except Exception as e:
            logger.error(f"Failed to read metrics: {e}")
            return {"error": str(e)}
        
        if not metrics:
            return {
                "total_queries": 0,
                "confidence_distribution": {},
                "route_distribution": {},
                "avg_latency_ms": 0,
                "error_rate": 0
            }
        
        # Compute statistics
        total = len(metrics)
        
        # Confidence distribution
        high_conf = sum(1 for m in metrics if m["confidence"] >= 0.8)
        medium_conf = sum(1 for m in metrics if 0.6 <= m["confidence"] < 0.8)
        low_conf = sum(1 for m in metrics if m["confidence"] < 0.6)
        
        # Route distribution
        route_counts = {}
        for m in metrics:
            route = m.get("route", "unknown")
            route_counts[route] = route_counts.get(route, 0) + 1
        
        # Response type distribution
        type_counts = {}
        for m in metrics:
            rtype = m.get("response_type", "unknown")
            type_counts[rtype] = type_counts.get(rtype, 0) + 1
        
        # Average latency
        avg_latency = sum(m["latency_ms"] for m in metrics) / total
        
        # Error rate
        errors = sum(1 for m in metrics if m.get("error"))
        error_rate = (errors / total) * 100
        
        # Intent distribution
        intent_counts = {}
        for m in metrics:
            intent = m.get("intent", "unknown")
            if intent:
                intent_counts[intent] = intent_counts.get(intent, 0) + 1
        
        return {
            "total_queries": total,
            "confidence_distribution": {
                "high (>=0.8)": f"{high_conf} ({high_conf/total*100:.1f}%)",
                "medium (0.6-0.8)": f"{medium_conf} ({medium_conf/total*100:.1f}%)",
                "low (<0.6)": f"{low_conf} ({low_conf/total*100:.1f}%)"
            },
            "route_distribution": {
                k: f"{v} ({v/total*100:.1f}%)" 
                for k, v in sorted(route_counts.items(), key=lambda x: x[1], reverse=True)
            },
            "response_type_distribution": {
                k: f"{v} ({v/total*100:.1f}%)" 
                for k, v in sorted(type_counts.items(), key=lambda x: x[1], reverse=True)
            },
            "intent_distribution": {
                k: f"{v} ({v/total*100:.1f}%)" 
                for k, v in sorted(intent_counts.items(), key=lambda x: x[1], reverse=True)
            },
            "avg_latency_ms": round(avg_latency, 2),
            "error_rate_pct": round(error_rate, 2),
            "time_range": {
                "from": metrics[0]["timestamp"],
                "to": metrics[-1]["timestamp"]
            }
        }


# Global metrics instance
metrics_logger = MetricsLogger()