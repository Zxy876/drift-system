from __future__ import annotations

import sys
import uuid
from pathlib import Path

from fastapi.testclient import TestClient

BACKEND_ROOT = Path(__file__).resolve().parent
PARENT_ROOT = BACKEND_ROOT.parent
for candidate in (str(BACKEND_ROOT), str(PARENT_ROOT)):
    if candidate not in sys.path:
        sys.path.insert(0, candidate)

from app.main import app


def test_intent_parse_endpoint_returns_intent_list():
    with TestClient(app) as client:
        response = client.post(
            "/intent/parse",
            json={
                "player_id": f"intent_parse_{uuid.uuid4().hex[:8]}",
                "text": "创建剧情 shrine",
            },
        )

    assert response.status_code == 200
    body = response.json()
    assert body.get("status") == "ok"
    assert isinstance(body.get("intents"), list)
    assert len(body.get("intents") or []) > 0
    first = body.get("intent") or {}
    assert isinstance(first, dict)
    assert isinstance(first.get("type"), str) and first.get("type")


def test_intent_parse_supports_poetry_scene_intent(monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)

    with TestClient(app) as client:
        response = client.post(
            "/intent/parse",
            json={
                "player_id": f"intent_poetry_{uuid.uuid4().hex[:8]}",
                "text": "/poem 月光沿着风声落下",
            },
        )

    assert response.status_code == 200
    body = response.json()
    assert body.get("status") == "ok"
    first = body.get("intent") or {}
    assert first.get("type") == "CREATE_POETRY_SCENE"
    assert str(first.get("raw_text") or "").strip() == "月光沿着风声落下"


def test_intent_event_endpoint_bridges_to_rule_event_with_registry_preview():
    player_id = f"intent_event_{uuid.uuid4().hex[:8]}"

    with TestClient(app) as client:
        upsert = client.post(
            "/registry/player-tags",
            json={
                "player": player_id,
                "tag": "shrine",
                "resource": "minecraft:lantern",
            },
        )
        assert upsert.status_code == 200

        response = client.post(
            "/intent/event",
            json={
                "player_id": player_id,
                "event_type": "chat",
                "message": "生成 shrine",
            },
        )

    assert response.status_code == 200
    body = response.json()
    assert body.get("status") == "ok"
    assert isinstance(body.get("player_input"), dict)
    assert body.get("player_input", {}).get("text") == "生成 shrine"
    assert body.get("intent_received") is True
    assert isinstance(body.get("registry_resources"), dict)


def test_intent_event_accepts_content_field_in_payload():
    player_id = f"intent_content_{uuid.uuid4().hex[:8]}"

    with TestClient(app) as client:
        response = client.post(
            "/intent/event",
            json={
                "player_id": player_id,
                "event_type": "chat",
                "payload": {
                    "content": "生成 shrine",
                },
            },
        )

    assert response.status_code == 200
    body = response.json()
    assert body.get("status") == "ok"
    assert isinstance(body.get("player_input"), dict)
    assert body.get("player_input", {}).get("text") == "生成 shrine"
