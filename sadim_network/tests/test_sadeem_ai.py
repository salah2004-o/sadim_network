import json
import os
import sys
from unittest.mock import patch

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("BOT_WORKER", "false")

from app import app
from app.models import ai_service


@pytest.fixture
def client():
    app.config["TESTING"] = True
    with app.test_client() as test_client:
        yield test_client


def login(client, user_id=1, role="user"):
    with client.session_transaction() as session:
        session["user_id"] = user_id
        session["role"] = role


def test_ai_allows_guest_page(client):
    response = client.get("/ai/")
    assert response.status_code == 200
    assert b"Sadeem AI" in response.data or "Sadeem AI".encode() in response.data


def test_guest_chat_not_persisted_to_db():
    with patch("app.models.ai_service._run_model", return_value={"content": "رد تجريبي", "tools": [], "provider": "gemini", "model": "x", "input_tokens": 1, "output_tokens": 1}):
        result = ai_service.guest_chat([], "ما هي شبكة سديم؟")
    assert result["content"] == "رد تجريبي"
    assert result.get("persisted") is False


def test_private_conversation_isolated(client):
    login(client, user_id=10)
    with patch("app.routes.ai._conversation", return_value=None):
        response = client.get("/ai/conversations/999")
    assert response.status_code == 404


def test_link_validation_removes_unknown_ids():
    with patch("app.models.ai_service._rows", side_effect=[[], []]):
        result = ai_service._validate_links("[كتاب غير موجود](/library/999)")
    assert result == "كتاب غير موجود"


def test_tool_results_are_json_serializable():
    value = {"price": ai_service._json(__import__("decimal").Decimal("12.50"))}
    assert json.dumps(value) == '{"price": 12.5}'
