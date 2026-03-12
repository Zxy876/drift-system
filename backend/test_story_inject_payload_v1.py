from __future__ import annotations

import os
import sys
import uuid
import json
from pathlib import Path

from fastapi.testclient import TestClient

BACKEND_ROOT = Path(__file__).resolve().parent
PARENT_ROOT = BACKEND_ROOT.parent
for candidate in (str(BACKEND_ROOT), str(PARENT_ROOT)):
    if candidate not in sys.path:
        sys.path.insert(0, candidate)

from app.main import app


def _validate_required_by_schema(value, schema):
    if not isinstance(schema, dict):
        return

    expected_type = schema.get("type")
    if expected_type == "object":
        assert isinstance(value, dict), f"expected object, got {type(value)}"
        required = schema.get("required") or []
        for key in required:
            assert key in value, f"missing required key: {key}"

        properties = schema.get("properties") or {}
        for key, child_schema in properties.items():
            if key in value:
                _validate_required_by_schema(value[key], child_schema)

    elif expected_type == "array":
        assert isinstance(value, list), f"expected array, got {type(value)}"
        item_schema = schema.get("items")
        if item_schema:
            for item in value:
                _validate_required_by_schema(item, item_schema)


def test_story_inject_returns_plugin_payload_v1_when_flag_enabled():
    schema_path = BACKEND_ROOT / "app" / "core" / "executor" / "plugin_payload_schema_v1.json"
    schema = __import__("json").loads(schema_path.read_text(encoding="utf-8"))

    prior_values = {
        "DRIFT_USE_PAYLOAD_V1": os.environ.get("DRIFT_USE_PAYLOAD_V1"),
        "DRIFT_FIXED_ANCHOR_X": os.environ.get("DRIFT_FIXED_ANCHOR_X"),
        "DRIFT_FIXED_ANCHOR_Y": os.environ.get("DRIFT_FIXED_ANCHOR_Y"),
        "DRIFT_FIXED_ANCHOR_Z": os.environ.get("DRIFT_FIXED_ANCHOR_Z"),
    }

    os.environ["DRIFT_USE_PAYLOAD_V1"] = "true"
    os.environ["DRIFT_FIXED_ANCHOR_X"] = "0"
    os.environ["DRIFT_FIXED_ANCHOR_Y"] = "64"
    os.environ["DRIFT_FIXED_ANCHOR_Z"] = "0"

    try:
        level_id = f"flagship_payload_v1_inject_test_{uuid.uuid4().hex[:8]}"
        with TestClient(app) as client:
            response = client.post(
                "/story/inject",
                json={
                    "level_id": level_id,
                    "title": "payload_v1 wiring",
                    "text": "平静夜晚的湖边，有一座木屋，门朝南",
                    "player_id": "payload_wiring_tester",
                },
            )

        assert response.status_code == 200
        body = response.json()

        assert body.get("version") == "plugin_payload_v1"
        assert isinstance(body.get("commands"), list)
        assert len(body.get("commands") or []) > 0
        assert isinstance(body.get("build_id"), str) and body.get("build_id")
        assert isinstance((body.get("hash") or {}).get("merged_blocks"), str)

        _validate_required_by_schema(body, schema)
    finally:
        for key, old in prior_values.items():
            if old is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = old


def test_story_inject_uses_v2_mapper_when_feature_flag_enabled():
    schema_path = BACKEND_ROOT / "app" / "core" / "executor" / "plugin_payload_schema_v1.json"
    schema = __import__("json").loads(schema_path.read_text(encoding="utf-8"))

    prior_values = {
        "DRIFT_USE_PAYLOAD_V1": os.environ.get("DRIFT_USE_PAYLOAD_V1"),
        "DRIFT_USE_V2_MAPPER": os.environ.get("DRIFT_USE_V2_MAPPER"),
        "DRIFT_V2_STRICT_MODE": os.environ.get("DRIFT_V2_STRICT_MODE"),
        "DRIFT_FIXED_ANCHOR_X": os.environ.get("DRIFT_FIXED_ANCHOR_X"),
        "DRIFT_FIXED_ANCHOR_Y": os.environ.get("DRIFT_FIXED_ANCHOR_Y"),
        "DRIFT_FIXED_ANCHOR_Z": os.environ.get("DRIFT_FIXED_ANCHOR_Z"),
    }

    os.environ["DRIFT_USE_PAYLOAD_V1"] = "true"
    os.environ["DRIFT_USE_V2_MAPPER"] = "true"
    os.environ["DRIFT_V2_STRICT_MODE"] = "false"
    os.environ["DRIFT_FIXED_ANCHOR_X"] = "0"
    os.environ["DRIFT_FIXED_ANCHOR_Y"] = "64"
    os.environ["DRIFT_FIXED_ANCHOR_Z"] = "0"

    try:
        level_id = f"flagship_payload_v1_v2_mapper_test_{uuid.uuid4().hex[:8]}"
        with TestClient(app) as client:
            response = client.post(
                "/story/inject",
                json={
                    "level_id": level_id,
                    "title": "payload_v1 v2 mapper wiring",
                    "text": "平静夜晚的湖边，有一座木屋，门朝南",
                    "player_id": "payload_v2_mapper_tester",
                },
            )

        assert response.status_code == 200
        body = response.json()

        assert body.get("version") == "plugin_payload_v1"
        assert body.get("scene_path") == "decision_mapper_v2"
        assert isinstance(body.get("commands"), list)
        assert len(body.get("commands") or []) > 0

        _validate_required_by_schema(body, schema)
    finally:
        for key, old in prior_values.items():
            if old is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = old


def test_story_inject_debug_trace_response_only_when_enabled():
    prior_values = {
        "DRIFT_USE_PAYLOAD_V1": os.environ.get("DRIFT_USE_PAYLOAD_V1"),
        "DRIFT_USE_V2_MAPPER": os.environ.get("DRIFT_USE_V2_MAPPER"),
        "DRIFT_V2_STRICT_MODE": os.environ.get("DRIFT_V2_STRICT_MODE"),
        "DRIFT_DEBUG_TRACE": os.environ.get("DRIFT_DEBUG_TRACE"),
        "DRIFT_FIXED_ANCHOR_X": os.environ.get("DRIFT_FIXED_ANCHOR_X"),
        "DRIFT_FIXED_ANCHOR_Y": os.environ.get("DRIFT_FIXED_ANCHOR_Y"),
        "DRIFT_FIXED_ANCHOR_Z": os.environ.get("DRIFT_FIXED_ANCHOR_Z"),
    }

    os.environ["DRIFT_USE_PAYLOAD_V1"] = "true"
    os.environ["DRIFT_USE_V2_MAPPER"] = "true"
    os.environ["DRIFT_V2_STRICT_MODE"] = "false"
    os.environ["DRIFT_DEBUG_TRACE"] = "true"
    os.environ["DRIFT_FIXED_ANCHOR_X"] = "0"
    os.environ["DRIFT_FIXED_ANCHOR_Y"] = "64"
    os.environ["DRIFT_FIXED_ANCHOR_Z"] = "0"

    try:
        level_id = f"flagship_payload_v1_debug_trace_test_{uuid.uuid4().hex[:8]}"
        with TestClient(app) as client:
            response = client.post(
                "/story/inject",
                json={
                    "level_id": level_id,
                    "title": "payload_v1 debug trace",
                    "text": "lake scene with mysterious fog and low music",
                    "player_id": "payload_debug_tester",
                },
            )

        assert response.status_code == 200
        body = response.json()

        assert body.get("mapping_status") == "OK"
        assert body.get("mapping_failure_code") == "NONE"
        assert body.get("degrade_reason") is None
        assert "decision_trace" in body
        assert body.get("lost_semantics") == ["sound.low_music"]

        decisions = (body.get("decision_trace") or {}).get("mapper_decisions") or []
        fog_decision = next((item for item in decisions if isinstance(item, dict) and item.get("rule_id") == "PROJECTION_ATMOSPHERE_FOG_V1"), None)
        assert fog_decision is not None
        assert int(fog_decision.get("projection_blocks_added") or 0) > 0

        file_path = body.get("file")
        assert isinstance(file_path, str) and file_path

        level_doc = json.loads(Path(file_path).read_text(encoding="utf-8"))
        assert "mapping_status" not in level_doc
        assert "decision_trace" not in level_doc
        assert "lost_semantics" not in level_doc

        bootstrap = level_doc.get("bootstrap_patch") or {}
        world_patch = level_doc.get("world_patch") or {}
        assert "decision_trace" not in bootstrap
        assert "decision_trace" not in world_patch
        assert "mapping_status" not in bootstrap
        assert "mapping_status" not in world_patch
    finally:
        for key, old in prior_values.items():
            if old is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = old


def test_story_inject_strict_mode_with_debug_returns_422_with_debug_fields():
    prior_values = {
        "DRIFT_USE_PAYLOAD_V1": os.environ.get("DRIFT_USE_PAYLOAD_V1"),
        "DRIFT_USE_V2_MAPPER": os.environ.get("DRIFT_USE_V2_MAPPER"),
        "DRIFT_V2_STRICT_MODE": os.environ.get("DRIFT_V2_STRICT_MODE"),
        "DRIFT_DEBUG_TRACE": os.environ.get("DRIFT_DEBUG_TRACE"),
    }

    os.environ["DRIFT_USE_PAYLOAD_V1"] = "true"
    os.environ["DRIFT_USE_V2_MAPPER"] = "true"
    os.environ["DRIFT_V2_STRICT_MODE"] = "true"
    os.environ["DRIFT_DEBUG_TRACE"] = "true"

    try:
        with TestClient(app) as client:
            response = client.post(
                "/story/inject",
                json={
                    "level_id": f"flagship_payload_v1_strict_debug_{uuid.uuid4().hex[:8]}",
                    "title": "strict debug trace",
                    "text": "在湖边制造一个神秘雾气与低沉音乐的场景",
                    "player_id": "strict_debug_tester",
                },
            )

        assert response.status_code == 422
        body = response.json()

        assert "EXEC_CAPABILITY_GAP" in (body.get("detail") or "")
        assert body.get("mapping_status") == "REJECTED"
        assert body.get("mapping_failure_code") == "EXEC_CAPABILITY_GAP"
        assert "degrade_reason" in body
        assert "lost_semantics" in body
        assert body.get("compose_path") == "scene_orchestrator_v2"

        decision_trace = body.get("decision_trace") or {}
        decisions = decision_trace.get("mapper_decisions") or []
        semantics = {item.get("semantic") for item in decisions if isinstance(item, dict)}
        assert "sound.low_music" in semantics
    finally:
        for key, old in prior_values.items():
            if old is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = old


def test_story_inject_strict_mode_without_debug_returns_422_without_debug_fields():
    prior_values = {
        "DRIFT_USE_PAYLOAD_V1": os.environ.get("DRIFT_USE_PAYLOAD_V1"),
        "DRIFT_USE_V2_MAPPER": os.environ.get("DRIFT_USE_V2_MAPPER"),
        "DRIFT_V2_STRICT_MODE": os.environ.get("DRIFT_V2_STRICT_MODE"),
        "DRIFT_DEBUG_TRACE": os.environ.get("DRIFT_DEBUG_TRACE"),
    }

    os.environ["DRIFT_USE_PAYLOAD_V1"] = "true"
    os.environ["DRIFT_USE_V2_MAPPER"] = "true"
    os.environ["DRIFT_V2_STRICT_MODE"] = "true"
    os.environ["DRIFT_DEBUG_TRACE"] = "false"

    try:
        with TestClient(app) as client:
            response = client.post(
                "/story/inject",
                json={
                    "level_id": f"flagship_payload_v1_strict_nodbg_{uuid.uuid4().hex[:8]}",
                    "title": "strict no debug trace",
                    "text": "在湖边制造一个神秘雾气与低沉音乐的场景",
                    "player_id": "strict_nodbg_tester",
                },
            )

        assert response.status_code == 422
        body = response.json()
        assert "EXEC_CAPABILITY_GAP" in (body.get("detail") or "")
        for key in (
            "mapping_status",
            "mapping_failure_code",
            "degrade_reason",
            "lost_semantics",
            "decision_trace",
            "compose_path",
        ):
            assert key not in body
    finally:
        for key, old in prior_values.items():
            if old is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = old
