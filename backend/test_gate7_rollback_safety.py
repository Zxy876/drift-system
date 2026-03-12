from __future__ import annotations

import os
import sys
import uuid
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient

BACKEND_ROOT = Path(__file__).resolve().parent
PARENT_ROOT = BACKEND_ROOT.parent
for candidate in (str(BACKEND_ROOT), str(PARENT_ROOT)):
    if candidate not in sys.path:
        sys.path.insert(0, candidate)

from app.main import app
from app.api.story_api import DATA_DIR
from app.core.executor.executor_v1 import execute_payload_v1
from app.core.executor.replay_v1 import replay_payload_v1


PROMPT = "平静夜晚的湖边，有一座7x5木屋，门朝南，开两扇窗"


def _level_file(level_id: str) -> Path:
    return Path(DATA_DIR) / f"{level_id}.json"


def test_gate7_payload_v2_off_returns_payload_v1_and_bypasses_v2_builder():
    prior_values = {
        "DRIFT_USE_PAYLOAD_V1": os.environ.get("DRIFT_USE_PAYLOAD_V1"),
        "DRIFT_USE_PAYLOAD_V2": os.environ.get("DRIFT_USE_PAYLOAD_V2"),
        "DRIFT_USE_V2_MAPPER": os.environ.get("DRIFT_USE_V2_MAPPER"),
        "DRIFT_V2_STRICT_MODE": os.environ.get("DRIFT_V2_STRICT_MODE"),
        "DRIFT_DEBUG_TRACE": os.environ.get("DRIFT_DEBUG_TRACE"),
    }

    os.environ["DRIFT_USE_PAYLOAD_V1"] = "true"
    os.environ["DRIFT_USE_PAYLOAD_V2"] = "false"
    os.environ["DRIFT_USE_V2_MAPPER"] = "false"
    os.environ["DRIFT_V2_STRICT_MODE"] = "false"
    os.environ["DRIFT_DEBUG_TRACE"] = "false"

    level_id = f"flagship_gate7_v2off_{uuid.uuid4().hex[:8]}"
    target_file = _level_file(level_id)
    if target_file.exists():
        target_file.unlink()

    try:
        with patch("app.api.story_api._build_payload_v2_for_inject", side_effect=AssertionError("v2 builder should not be called when DRIFT_USE_PAYLOAD_V2=false")):
            with TestClient(app) as client:
                response = client.post(
                    "/story/inject",
                    json={
                        "level_id": level_id,
                        "title": "gate7 rollback",
                        "text": PROMPT,
                        "player_id": "gate7_tester",
                    },
                )

        assert response.status_code == 200
        body = response.json()
        assert body.get("version") == "plugin_payload_v1"
        assert isinstance((body.get("hash") or {}).get("merged_blocks"), str)
        assert "final_commands_hash_v2" not in body
        assert target_file.exists()
    finally:
        for key, old in prior_values.items():
            if old is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = old
        if target_file.exists():
            target_file.unlink()


def test_gate7_executor_and_replay_v1_still_pass_when_v2_off():
    prior_values = {
        "DRIFT_USE_PAYLOAD_V1": os.environ.get("DRIFT_USE_PAYLOAD_V1"),
        "DRIFT_USE_PAYLOAD_V2": os.environ.get("DRIFT_USE_PAYLOAD_V2"),
        "DRIFT_USE_V2_MAPPER": os.environ.get("DRIFT_USE_V2_MAPPER"),
        "DRIFT_V2_STRICT_MODE": os.environ.get("DRIFT_V2_STRICT_MODE"),
        "DRIFT_DEBUG_TRACE": os.environ.get("DRIFT_DEBUG_TRACE"),
    }

    os.environ["DRIFT_USE_PAYLOAD_V1"] = "true"
    os.environ["DRIFT_USE_PAYLOAD_V2"] = "false"
    os.environ["DRIFT_USE_V2_MAPPER"] = "false"
    os.environ["DRIFT_V2_STRICT_MODE"] = "false"
    os.environ["DRIFT_DEBUG_TRACE"] = "false"

    level_id = f"flagship_gate7_exec_{uuid.uuid4().hex[:8]}"
    target_file = _level_file(level_id)
    if target_file.exists():
        target_file.unlink()

    try:
        with TestClient(app) as client:
            response = client.post(
                "/story/inject",
                json={
                    "level_id": level_id,
                    "title": "gate7 executor replay",
                    "text": PROMPT,
                    "player_id": "gate7_exec_tester",
                },
            )

        assert response.status_code == 200
        payload = response.json()
        assert payload.get("version") == "plugin_payload_v1"

        exec_result = execute_payload_v1(payload)
        replay_result = replay_payload_v1(payload)

        assert exec_result.get("status") == "SUCCESS"
        assert exec_result.get("failure_code") == "NONE"
        assert replay_result.get("status") == "SUCCESS"
        assert replay_result.get("failure_code") == "NONE"
    finally:
        for key, old in prior_values.items():
            if old is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = old
        if target_file.exists():
            target_file.unlink()
