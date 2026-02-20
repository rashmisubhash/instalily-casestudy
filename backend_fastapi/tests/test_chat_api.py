from fastapi.testclient import TestClient

from app.agent.models import AgentResponse
from app.main import app
import app.main as main_module


def test_chat_endpoint_happy_path(monkeypatch):
    client = TestClient(app)

    def fake_handle_query(**kwargs):
        return AgentResponse(
            type="part_lookup",
            confidence=0.85,
            requires_clarification=False,
            explanation="This part installs in a few steps.",
            helpful_tips=["Disconnect power first."],
        )

    monkeypatch.setattr(main_module.agent, "handle_query", fake_handle_query)

    response = client.post(
        "/chat",
        json={"conversation_id": "test-conv-1", "message": "How can I install PS11752778?"},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["conversation_id"]
    assert payload["response"]["type"] == "part_lookup"
    assert payload["response"]["confidence"] == 0.85


def test_chat_endpoint_returns_500_on_agent_error(monkeypatch):
    client = TestClient(app)

    def fake_handle_query(**kwargs):
        raise RuntimeError("Injected failure")

    monkeypatch.setattr(main_module.agent, "handle_query", fake_handle_query)

    response = client.post(
        "/chat",
        json={"conversation_id": "test-conv-2", "message": "help"},
    )

    assert response.status_code == 500
    assert "Injected failure" in response.json()["detail"]
