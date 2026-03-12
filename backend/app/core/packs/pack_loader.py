from __future__ import annotations

import json
from pathlib import Path
from typing import Any, List

from .pack_types import PackMeta


PACK_DIR = Path(__file__).resolve().parents[2] / "content" / "packs"


def _safe_int(value: Any, default: int = 0) -> int:
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return int(default)


def _safe_bool(value: Any, default: bool = True) -> bool:
    if isinstance(value, bool):
        return value
    if value is None:
        return bool(default)
    normalized = str(value).strip().lower()
    if normalized in {"1", "true", "yes", "on"}:
        return True
    if normalized in {"0", "false", "no", "off"}:
        return False
    return bool(default)


def _normalize_token(value: Any, default: str = "") -> str:
    token = str(value or "").strip().lower()
    if not token:
        return str(default or "")
    return token.replace("-", "_").replace(" ", "_").strip("_") or str(default or "")


def _read_json(path: Path) -> Any:
    if not path.exists() or not path.is_file():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None


def load_packs() -> List[PackMeta]:
    packs: List[PackMeta] = []
    if not PACK_DIR.exists() or not PACK_DIR.is_dir():
        return packs

    seen_pack_ids: set[str] = set()
    for directory in sorted(PACK_DIR.iterdir(), key=lambda row: row.name):
        if not directory.is_dir():
            continue

        meta_path = directory / "pack.json"
        payload = _read_json(meta_path)
        if not isinstance(payload, dict):
            continue

        fallback_name = _normalize_token(directory.name)
        pack_id = _normalize_token(payload.get("pack_id"), fallback_name)
        if not pack_id or pack_id in seen_pack_ids:
            continue

        seen_pack_ids.add(pack_id)

        version = str(payload.get("version") or "1.0").strip() or "1.0"
        namespace = _normalize_token(payload.get("namespace"), pack_id)
        priority = _safe_int(payload.get("priority"), 0)
        enabled = _safe_bool(payload.get("enabled"), True)

        packs.append(
            PackMeta(
                pack_id=pack_id,
                version=version,
                namespace=namespace,
                priority=priority,
                enabled=enabled,
                pack_path=str(directory),
            )
        )

    packs.sort(key=lambda pack_meta: (-int(pack_meta.priority), str(pack_meta.pack_id)))
    return packs
