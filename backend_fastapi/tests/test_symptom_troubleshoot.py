from app.agent.handlers import AgentHandlers
from app.core.state import state


def test_validated_symptom_flow_uses_llm_generation(monkeypatch):
    handlers = AgentHandlers()

    state["model_id_to_parts_map"] = {"WDT780SAEM1": ["PS11752778"]}
    state["part_id_map"] = {
        "PS11752778": {
            "part_id": "PS11752778",
            "title": "Dishwasher Drain Pump",
            "brand": "Whirlpool",
            "price": "$49.99",
            "description": "Drains water from dishwasher tub.",
            "symptoms": "not draining|standing water",
            "url": "https://www.partselect.com/PS11752778",
            "rating": "4.7",
        }
    }

    def fake_vector_search(query, top_k=20):
        return [
            {
                "part_id": "PS11752778",
                "title": "Dishwasher Drain Pump",
                "brand": "Whirlpool",
                "price": "$49.99",
                "description": "Drains water from dishwasher tub.",
                "symptoms": "not draining|standing water",
                "url": "https://www.partselect.com/PS11752778",
                "rating": "4.7",
                "similarity_score": 0.82,
            }
        ]

    captured = {}

    def fake_generate(symptom, model_id, recommended_parts, user_query):
        captured["symptom"] = symptom
        captured["model_id"] = model_id
        captured["recommended_parts"] = recommended_parts
        captured["user_query"] = user_query
        return {
            "explanation": "Drain pump is the most likely failure point.",
            "diagnostic_steps": ["Check for standing water.", "Inspect pump impeller."],
            "tips": ["Disconnect power before servicing."],
        }

    monkeypatch.setattr("app.agent.handlers.vector_search", fake_vector_search)
    monkeypatch.setattr(handlers, "_generate_diagnostic_response", fake_generate)

    response = handlers.handle_symptom_troubleshoot(
        symptom="dishwasher not draining",
        model_id="WDT780SAEM1",
        session_entities={"appliance": "dishwasher"},
        confidence=0.6,
        user_query="My dishwasher is not draining, model WDT780SAEM1",
    )

    assert response.type == "symptom_solution"
    assert response.recommended_parts
    assert response.diagnostic_steps == ["Check for standing water.", "Inspect pump impeller."]
    assert response.confidence > 0.6
    assert captured["symptom"] == "dishwasher not draining"
    assert captured["model_id"] == "WDT780SAEM1"
    assert captured["recommended_parts"][0]["part_id"] == "PS11752778"


def test_validated_symptom_flow_falls_back_when_llm_generation_fails(monkeypatch):
    handlers = AgentHandlers()

    state["model_id_to_parts_map"] = {"WDT780SAEM1": ["PS11752778"]}
    state["part_id_map"] = {
        "PS11752778": {
            "part_id": "PS11752778",
            "title": "Dishwasher Drain Pump",
            "brand": "Whirlpool",
            "price": "$49.99",
            "description": "Drains water from dishwasher tub.",
            "symptoms": "not draining|standing water",
            "url": "https://www.partselect.com/PS11752778",
            "rating": "4.7",
        }
    }

    monkeypatch.setattr(
        "app.agent.handlers.vector_search",
        lambda *args, **kwargs: [
            {
                "part_id": "PS11752778",
                "title": "Dishwasher Drain Pump",
                "brand": "Whirlpool",
                "price": "$49.99",
                "description": "Drains water from dishwasher tub.",
                "symptoms": "not draining|standing water",
                "url": "https://www.partselect.com/PS11752778",
                "rating": "4.7",
                "similarity_score": 0.81,
            }
        ],
    )

    def raises(*args, **kwargs):
        raise RuntimeError("LLM unavailable")

    monkeypatch.setattr(handlers, "_generate_diagnostic_response", raises)

    response = handlers.handle_symptom_troubleshoot(
        symptom="dishwasher not draining",
        model_id="WDT780SAEM1",
        session_entities={"appliance": "dishwasher"},
        confidence=0.6,
        user_query="My dishwasher is not draining, model WDT780SAEM1",
    )

    assert response.type == "symptom_solution"
    assert response.recommended_parts
    assert response.explanation == "Based on your symptom, here are recommended parts:"
