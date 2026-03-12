from __future__ import annotations

import json
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


def test_story_inject_payload_v2_writes_trng_transaction_meta_and_debug_receipt():
    prior_values = {
        "DRIFT_USE_PAYLOAD_V1": os.environ.get("DRIFT_USE_PAYLOAD_V1"),
        "DRIFT_USE_PAYLOAD_V2": os.environ.get("DRIFT_USE_PAYLOAD_V2"),
        "DRIFT_V2_STRICT_MODE": os.environ.get("DRIFT_V2_STRICT_MODE"),
        "DRIFT_DEBUG_TRACE": os.environ.get("DRIFT_DEBUG_TRACE"),
    }

    os.environ["DRIFT_USE_PAYLOAD_V1"] = "false"
    os.environ["DRIFT_USE_PAYLOAD_V2"] = "true"
    os.environ["DRIFT_V2_STRICT_MODE"] = "false"
    os.environ["DRIFT_DEBUG_TRACE"] = "true"

    level_id = f"flagship_m5_tx_v2_{uuid.uuid4().hex[:8]}"
    target_file = _level_file(level_id)
    if target_file.exists():
        target_file.unlink()

    try:
        with TestClient(app) as client:
            response = client.post(
                "/story/inject",
                json={
                    "level_id": level_id,
                    "title": "m5 tx v2",
                    "text": "平静湖边，有轻雾与守卫",
                    "player_id": "m5_v2_tester",
                },
            )

        assert response.status_code == 200
        body = response.json()
        transaction = body.get("transaction") or {}
        assert isinstance(transaction.get("tx_id"), str) and transaction.get("tx_id")
        assert isinstance(transaction.get("committed_state_hash"), str) and transaction.get("committed_state_hash")
        assert isinstance(transaction.get("committed_graph_hash"), str) and transaction.get("committed_graph_hash")
        assert int(transaction.get("event_count") or 0) >= 1

        level_doc = json.loads(target_file.read_text(encoding="utf-8"))
        tx_meta = ((level_doc.get("meta") or {}).get("trng_transaction") or {})
        assert tx_meta.get("tx_id") == transaction.get("tx_id")
        assert tx_meta.get("committed_state_hash") == transaction.get("committed_state_hash")
        assert tx_meta.get("committed_graph_hash") == transaction.get("committed_graph_hash")
    finally:
        for key, old in prior_values.items():
            if old is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = old
        if target_file.exists():
            target_file.unlink()


def test_story_inject_payload_v1_writes_trng_transaction_meta_without_debug_leak():
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

    level_id = f"flagship_m5_tx_v1_{uuid.uuid4().hex[:8]}"
    target_file = _level_file(level_id)
    if target_file.exists():
        target_file.unlink()

    try:
        with TestClient(app) as client:
            response = client.post(
                "/story/inject",
                json={
                    "level_id": level_id,
                    "title": "m5 tx v1",
                    "text": "平静夜晚的湖边，有一座木屋",
                    "player_id": "m5_v1_tester",
                },
            )

        assert response.status_code == 200
        body = response.json()
        assert "transaction" not in body

        level_doc = json.loads(target_file.read_text(encoding="utf-8"))
        tx_meta = ((level_doc.get("meta") or {}).get("trng_transaction") or {})
        assert isinstance(tx_meta.get("tx_id"), str) and tx_meta.get("tx_id")
        assert isinstance(tx_meta.get("committed_state_hash"), str) and tx_meta.get("committed_state_hash")
        assert isinstance(tx_meta.get("committed_graph_hash"), str) and tx_meta.get("committed_graph_hash")
        assert int(tx_meta.get("event_count") or 0) >= 1
    finally:
        for key, old in prior_values.items():
            if old is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = old
        if target_file.exists():
            target_file.unlink()
