from __future__ import annotations

import os
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
from app.api.story_api import DATA_DIR


STRICT_PROMPT = "在湖边制造一个神秘雾气与低沉音乐的场景"


def _level_file(level_id: str) -> Path:
    return Path(DATA_DIR) / f"{level_id}.json"


def test_gate4_strict_422_has_zero_side_effect_and_complete_trace():
    prior_values = {
        "DRIFT_USE_PAYLOAD_V1": os.environ.get("DRIFT_USE_PAYLOAD_V1"),
        "DRIFT_USE_PAYLOAD_V2": os.environ.get("DRIFT_USE_PAYLOAD_V2"),
        "DRIFT_V2_STRICT_MODE": os.environ.get("DRIFT_V2_STRICT_MODE"),
        "DRIFT_DEBUG_TRACE": os.environ.get("DRIFT_DEBUG_TRACE"),
    }

    os.environ["DRIFT_USE_PAYLOAD_V1"] = "false"
    os.environ["DRIFT_USE_PAYLOAD_V2"] = "true"
    os.environ["DRIFT_V2_STRICT_MODE"] = "true"
    os.environ["DRIFT_DEBUG_TRACE"] = "true"

    level_id = f"flagship_payload_v2_gate4_strict_{uuid.uuid4().hex[:8]}"
    target_file = _level_file(level_id)
    if target_file.exists():
        target_file.unlink()

    try:
        with TestClient(app) as client:
            response = client.post(
                "/story/inject",
                json={
                    "level_id": level_id,
                    "title": "gate4 strict integrity",
                    "text": STRICT_PROMPT,
                    "player_id": "gate4_strict_tester",
                },
            )

        assert response.status_code == 422
        body = response.json()

        assert "payload_v2_build_failed" in (body.get("detail") or "")
        assert "EXEC_CAPABILITY_GAP" in (body.get("detail") or "")

        assert body.get("mapping_failure_code") == "EXEC_CAPABILITY_GAP"
        assert isinstance(body.get("lost_semantics"), list)
        assert "sound.low_music" in (body.get("lost_semantics") or [])

        assert isinstance(body.get("rule_version"), str) and body.get("rule_version")
        assert isinstance(body.get("engine_version"), str) and body.get("engine_version")
        assert isinstance(body.get("decision_trace"), dict)

        for forbidden_key in ("hash", "final_commands_hash_v2", "world_patch", "file", "version", "commands"):
            assert forbidden_key not in body

        assert not target_file.exists()
    finally:
        for key, old in prior_values.items():
            if old is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = old
        if target_file.exists():
            target_file.unlink()


def test_gate4_strict_without_debug_hides_trace_fields():
    prior_values = {
        "DRIFT_USE_PAYLOAD_V1": os.environ.get("DRIFT_USE_PAYLOAD_V1"),
        "DRIFT_USE_PAYLOAD_V2": os.environ.get("DRIFT_USE_PAYLOAD_V2"),
        "DRIFT_V2_STRICT_MODE": os.environ.get("DRIFT_V2_STRICT_MODE"),
        "DRIFT_DEBUG_TRACE": os.environ.get("DRIFT_DEBUG_TRACE"),
    }

    os.environ["DRIFT_USE_PAYLOAD_V1"] = "false"
    os.environ["DRIFT_USE_PAYLOAD_V2"] = "true"
    os.environ["DRIFT_V2_STRICT_MODE"] = "true"
    os.environ["DRIFT_DEBUG_TRACE"] = "false"

    level_id = f"flagship_payload_v2_gate4_nodbg_{uuid.uuid4().hex[:8]}"
    target_file = _level_file(level_id)
    if target_file.exists():
        target_file.unlink()

    try:
        with TestClient(app) as client:
            response = client.post(
                "/story/inject",
                json={
                    "level_id": level_id,
                    "title": "gate4 strict no debug",
                    "text": STRICT_PROMPT,
                    "player_id": "gate4_nodbg_tester",
                },
            )

        assert response.status_code == 422
        body = response.json()
        for debug_key in (
            "mapping_status",
            "mapping_failure_code",
            "degrade_reason",
            "lost_semantics",
            "rule_version",
            "engine_version",
            "decision_trace",
            "compose_path",
        ):
            assert debug_key not in body

        assert not target_file.exists()
    finally:
        for key, old in prior_values.items():
            if old is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = old
        if target_file.exists():
            target_file.unlink()


def test_gate4_default_does_not_pollute_strict_behavior():
    prior_values = {
        "DRIFT_USE_PAYLOAD_V1": os.environ.get("DRIFT_USE_PAYLOAD_V1"),
        "DRIFT_USE_PAYLOAD_V2": os.environ.get("DRIFT_USE_PAYLOAD_V2"),
        "DRIFT_V2_STRICT_MODE": os.environ.get("DRIFT_V2_STRICT_MODE"),
        "DRIFT_DEBUG_TRACE": os.environ.get("DRIFT_DEBUG_TRACE"),
    }

    os.environ["DRIFT_USE_PAYLOAD_V1"] = "false"
    os.environ["DRIFT_USE_PAYLOAD_V2"] = "true"
    os.environ["DRIFT_DEBUG_TRACE"] = "true"

    default_level_id = f"flagship_payload_v2_gate4_default_{uuid.uuid4().hex[:8]}"
    strict_level_id = f"flagship_payload_v2_gate4_strict2_{uuid.uuid4().hex[:8]}"
    default_file = _level_file(default_level_id)
    strict_file = _level_file(strict_level_id)
    for path in (default_file, strict_file):
        if path.exists():
            path.unlink()

    try:
        os.environ["DRIFT_V2_STRICT_MODE"] = "false"
        with TestClient(app) as client:
            default_response = client.post(
                "/story/inject",
                json={
                    "level_id": default_level_id,
                    "title": "gate4 default",
                    "text": STRICT_PROMPT,
                    "player_id": "gate4_default_tester",
                },
            )

        assert default_response.status_code == 200
        default_body = default_response.json()
        assert default_body.get("version") == "plugin_payload_v2"
        assert isinstance((default_body.get("hash") or {}).get("final_commands"), str)
        assert default_file.exists()

        os.environ["DRIFT_V2_STRICT_MODE"] = "true"
        with TestClient(app) as client:
            strict_response = client.post(
                "/story/inject",
                json={
                    "level_id": strict_level_id,
                    "title": "gate4 strict",
                    "text": STRICT_PROMPT,
                    "player_id": "gate4_strict_tester_2",
                },
            )

        assert strict_response.status_code == 422
        strict_body = strict_response.json()
        assert "EXEC_CAPABILITY_GAP" in (strict_body.get("detail") or "")
        assert "final_commands_hash_v2" not in strict_body
        assert not strict_file.exists()
    finally:
        for key, old in prior_values.items():
            if old is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = old
        for path in (default_file, strict_file):
            if path.exists():
                path.unlink()
