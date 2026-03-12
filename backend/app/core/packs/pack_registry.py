from __future__ import annotations

from threading import RLock
from typing import List, Optional

from .pack_loader import load_packs
from .pack_types import PackMeta


def _normalize_token(value: str | None) -> str:
    token = str(value or "").strip().lower()
    if not token:
        return ""
    return token.replace("-", "_").replace(" ", "_").strip("_")


class PackRegistry:
    def __init__(self, packs: Optional[List[PackMeta]] = None) -> None:
        self._lock = RLock()
        self._packs = list(packs) if isinstance(packs, list) else load_packs()

    def refresh(self) -> List[PackMeta]:
        with self._lock:
            self._packs = load_packs()
            return list(self._packs)

    def all(self) -> List[PackMeta]:
        with self._lock:
            return list(self._packs)

    def enabled(self) -> List[PackMeta]:
        with self._lock:
            return [pack_meta for pack_meta in self._packs if bool(pack_meta.enabled)]

    def enabled_ids(self) -> List[str]:
        rows: List[str] = []
        for pack_meta in self.enabled():
            token = _normalize_token(pack_meta.pack_id)
            if token:
                rows.append(token)
        return rows

    def get(self, pack_id: str | None) -> Optional[PackMeta]:
        wanted = _normalize_token(pack_id)
        if not wanted:
            return None
        with self._lock:
            for pack_meta in self._packs:
                if _normalize_token(pack_meta.pack_id) == wanted:
                    return pack_meta
        return None


_registry = PackRegistry()


def get_pack_registry() -> PackRegistry:
    return _registry
