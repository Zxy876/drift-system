from __future__ import annotations

import os
import sqlite3
import threading
import time
from typing import Any, Dict, List, Optional

from app.core.story.story_loader import BACKEND_DIR


DEFAULT_PLAYER_TAG_DB_PATH = os.path.join(BACKEND_DIR, "data", "player_tags.db")


def _normalize_resource_id(raw_value: Any) -> str:
    token = str(raw_value or "").strip().lower()
    if not token:
        return ""
    token = token.replace(" ", "_").replace("-", "_").strip("_")
    return token


def _normalize_namespace(raw_value: Any, resource_id: str) -> str:
    token = str(raw_value or "").strip().lower()
    if token:
        token = token.replace(" ", "_").replace("-", "_").strip("_")
    if token:
        return token

    if ":" in resource_id:
        namespace = resource_id.split(":", 1)[0].strip().lower()
        if namespace:
            return namespace

    return "minecraft"


def _normalize_resource_type(raw_value: Any) -> str:
    token = str(raw_value or "").strip().lower()
    if not token:
        return "item"
    token = token.replace(" ", "_").replace("-", "_").strip("_")
    return token or "item"


def _normalize_source(raw_value: Any) -> str | None:
    token = str(raw_value or "").strip().lower()
    if not token:
        return None
    return token


class PlayerTagStore:
    def __init__(self, db_path: str | None = None) -> None:
        configured_path = str(os.environ.get("DRIFT_PLAYER_TAG_DB_PATH") or "").strip()
        resolved_path = db_path or configured_path or DEFAULT_PLAYER_TAG_DB_PATH
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
    def _table_columns(conn: sqlite3.Connection) -> set[str]:
        rows = conn.execute("PRAGMA table_info(player_tags)").fetchall()
        return {
            str(row["name"])
            for row in rows
            if row is not None and str(row["name"] or "").strip()
        }

    @staticmethod
    def _ensure_column(
        conn: sqlite3.Connection,
        columns: set[str],
        *,
        column_name: str,
        alter_clause: str,
    ) -> None:
        if column_name in columns:
            return
        conn.execute(f"ALTER TABLE player_tags ADD COLUMN {alter_clause}")
        columns.add(column_name)

    def _ensure_schema(self, conn: sqlite3.Connection) -> None:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS player_tags (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                player_id TEXT NOT NULL,
                tag TEXT NOT NULL,
                resource_id TEXT NOT NULL,
                resource_type TEXT NOT NULL DEFAULT 'item',
                namespace TEXT NOT NULL DEFAULT 'minecraft',
                source TEXT NULL,
                created_at INTEGER NOT NULL,
                updated_at INTEGER NOT NULL
            )
            """
        )

        columns = self._table_columns(conn)
        self._ensure_column(
            conn,
            columns,
            column_name="resource_type",
            alter_clause="resource_type TEXT NOT NULL DEFAULT 'item'",
        )
        self._ensure_column(
            conn,
            columns,
            column_name="namespace",
            alter_clause="namespace TEXT NOT NULL DEFAULT 'minecraft'",
        )
        self._ensure_column(
            conn,
            columns,
            column_name="source",
            alter_clause="source TEXT NULL",
        )
        self._ensure_column(
            conn,
            columns,
            column_name="created_at",
            alter_clause="created_at INTEGER NOT NULL DEFAULT 0",
        )
        self._ensure_column(
            conn,
            columns,
            column_name="updated_at",
            alter_clause="updated_at INTEGER NOT NULL DEFAULT 0",
        )

        conn.execute(
            """
            CREATE UNIQUE INDEX IF NOT EXISTS ux_player_tags_player_tag
            ON player_tags(player_id, tag)
            """
        )

    @staticmethod
    def _row_to_item(row: sqlite3.Row | None) -> Optional[Dict[str, Any]]:
        if row is None:
            return None

        return {
            "id": int(row["id"]),
            "player_id": str(row["player_id"]),
            "tag": str(row["tag"]),
            "resource_id": str(row["resource_id"]),
            "resource_type": str(row["resource_type"]),
            "namespace": str(row["namespace"]),
            "source": row["source"],
            "created_at": int(row["created_at"]),
            "updated_at": int(row["updated_at"]),
        }

    def upsert_tag(
        self,
        *,
        player_id: str,
        tag: str,
        resource_id: str,
        resource_type: str | None = None,
        namespace: str | None = None,
        source: str | None = None,
    ) -> Optional[Dict[str, Any]]:
        normalized_player = str(player_id or "").strip()
        normalized_tag = str(tag or "").strip()
        normalized_resource_id = _normalize_resource_id(resource_id)

        if not normalized_player or not normalized_tag or not normalized_resource_id:
            return None

        normalized_resource_type = _normalize_resource_type(resource_type)
        normalized_namespace = _normalize_namespace(namespace, normalized_resource_id)
        normalized_source = _normalize_source(source)
        now_ms = int(time.time() * 1000)

        with self._lock:
            with self._connect() as conn:
                self._ensure_schema(conn)
                conn.execute(
                    """
                    INSERT INTO player_tags (
                        player_id, tag, resource_id, resource_type, namespace, source, created_at, updated_at
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(player_id, tag) DO UPDATE SET
                        resource_id = excluded.resource_id,
                        resource_type = excluded.resource_type,
                        namespace = excluded.namespace,
                        source = excluded.source,
                        updated_at = excluded.updated_at
                    """,
                    (
                        normalized_player,
                        normalized_tag,
                        normalized_resource_id,
                        normalized_resource_type,
                        normalized_namespace,
                        normalized_source,
                        now_ms,
                        now_ms,
                    ),
                )

                row = conn.execute(
                    """
                    SELECT id, player_id, tag, resource_id, resource_type, namespace, source, created_at, updated_at
                    FROM player_tags
                    WHERE player_id = ? AND tag = ?
                    """,
                    (normalized_player, normalized_tag),
                ).fetchone()

        return self._row_to_item(row)

    def list_player_tags(self, player_id: str) -> List[Dict[str, Any]]:
        normalized_player = str(player_id or "").strip()
        if not normalized_player:
            return []

        with self._lock:
            with self._connect() as conn:
                self._ensure_schema(conn)
                rows = conn.execute(
                    """
                    SELECT id, player_id, tag, resource_id, resource_type, namespace, source, created_at, updated_at
                    FROM player_tags
                    WHERE player_id = ?
                    ORDER BY updated_at DESC, id DESC
                    """,
                    (normalized_player,),
                ).fetchall()

        return [
            item
            for item in (self._row_to_item(row) for row in rows)
            if item is not None
        ]

    def list_tag_resources(self, player_id: str, tag: str) -> List[Dict[str, Any]]:
        normalized_player = str(player_id or "").strip()
        normalized_tag = str(tag or "").strip()
        if not normalized_player or not normalized_tag:
            return []

        with self._lock:
            with self._connect() as conn:
                self._ensure_schema(conn)
                rows = conn.execute(
                    """
                    SELECT id, player_id, tag, resource_id, resource_type, namespace, source, created_at, updated_at
                    FROM player_tags
                    WHERE player_id = ? AND tag = ?
                    ORDER BY updated_at DESC, id DESC
                    """,
                    (normalized_player, normalized_tag),
                ).fetchall()

        return [
            item
            for item in (self._row_to_item(row) for row in rows)
            if item is not None
        ]

    def delete_player_tag(self, *, player_id: str, tag: str) -> bool:
        normalized_player = str(player_id or "").strip()
        normalized_tag = str(tag or "").strip()
        if not normalized_player or not normalized_tag:
            return False

        with self._lock:
            with self._connect() as conn:
                self._ensure_schema(conn)
                cursor = conn.execute(
                    "DELETE FROM player_tags WHERE player_id = ? AND tag = ?",
                    (normalized_player, normalized_tag),
                )

        return int(cursor.rowcount or 0) > 0

    def delete_tag(self, tag_id: int) -> bool:
        try:
            normalized_id = int(tag_id)
        except (TypeError, ValueError):
            return False

        if normalized_id <= 0:
            return False

        with self._lock:
            with self._connect() as conn:
                self._ensure_schema(conn)
                cursor = conn.execute(
                    "DELETE FROM player_tags WHERE id = ?",
                    (normalized_id,),
                )

        return int(cursor.rowcount or 0) > 0


player_tag_store = PlayerTagStore()
