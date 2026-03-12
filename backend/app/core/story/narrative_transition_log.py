from __future__ import annotations

import json
import os
import re
import threading
import time
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

from app.core.story.story_loader import BACKEND_DIR


DEFAULT_NARRATIVE_TRANSITION_DIR = os.path.join(BACKEND_DIR, "data", "narrative_transitions")


def _normalize_token(value: Any) -> str:
    token = str(value or "").strip().lower()
    if not token:
        return ""
    return token.replace("-", "_").replace(" ", "_").strip("_")


def _safe_int(value: Any, default: int = 0) -> int:
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return int(default)


def _safe_player_filename(player_id: str) -> str:
    normalized = _normalize_token(player_id)
    if not normalized:
        normalized = "default"
    sanitized = re.sub(r"[^a-z0-9_]+", "_", normalized)
    return f"{sanitized}.json"


@dataclass
class NarrativeTransitionLogEntry:
    player_id: str
    from_node: str | None
    transition_id: str
    to_node: str
    reason: str
    input_snapshot: Dict[str, Any]
    created_at_ms: int

    def to_dict(self) -> Dict[str, Any]:
        return {
            "player_id": str(self.player_id or "default"),
            "from_node": _normalize_token(self.from_node),
            "transition_id": _normalize_token(self.transition_id),
            "to_node": _normalize_token(self.to_node),
            "reason": str(self.reason or ""),
            "input_snapshot": dict(self.input_snapshot or {}),
            "created_at_ms": _safe_int(self.created_at_ms, int(time.time() * 1000)),
        }


class NarrativeTransitionLogStore:
    def __init__(self, base_dir: str | None = None) -> None:
        configured = str(os.environ.get("DRIFT_NARRATIVE_TRANSITION_DIR") or "").strip()
        self.base_dir = os.path.abspath(str(base_dir or configured or DEFAULT_NARRATIVE_TRANSITION_DIR))
        self._lock = threading.RLock()

    def _file_path_for_player(self, player_id: str) -> str:
        return os.path.join(self.base_dir, _safe_player_filename(player_id))

    def _read_player_doc(self, player_id: str) -> Dict[str, Any]:
        file_path = self._file_path_for_player(player_id)
        if not os.path.exists(file_path):
            return {
                "player_id": str(player_id or "default"),
                "transitions": [],
            }

        try:
            with open(file_path, "r", encoding="utf-8") as handle:
                raw = json.loads(handle.read())
        except Exception:
            return {
                "player_id": str(player_id or "default"),
                "transitions": [],
            }

        if not isinstance(raw, dict):
            return {
                "player_id": str(player_id or "default"),
                "transitions": [],
            }

        transitions = raw.get("transitions") if isinstance(raw.get("transitions"), list) else []
        return {
            "player_id": str(raw.get("player_id") or player_id or "default"),
            "transitions": [row for row in transitions if isinstance(row, dict)],
        }

    def _write_player_doc(self, player_id: str, payload: Dict[str, Any]) -> None:
        os.makedirs(self.base_dir, exist_ok=True)
        file_path = self._file_path_for_player(player_id)
        with open(file_path, "w", encoding="utf-8") as handle:
            json.dump(payload, handle, ensure_ascii=False, indent=2)

    def append_entry(self, entry: NarrativeTransitionLogEntry, *, keep_last: int = 200) -> Dict[str, Any]:
        row = entry.to_dict()
        player_id = str(row.get("player_id") or "default")

        with self._lock:
            doc = self._read_player_doc(player_id)
            transitions = list(doc.get("transitions") or [])
            transitions.append(row)
            if keep_last > 0 and len(transitions) > keep_last:
                transitions = transitions[-keep_last:]
            doc["player_id"] = player_id
            doc["transitions"] = transitions
            self._write_player_doc(player_id, doc)

        return row

    def last_entry(self, player_id: str) -> Optional[Dict[str, Any]]:
        with self._lock:
            doc = self._read_player_doc(player_id)
            transitions = list(doc.get("transitions") or [])
        if not transitions:
            return None
        return dict(transitions[-1])

    def list_entries(self, player_id: str, *, limit: int = 20) -> List[Dict[str, Any]]:
        normalized_limit = max(1, _safe_int(limit, 20))
        with self._lock:
            doc = self._read_player_doc(player_id)
            transitions = list(doc.get("transitions") or [])
        if not transitions:
            return []
        return [dict(row) for row in transitions[-normalized_limit:]]


narrative_transition_log_store = NarrativeTransitionLogStore()
