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


def test_world_story_rule_event_ingests_collect_into_trng_when_debug_enabled():
    prior_values = {
        "DRIFT_ENABLE_PLUGIN_TRNG": os.environ.get("DRIFT_ENABLE_PLUGIN_TRNG"),
        "DRIFT_DEBUG_TRACE": os.environ.get("DRIFT_DEBUG_TRACE"),
    }

    os.environ["DRIFT_ENABLE_PLUGIN_TRNG"] = "true"
    os.environ["DRIFT_DEBUG_TRACE"] = "true"

    player_id = f"m6_collect_{uuid.uuid4().hex[:8]}"

    try:
        with TestClient(app) as client:
            response = client.post(
                "/world/story/rule-event",
                json={
                    "player_id": player_id,
                    "event_type": "collect",
                    "payload": {
                        "item_type": "oak_log",
                        "amount": 3,
                        "location": {"x": 10, "y": 65, "z": -3},
                    },
                },
            )

        assert response.status_code == 200
        body = response.json()
        assert body.get("status") == "ok"

        tx = body.get("interaction_transaction") or {}
        assert isinstance(tx.get("tx_id"), str) and tx.get("tx_id")
        assert tx.get("event_count") == 1
        assert isinstance(tx.get("committed_state_hash"), str) and tx.get("committed_state_hash")
        assert isinstance(tx.get("committed_graph_hash"), str) and tx.get("committed_graph_hash")

        interaction_event = tx.get("interaction_event") or {}
        assert interaction_event.get("type") == "collect"
        assert (interaction_event.get("data") or {}).get("item_type") == "oak_log"
        assert (interaction_event.get("data") or {}).get("resource") == "oak_log"
        assert (interaction_event.get("anchor") or {}).get("base_x") == 10
        assert (interaction_event.get("anchor") or {}).get("base_y") == 65
        assert (interaction_event.get("anchor") or {}).get("base_z") == -3
    finally:
        for key, old in prior_values.items():
            if old is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = old


def test_world_story_rule_event_hides_transaction_trace_when_debug_disabled():
    prior_values = {
        "DRIFT_ENABLE_PLUGIN_TRNG": os.environ.get("DRIFT_ENABLE_PLUGIN_TRNG"),
        "DRIFT_DEBUG_TRACE": os.environ.get("DRIFT_DEBUG_TRACE"),
    }

    os.environ["DRIFT_ENABLE_PLUGIN_TRNG"] = "true"
    os.environ["DRIFT_DEBUG_TRACE"] = "false"

    player_id = f"m6_talk_{uuid.uuid4().hex[:8]}"

    try:
        with TestClient(app) as client:
            response = client.post(
                "/world/story/rule-event",
                json={
                    "player_id": player_id,
                    "event_type": "chat",
                    "payload": {
                        "text": "你好，向导",
                    },
                },
            )

        assert response.status_code == 200
        body = response.json()
        assert body.get("status") == "ok"
        assert "interaction_transaction" not in body
        assert "interaction_transaction_error" not in body
    finally:
        for key, old in prior_values.items():
            if old is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = old


def test_world_story_rule_event_ingests_npc_talk_into_trng_talk_type():
    prior_values = {
        "DRIFT_ENABLE_PLUGIN_TRNG": os.environ.get("DRIFT_ENABLE_PLUGIN_TRNG"),
        "DRIFT_DEBUG_TRACE": os.environ.get("DRIFT_DEBUG_TRACE"),
    }

    os.environ["DRIFT_ENABLE_PLUGIN_TRNG"] = "true"
    os.environ["DRIFT_DEBUG_TRACE"] = "true"

    player_id = f"m6_npc_talk_{uuid.uuid4().hex[:8]}"

    try:
        with TestClient(app) as client:
            response = client.post(
                "/world/story/rule-event",
                json={
                    "player_id": player_id,
                    "event_type": "npc_talk",
                    "payload": {
                        "npc_id": "wanderer_01",
                        "npc_name": "阿无",
                        "interaction": "right_click",
                        "location": {"x": -183, "y": 70, "z": -161},
                    },
                },
            )

        assert response.status_code == 200
        body = response.json()
        assert body.get("status") == "ok"

        tx = body.get("interaction_transaction") or {}
        interaction_event = tx.get("interaction_event") or {}
        assert interaction_event.get("type") == "talk"
        assert interaction_event.get("npc_id") == "wanderer_01"
        assert (interaction_event.get("data") or {}).get("event_type") == "npc_talk"
        assert (interaction_event.get("data") or {}).get("npc_id") == "wanderer_01"
    finally:
        for key, old in prior_values.items():
            if old is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = old


def test_world_story_rule_event_ingests_npc_trigger_with_trigger_key():
    prior_values = {
        "DRIFT_ENABLE_PLUGIN_TRNG": os.environ.get("DRIFT_ENABLE_PLUGIN_TRNG"),
        "DRIFT_DEBUG_TRACE": os.environ.get("DRIFT_DEBUG_TRACE"),
    }

    os.environ["DRIFT_ENABLE_PLUGIN_TRNG"] = "true"
    os.environ["DRIFT_DEBUG_TRACE"] = "true"

    player_id = f"m6_npc_trigger_{uuid.uuid4().hex[:8]}"

    try:
        with TestClient(app) as client:
            response = client.post(
                "/world/story/rule-event",
                json={
                    "player_id": player_id,
                    "event_type": "npc_trigger",
                    "payload": {
                        "trigger": "npc_trade_blacksmith",
                        "npc_id": "blacksmith",
                        "location": {"x": 4, "y": 66, "z": 12},
                    },
                },
            )

        assert response.status_code == 200
        body = response.json()
        assert body.get("status") == "ok"

        tx = body.get("interaction_transaction") or {}
        interaction_event = tx.get("interaction_event") or {}
        assert interaction_event.get("type") == "trigger"
        assert interaction_event.get("npc_id") == "blacksmith"
        assert (interaction_event.get("data") or {}).get("trigger") == "npc_trade_blacksmith"
        assert (interaction_event.get("data") or {}).get("event_type") == "npc_trigger"
        assert (interaction_event.get("anchor") or {}).get("base_x") == 4
        assert (interaction_event.get("anchor") or {}).get("base_y") == 66
        assert (interaction_event.get("anchor") or {}).get("base_z") == 12
    finally:
        for key, old in prior_values.items():
            if old is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = old
