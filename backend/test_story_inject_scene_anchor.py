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


def _level_file(level_id: str) -> Path:
    return Path(DATA_DIR) / f"{level_id}.json"


def test_story_inject_payload_v2_infers_memory_scene_anchor_from_text():
    prior_values = {
        "DRIFT_USE_PAYLOAD_V1": os.environ.get("DRIFT_USE_PAYLOAD_V1"),
        "DRIFT_USE_PAYLOAD_V2": os.environ.get("DRIFT_USE_PAYLOAD_V2"),
        "DRIFT_V2_STRICT_MODE": os.environ.get("DRIFT_V2_STRICT_MODE"),
        "DRIFT_DEBUG_TRACE": os.environ.get("DRIFT_DEBUG_TRACE"),
        "DRIFT_FIXED_ANCHOR_X": os.environ.get("DRIFT_FIXED_ANCHOR_X"),
        "DRIFT_FIXED_ANCHOR_Y": os.environ.get("DRIFT_FIXED_ANCHOR_Y"),
        "DRIFT_FIXED_ANCHOR_Z": os.environ.get("DRIFT_FIXED_ANCHOR_Z"),
        "DRIFT_SCENE_ANCHOR": os.environ.get("DRIFT_SCENE_ANCHOR"),
        "DRIFT_SCENE_ANCHOR_MEMORY_SCENE_X": os.environ.get("DRIFT_SCENE_ANCHOR_MEMORY_SCENE_X"),
        "DRIFT_SCENE_ANCHOR_MEMORY_SCENE_Y": os.environ.get("DRIFT_SCENE_ANCHOR_MEMORY_SCENE_Y"),
        "DRIFT_SCENE_ANCHOR_MEMORY_SCENE_Z": os.environ.get("DRIFT_SCENE_ANCHOR_MEMORY_SCENE_Z"),
    }

    os.environ["DRIFT_USE_PAYLOAD_V1"] = "false"
    os.environ["DRIFT_USE_PAYLOAD_V2"] = "true"
    os.environ["DRIFT_V2_STRICT_MODE"] = "false"
    os.environ["DRIFT_DEBUG_TRACE"] = "false"
    os.environ["DRIFT_FIXED_ANCHOR_X"] = "0"
    os.environ["DRIFT_FIXED_ANCHOR_Y"] = "64"
    os.environ["DRIFT_FIXED_ANCHOR_Z"] = "0"
    os.environ.pop("DRIFT_SCENE_ANCHOR", None)
    os.environ["DRIFT_SCENE_ANCHOR_MEMORY_SCENE_X"] = "300"
    os.environ["DRIFT_SCENE_ANCHOR_MEMORY_SCENE_Y"] = "72"
    os.environ["DRIFT_SCENE_ANCHOR_MEMORY_SCENE_Z"] = "-40"

    level_id = f"flagship_scene_anchor_memory_{uuid.uuid4().hex[:8]}"
    target_file = _level_file(level_id)
    if target_file.exists():
        target_file.unlink()

    try:
        with TestClient(app) as client:
            response = client.post(
                "/story/inject",
                json={
                    "level_id": level_id,
                    "title": "scene anchor memory",
                    "text": "这是一段回忆场景，在湖边重现童年木屋",
                    "player_id": "scene_anchor_tester",
                },
            )

        assert response.status_code == 200
        body = response.json()

        assert body.get("version") == "plugin_payload_v2"
        assert body.get("payload_version") == "v2.1"
        assert body.get("anchor") == "memory_scene"

        origin = body.get("origin") or {}
        assert origin.get("base_x") == 300
        assert origin.get("base_y") == 72
        assert origin.get("base_z") == -40

        anchors = body.get("anchors") or {}
        assert sorted(anchors.keys()) == ["home", "interaction_zone", "memory_scene", "npc_zone"]

        block_ops = body.get("block_ops") or []
        assert isinstance(block_ops, list) and len(block_ops) > 0
        assert all((op.get("anchor") == "memory_scene") for op in block_ops)
        assert target_file.exists()
    finally:
        for key, old in prior_values.items():
            if old is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = old
        if target_file.exists():
            target_file.unlink()


def test_story_inject_payload_v2_explicit_anchor_overrides_inference():
    prior_values = {
        "DRIFT_USE_PAYLOAD_V1": os.environ.get("DRIFT_USE_PAYLOAD_V1"),
        "DRIFT_USE_PAYLOAD_V2": os.environ.get("DRIFT_USE_PAYLOAD_V2"),
        "DRIFT_V2_STRICT_MODE": os.environ.get("DRIFT_V2_STRICT_MODE"),
        "DRIFT_DEBUG_TRACE": os.environ.get("DRIFT_DEBUG_TRACE"),
        "DRIFT_FIXED_ANCHOR_X": os.environ.get("DRIFT_FIXED_ANCHOR_X"),
        "DRIFT_FIXED_ANCHOR_Y": os.environ.get("DRIFT_FIXED_ANCHOR_Y"),
        "DRIFT_FIXED_ANCHOR_Z": os.environ.get("DRIFT_FIXED_ANCHOR_Z"),
        "DRIFT_SCENE_ANCHOR_INTERACTION_ZONE_X": os.environ.get("DRIFT_SCENE_ANCHOR_INTERACTION_ZONE_X"),
        "DRIFT_SCENE_ANCHOR_INTERACTION_ZONE_Y": os.environ.get("DRIFT_SCENE_ANCHOR_INTERACTION_ZONE_Y"),
        "DRIFT_SCENE_ANCHOR_INTERACTION_ZONE_Z": os.environ.get("DRIFT_SCENE_ANCHOR_INTERACTION_ZONE_Z"),
    }

    os.environ["DRIFT_USE_PAYLOAD_V1"] = "false"
    os.environ["DRIFT_USE_PAYLOAD_V2"] = "true"
    os.environ["DRIFT_V2_STRICT_MODE"] = "false"
    os.environ["DRIFT_DEBUG_TRACE"] = "false"
    os.environ["DRIFT_FIXED_ANCHOR_X"] = "0"
    os.environ["DRIFT_FIXED_ANCHOR_Y"] = "64"
    os.environ["DRIFT_FIXED_ANCHOR_Z"] = "0"
    os.environ["DRIFT_SCENE_ANCHOR_INTERACTION_ZONE_X"] = "40"
    os.environ["DRIFT_SCENE_ANCHOR_INTERACTION_ZONE_Y"] = "66"
    os.environ["DRIFT_SCENE_ANCHOR_INTERACTION_ZONE_Z"] = "99"

    level_id = f"flagship_scene_anchor_override_{uuid.uuid4().hex[:8]}"
    target_file = _level_file(level_id)
    if target_file.exists():
        target_file.unlink()

    try:
        with TestClient(app) as client:
            response = client.post(
                "/story/inject",
                json={
                    "level_id": level_id,
                    "title": "scene anchor override",
                    "text": "这是一段回忆场景，理论上会被推断为memory_scene",
                    "anchor": "interaction_zone",
                    "player_id": "scene_anchor_override_tester",
                },
            )

        assert response.status_code == 200
        body = response.json()

        assert body.get("version") == "plugin_payload_v2"
        assert body.get("anchor") == "interaction_zone"

        origin = body.get("origin") or {}
        assert origin.get("base_x") == 40
        assert origin.get("base_y") == 66
        assert origin.get("base_z") == 99
        assert target_file.exists()
    finally:
        for key, old in prior_values.items():
            if old is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = old
        if target_file.exists():
            target_file.unlink()
