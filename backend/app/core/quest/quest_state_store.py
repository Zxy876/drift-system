from __future__ import annotations

import json
import os
import sqlite3
import threading
import time
from typing import Any, Dict, Optional

from app.core.story.story_loader import BACKEND_DIR


DEFAULT_QUEST_STATE_DB_PATH = os.path.join(BACKEND_DIR, "data", "quest_state.db")


class QuestStateStore:
    def __init__(self, db_path: str | None = None) -> None:
        configured_path = str(os.environ.get("DRIFT_QUEST_STATE_DB_PATH") or "").strip()
        resolved_path = db_path or configured_path or DEFAULT_QUEST_STATE_DB_PATH
        self.db_path = os.path.abspath(str(resolved_path))
        self._lock = threading.RLock()

    def _connect(self) -> sqlite3.Connection:
        parent = os.path.dirname(self.db_path)
        if parent:
            os.makedirs(parent, exist_ok=True)
        conn = sqlite3.connect(self.db_path, timeout=5.0)
        conn.row_factory = sqlite3.Row
        return conn

    @staticmethod
    def _ensure_schema(conn: sqlite3.Connection) -> None:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS player_quest_state (
                player_id TEXT NOT NULL,
                level_id TEXT NOT NULL,
                state_json TEXT NOT NULL,
                updated_at_ms INTEGER NOT NULL,
                PRIMARY KEY (player_id, level_id)
            )
            """
        )

    def save_state(self, player_id: str, level_id: str, state: Dict[str, Any]) -> None:
        normalized_player = str(player_id or "").strip()
        normalized_level = str(level_id or "").strip()
        if not normalized_player or not normalized_level or not isinstance(state, dict):
            return

        now_ms = int(time.time() * 1000)
        payload = json.dumps(state, ensure_ascii=False, separators=(",", ":"))

        with self._lock:
            with self._connect() as conn:
                self._ensure_schema(conn)
                conn.execute(
                    """
                    INSERT INTO player_quest_state (player_id, level_id, state_json, updated_at_ms)
                    VALUES (?, ?, ?, ?)
                    ON CONFLICT(player_id, level_id) DO UPDATE SET
                        state_json = excluded.state_json,
                        updated_at_ms = excluded.updated_at_ms
                    """,
                    (normalized_player, normalized_level, payload, now_ms),
                )

    def load_state(self, player_id: str, level_id: str) -> Optional[Dict[str, Any]]:
        normalized_player = str(player_id or "").strip()
        normalized_level = str(level_id or "").strip()
        if not normalized_player or not normalized_level:
            return None

        with self._lock:
            with self._connect() as conn:
                self._ensure_schema(conn)
                row = conn.execute(
                    """
                    SELECT state_json
                    FROM player_quest_state
                    WHERE player_id = ? AND level_id = ?
                    """,
                    (normalized_player, normalized_level),
                ).fetchone()

        if not row:
            return None

        raw_json = row["state_json"]
        if not isinstance(raw_json, str) or not raw_json.strip():
            return None

        try:
            decoded = json.loads(raw_json)
        except (TypeError, ValueError):
            return None

        return decoded if isinstance(decoded, dict) else None

    def delete_state(self, player_id: str, level_id: str) -> None:
        normalized_player = str(player_id or "").strip()
        normalized_level = str(level_id or "").strip()
        if not normalized_player or not normalized_level:
            return

        with self._lock:
            with self._connect() as conn:
                self._ensure_schema(conn)
                conn.execute(
                    "DELETE FROM player_quest_state WHERE player_id = ? AND level_id = ?",
                    (normalized_player, normalized_level),
                )

    def delete_player_states(self, player_id: str) -> int:
        normalized_player = str(player_id or "").strip()
        if not normalized_player:
            return 0

        with self._lock:
            with self._connect() as conn:
                self._ensure_schema(conn)
                cursor = conn.execute(
                    "DELETE FROM player_quest_state WHERE player_id = ?",
                    (normalized_player,),
                )

        return int(cursor.rowcount or 0)


quest_state_store = QuestStateStore()
