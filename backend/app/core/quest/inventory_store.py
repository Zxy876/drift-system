from __future__ import annotations

import os
import sqlite3
import threading
import time
from typing import Dict

from app.core.runtime.resource_canonical import normalize_inventory_resource_token
from app.core.story.story_loader import BACKEND_DIR


DEFAULT_INVENTORY_DB_PATH = os.path.join(BACKEND_DIR, "data", "inventory.db")


def _normalize_resource_token(raw_value: object) -> str:
    return normalize_inventory_resource_token(raw_value)


class InventoryStore:
    def __init__(self, db_path: str | None = None) -> None:
        configured_path = str(os.environ.get("DRIFT_INVENTORY_DB_PATH") or "").strip()
        resolved_path = db_path or configured_path or DEFAULT_INVENTORY_DB_PATH
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
            CREATE TABLE IF NOT EXISTS player_inventory (
                player_id TEXT NOT NULL,
                resource TEXT NOT NULL,
                amount INTEGER NOT NULL DEFAULT 0,
                updated_at_ms INTEGER NOT NULL,
                PRIMARY KEY (player_id, resource)
            )
            """
        )

    def add_resource(self, player_id: str, resource: str, amount: int = 1) -> int:
        normalized_player = str(player_id or "").strip()
        normalized_resource = _normalize_resource_token(resource)

        try:
            delta = int(amount)
        except (TypeError, ValueError):
            delta = 0

        if not normalized_player or not normalized_resource or delta == 0:
            return 0

        now_ms = int(time.time() * 1000)

        with self._lock:
            with self._connect() as conn:
                self._ensure_schema(conn)
                conn.execute(
                    """
                    INSERT INTO player_inventory (player_id, resource, amount, updated_at_ms)
                    VALUES (?, ?, ?, ?)
                    ON CONFLICT(player_id, resource) DO UPDATE SET
                        amount = CASE
                            WHEN player_inventory.amount + excluded.amount < 0 THEN 0
                            ELSE player_inventory.amount + excluded.amount
                        END,
                        updated_at_ms = excluded.updated_at_ms
                    """,
                    (normalized_player, normalized_resource, delta, now_ms),
                )
                conn.execute(
                    "DELETE FROM player_inventory WHERE player_id = ? AND resource = ? AND amount <= 0",
                    (normalized_player, normalized_resource),
                )
                row = conn.execute(
                    "SELECT amount FROM player_inventory WHERE player_id = ? AND resource = ?",
                    (normalized_player, normalized_resource),
                ).fetchone()
                return int(row["amount"]) if row else 0

    def get_resources(self, player_id: str) -> Dict[str, int]:
        normalized_player = str(player_id or "").strip()
        if not normalized_player:
            return {}

        with self._lock:
            with self._connect() as conn:
                self._ensure_schema(conn)
                rows = conn.execute(
                    "SELECT resource, amount FROM player_inventory WHERE player_id = ? AND amount > 0",
                    (normalized_player,),
                ).fetchall()

        return {
            str(row["resource"]): int(row["amount"])
            for row in rows
            if row is not None and int(row["amount"]) > 0
        }

    def clear_player_resources(self, player_id: str) -> int:
        normalized_player = str(player_id or "").strip()
        if not normalized_player:
            return 0

        with self._lock:
            with self._connect() as conn:
                self._ensure_schema(conn)
                cursor = conn.execute(
                    "DELETE FROM player_inventory WHERE player_id = ?",
                    (normalized_player,),
                )

        return int(cursor.rowcount or 0)


inventory_store = InventoryStore()
