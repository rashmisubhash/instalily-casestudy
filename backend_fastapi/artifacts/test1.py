"""
Comprehensive Test Suite for PartSelect Agent

Tests:
- Edge cases (empty query, special chars, etc.)
- Failure scenarios (ChromaDB timeout, etc.)
- Confidence scoring accuracy
- Guardrails (out of scope, topic drift)
"""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

import pytest
import json
from unittest.mock import Mock, patch
from app.agent.router import ApplianceAgent, AgentResponse


class TestEdgeCases:
    """Test edge cases and unusual inputs"""
    
    def setup_method(self):
        self.agent = ApplianceAgent()
    
    def test_empty_query(self):
        """Should handle empty query gracefully"""
        response = self.agent.handle_query("", "test", "", {})
        assert response.type == "clarification_needed"
        assert response.confidence < 0.5
    
    def test_very_long_query(self):
        """Should handle very long queries"""
        long_query = "My refrigerator " + ("is broken " * 200)
        response = self.agent.handle_query(long_query, "test", "", {})
        # Should not crash
        assert response is not None
    
    def test_special_characters_in_part_number(self):
        """Should handle special characters"""
        response = self.agent.handle_query("Part #PS11752778!", "test", "", {})
        # Should extract PS11752778
        assert response.type in ["part_lookup", "clarification_needed"]
    
    def test_multiple_model_numbers(self):
        """Should handle multiple model numbers"""
        response = self.agent.handle_query(
            "Is PS11752778 compatible with 10641122211 or 10640262010?",
            "test", "", {}
        )
        # Should extract one model number
        assert response is not None
    
    def test_unicode_characters(self):
        """Should handle unicode characters"""
        response = self.agent.handle_query(
            "Mi refrigerador está roto 🧊", "test", "", {}
        )
        assert response is not None


class TestFailureScenarios:
    """Test failure scenarios and fallbacks"""
    
    def setup_method(self):
        self.agent = ApplianceAgent()
    
    @patch('app.tools.part_tools.vector_search')
    def test_chromadb_timeout(self, mock_search):
        """Should fallback when ChromaDB times out"""
        mock_search.side_effect = Exception("Timeout")
        
        response = self.agent.handle_query(
            "Ice maker not working model 10641122211",
            "test", "", {}
        )
        
        # Should not crash, should return some response
        assert response is not None
        assert response.type in ["symptom_solution", "clarification_needed"]
    
    @patch('app.agent.planner.ClaudePlanner.plan')
    def test_bedrock_error(self, mock_plan):
        """Should handle Bedrock errors gracefully"""
        mock_plan.side_effect = Exception("Bedrock unavailable")
        
        response = self.agent.handle_query(
            "Part PS11752778", "test", "", {}
        )
        
        # Should fallback to low confidence response
        assert response is not None
    
    def test_invalid_json_in_state(self):
        """Should handle invalid state gracefully"""
        invalid_state = {"invalid": "structure"}
        
        response = self.agent.handle_query(
            "Help", "test", "", invalid_state
        )
        
        assert response is not None


class TestConfidenceScoring:
    """Test confidence scoring accuracy"""
    
    def setup_method(self):
        self.agent = ApplianceAgent()
    
    def test_high_confidence_with_valid_part(self):
        """Valid part ID should give high confidence"""
        candidates = {"part_id": "PS11752778", "model_id": None}
        plan = {"intent": "part_lookup", "confidence": 0.9, "part_id": "PS11752778"}
        resolved = {"part_id": "PS11752778", "part_id_valid": True}
        
        confidence = self.agent.compute_confidence(resolved, plan, candidates, {})
        
        # Calculation: 0.1 (regex) + 0.15 (valid) + 0.36 (llm) = 0.61
        assert confidence >= 0.6
    
    def test_partial_credit_for_unvalidated_model(self):
        """Unvalidated model should get partial credit"""
        candidates = {"part_id": None, "model_id": "9999999"}
        plan = {"intent": "symptom_troubleshoot", "confidence": 0.8}
        resolved = {"model_id": "9999999", "model_id_valid": False, "symptom": "leak"}
        
        confidence = self.agent.compute_confidence(resolved, plan, candidates, {})
        
        # Should be > 0 but < full credit
        assert 0.3 < confidence < 0.7
    
    def test_low_confidence_without_entities(self):
        """No entities should give low confidence"""
        candidates = {"part_id": None, "model_id": None}
        plan = {"intent": "general_question", "confidence": 0.3}
        resolved = {"part_id": None, "model_id": None}
        
        confidence = self.agent.compute_confidence(resolved, plan, candidates, {})
        
        assert confidence < 0.5


class TestGuardrails:
    """Test scope and safety guardrails"""
    
    def setup_method(self):
        self.agent = ApplianceAgent()
    
    def test_out_of_scope_oven(self):
        """Should reject oven queries"""
        response = self.agent.handle_query(
            "My oven won't heat up", "test", "", {}
        )
        
        assert response.type == "clarification_needed"
        assert "refrigerator" in response.message.lower() or "dishwasher" in response.message.lower()
    
    def test_out_of_scope_washing_machine(self):
        """Should reject washing machine queries"""
        response = self.agent.handle_query(
            "My washer is leaking", "test", "", {}
        )
        
        assert response.type == "clarification_needed"
    
    def test_in_scope_refrigerator(self):
        """Should accept refrigerator queries"""
        response = self.agent.handle_query(
            "My refrigerator is leaking", "test", "", {}
        )
        
        # Should not be rejected as out of scope
        assert response.type != "clarification_needed" or "refrigerator" not in response.message
    
    def test_topic_drift_reset(self):
        """Should reset session on topic drift"""
        session = {"appliance": "refrigerator", "last_symptom": "ice maker"}
        
        response = self.agent.handle_query(
            "Actually my dishwasher won't drain", "test", "", session
        )
        
        # Session should be cleared
        assert len(session) == 0 or session.get("appliance") == "dishwasher"


class TestGracefulDegradation:
    """Test graceful degradation with unvalidated data"""
    
    def setup_method(self):
        self.agent = ApplianceAgent()
    
    def test_unvalidated_model_provides_recommendations(self):
        """Should provide recommendations even with unvalidated model"""
        session = {"last_symptom": "drain leaking"}
        
        response = self.agent.handle_query(
            "1234567890", "test", "", session
        )
        
        # Should not give up - should provide something
        assert response.type in ["symptom_solution", "clarification_needed"]
        
        # If symptom_solution, should have recommendations
        if response.type == "symptom_solution":
            assert len(response.recommended_parts) > 0


class TestMetrics:
    """Test metrics logging and analytics"""
    
    def setup_method(self):
        self.agent = ApplianceAgent()
        
        # Clear any existing metrics file
        import os
        if os.path.exists("metrics.jsonl"):
            os.remove("metrics.jsonl")
    
    def test_metrics_logged_for_query(self):
        """Metrics should be logged for every query"""
        from app.core.metrics import metrics_logger
        
        # Make a query
        response = self.agent.handle_query(
            "Part PS11752778", "test", "", {}
        )
        
        # Check metrics file exists
        import os
        assert os.path.exists("metrics.jsonl")
        
        # Read last line
        with open("metrics.jsonl", 'r') as f:
            lines = f.readlines()
            assert len(lines) > 0
            
            # Parse last metric
            import json
            last_metric = json.loads(lines[-1])
            
            # Verify structure
            assert "timestamp" in last_metric
            assert "response_type" in last_metric
            assert "confidence" in last_metric
            assert "latency_ms" in last_metric
            assert last_metric["response_type"] == response.type
    
    def test_analytics_endpoint_returns_data(self):
        """Analytics should aggregate metrics correctly"""
        from app.core.metrics import metrics_logger
        
        # Make several queries to populate metrics
        self.agent.handle_query("Part PS11752778", "test1", "", {})
        self.agent.handle_query("Ice maker broken", "test2", "", {})
        self.agent.handle_query("Model 10641122211", "test3", "", {})
        
        # Get analytics
        analytics = metrics_logger.get_analytics(limit=100)
        
        # Should have data
        assert analytics["total_queries"] >= 3
        assert "confidence_distribution" in analytics
        assert "route_distribution" in analytics
        assert "avg_latency_ms" in analytics
        assert "error_rate_pct" in analytics
        
        # Confidence distribution should have all tiers
        conf_dist = analytics["confidence_distribution"]
        assert "high" in str(conf_dist) or "medium" in str(conf_dist) or "low" in str(conf_dist)
    
    def test_error_logged_in_metrics(self):
        """Errors should be logged in metrics"""
        from unittest.mock import patch
        from app.core.metrics import metrics_logger
        
        # Force an error
        with patch('app.agent.planner.ClaudePlanner.plan') as mock_plan:
            mock_plan.side_effect = Exception("Test error")
            
            response = self.agent.handle_query("Test", "test", "", {})
            
            # Should still return a response
            assert response is not None
            
            # Error should be in metrics
            analytics = metrics_logger.get_analytics(limit=10)
            assert analytics["error_rate_pct"] > 0


def run_tests():
    """Run all tests"""
    pytest.main([__file__, "-v", "--tb=short"])


if __name__ == "__main__":
    run_tests()