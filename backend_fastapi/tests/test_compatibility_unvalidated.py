from app.agent.handlers import AgentHandlers
from app.core.state import state


def test_unknown_model_returns_likely_alternatives(monkeypatch):
    handlers = AgentHandlers()

    state["part_id_map"] = {
        "PS11752778": {
            "part_id": "PS11752778",
            "title": "Dishwasher Dishrack Wheel Kit",
            "brand": "Whirlpool",
            "price": "$8.99",
            "description": "Wheel kit for lower dish rack.",
            "symptoms": "wheel broken|rack not rolling",
            "url": "https://www.partselect.com/PS11752778",
            "rating": "4.7",
        },
        "PS10000001": {
            "part_id": "PS10000001",
            "title": "Dishrack Roller Assembly",
            "brand": "Whirlpool",
            "price": "$10.99",
            "description": "Replacement roller assembly.",
            "symptoms": "rack not rolling",
            "url": "https://www.partselect.com/PS10000001",
            "rating": "4.5",
        },
        "PS10000002": {
            "part_id": "PS10000002",
            "title": "Dishwasher Rail Support",
            "brand": "Whirlpool",
            "price": "$12.99",
            "description": "Rail support replacement part.",
            "symptoms": "rack unstable",
            "url": "https://www.partselect.com/PS10000002",
            "rating": "4.4",
        },
    }

    monkeypatch.setattr(
        "app.agent.handlers.vector_search",
        lambda *args, **kwargs: [
            {"part_id": "PS11752778", "similarity_score": 0.9},
            {"part_id": "PS10000001", "similarity_score": 0.8},
            {"part_id": "PS10000002", "similarity_score": 0.7},
        ],
    )

    response = handlers.handle_compatibility_unvalidated(
        part_id="PS11752778",
        model_id="WDT780SAEM1",
        resolved={},
        session_entities={},
        confidence=0.8,
        user_query="Is this part compatible with WDT780SAEM1?",
    )

    assert response.type == "compatibility"
    assert response.requires_clarification is True
    assert response.compatible is None
    assert len(response.alternative_parts) == 2
    assert "couldn't verify model" in (response.explanation or "").lower()
