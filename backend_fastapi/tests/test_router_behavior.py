from app.agent.models import AgentResponse
from app.agent.router import ApplianceAgent


def _dummy_response(response_type: str) -> AgentResponse:
    return AgentResponse(
        type=response_type,
        confidence=0.8,
        requires_clarification=response_type in {"clarification_needed", "model_required"},
        message="ok",
    )


def test_session_entities_not_reused_for_new_symptom_query():
    agent = ApplianceAgent()

    plan = {
        "intent": "symptom_troubleshoot",
        "confidence": 0.9,
        "part_id": None,
        "model_id": None,
        "symptom": "ice maker not working",
        "appliance": "refrigerator",
        "brand": "Whirlpool",
        "query": "Whirlpool refrigerator ice maker not working",
    }
    candidates = {"part_id": None, "model_id": None}
    session = {"part_id": "PS11752778", "model_id": "WDT780SAEM1"}

    resolved = agent.validate_and_resolve(plan, candidates, session, "The ice maker is not working")

    assert resolved["part_id"] is None
    assert resolved["model_id"] is None
    assert resolved["symptom"] == "Whirlpool refrigerator ice maker not working"


def test_session_part_reused_only_with_explicit_reference():
    agent = ApplianceAgent()

    plan = {
        "intent": "compatibility_check",
        "confidence": 0.9,
        "part_id": None,
        "model_id": "WDT780SAEM1",
        "symptom": None,
        "appliance": None,
        "brand": None,
        "query": "compatibility check WDT780SAEM1",
    }
    candidates = {"part_id": None, "model_id": None}
    session = {"part_id": "PS11752778"}

    resolved = agent.validate_and_resolve(plan, candidates, session, "Is this part compatible with model WDT780SAEM1?")
    assert resolved["part_id"] == "PS11752778"


def test_compatibility_routing_uses_unvalidated_handler_for_unknown_model(monkeypatch):
    agent = ApplianceAgent()
    called = {"validated": False, "unvalidated": False}

    monkeypatch.setattr(
        agent.handlers,
        "handle_compatibility",
        lambda **kwargs: called.__setitem__("validated", True) or _dummy_response("compatibility"),
    )
    monkeypatch.setattr(
        agent.handlers,
        "handle_compatibility_unvalidated",
        lambda **kwargs: called.__setitem__("unvalidated", True) or _dummy_response("compatibility"),
    )

    resolved = {
        "intent": "compatibility_check",
        "part_id": "PS11752778",
        "model_id": "UNKNOWN123",
        "symptom": None,
        "part_id_valid": True,
        "model_id_valid": False,
    }

    response = agent.route(resolved, {}, 0.8, "Is this part compatible with UNKNOWN123?")

    assert response.type == "compatibility"
    assert called["unvalidated"] is True
    assert called["validated"] is False


def test_compatibility_routing_uses_validated_handler_when_model_exists(monkeypatch):
    agent = ApplianceAgent()
    called = {"validated": False, "unvalidated": False}

    monkeypatch.setattr(
        agent.handlers,
        "handle_compatibility",
        lambda **kwargs: called.__setitem__("validated", True) or _dummy_response("compatibility"),
    )
    monkeypatch.setattr(
        agent.handlers,
        "handle_compatibility_unvalidated",
        lambda **kwargs: called.__setitem__("unvalidated", True) or _dummy_response("compatibility"),
    )

    resolved = {
        "intent": "compatibility_check",
        "part_id": "PS11752778",
        "model_id": "KNOWN123",
        "symptom": None,
        "part_id_valid": True,
        "model_id_valid": True,
    }

    response = agent.route(resolved, {}, 0.8, "Is this part compatible with KNOWN123?")

    assert response.type == "compatibility"
    assert called["validated"] is True
    assert called["unvalidated"] is False


def test_symptom_intent_does_not_get_hijacked_by_compatibility(monkeypatch):
    agent = ApplianceAgent()

    monkeypatch.setattr(
        agent.planner,
        "plan",
        lambda _input: {
            "intent": "symptom_troubleshoot",
            "confidence": 0.9,
            "part_id": None,
            "model_id": None,
            "symptom": "ice maker not working",
            "appliance": "refrigerator",
            "brand": "Whirlpool",
            "query": "Whirlpool refrigerator ice maker not working",
        },
    )

    response = agent.handle_query(
        user_query="The ice maker on my Whirlpool fridge is not working. How can I fix it?",
        conversation_id="c1",
        conversation_summary="",
        session_entities={"part_id": "PS11752778", "model_id": "WDT780SAEM1"},
    )

    assert response.type == "model_required"


def test_model_only_followup_reuses_last_symptom(monkeypatch):
    agent = ApplianceAgent()
    called = {"issue_required": False, "symptom_unvalidated": False}

    monkeypatch.setattr(
        agent.handlers,
        "handle_issue_required",
        lambda **kwargs: called.__setitem__("issue_required", True) or _dummy_response("issue_required"),
    )
    monkeypatch.setattr(
        agent.handlers,
        "handle_symptom_troubleshoot_unvalidated",
        lambda **kwargs: called.__setitem__("symptom_unvalidated", True) or _dummy_response("symptom_solution"),
    )

    resolved = {
        "intent": "part_lookup",
        "part_id": None,
        "model_id": "WRX735SDHZ08",
        "symptom": None,
        "part_id_valid": False,
        "model_id_valid": False,
    }
    session = {
        "last_symptom": "Whirlpool refrigerator ice maker not working",
        "appliance": "refrigerator",
        "brand": "Whirlpool",
    }

    response = agent.route(resolved, session, 0.59, "WRX735SDHZ08")

    assert response.type == "symptom_solution"
    assert called["symptom_unvalidated"] is True
    assert called["issue_required"] is False


def test_out_of_scope_query_returns_clarification(monkeypatch):
    agent = ApplianceAgent()

    monkeypatch.setattr(
        agent.planner,
        "plan",
        lambda _input: {
            "intent": "general_question",
            "confidence": 0.9,
            "part_id": None,
            "model_id": None,
            "symptom": "oven not heating",
            "appliance": "oven",
            "brand": None,
            "query": "oven not heating",
        },
    )

    response = agent.handle_query(
        user_query="My oven is not heating",
        conversation_id="c2",
        conversation_summary="",
        session_entities={},
    )

    assert response.type == "clarification_needed"
    assert "refrigerator and dishwasher" in (response.message or "").lower()


def test_obvious_non_domain_query_bypasses_planner(monkeypatch):
    agent = ApplianceAgent()

    def _planner_should_not_run(_input):
        raise AssertionError("planner.plan should not be called for obvious non-domain queries")

    monkeypatch.setattr(agent.planner, "plan", _planner_should_not_run)

    response = agent.handle_query(
        user_query="What is the capital of USA?",
        conversation_id="c3",
        conversation_summary="",
        session_entities={},
    )

    assert response.type == "clarification_needed"
    assert "refrigerator and dishwasher" in (response.message or "").lower()
