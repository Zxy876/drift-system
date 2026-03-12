from __future__ import annotations

import json
from copy import deepcopy
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional


SCENE_CONTENT_DIR = Path(__file__).resolve().parents[2] / "content" / "scenes"
DEFAULT_FRAGMENTS_DIR = SCENE_CONTENT_DIR / "fragments"


class FragmentRegistryConflictError(RuntimeError):
    pass


def _normalize_token(value: Any) -> str:
    token = str(value or "").strip().lower()
    if not token:
        return ""
    return token.replace("-", "_").replace(" ", "_").strip("_")


def _normalize_token_list(values: Any) -> List[str]:
    if not isinstance(values, list):
        return []

    normalized: List[str] = []
    seen: set[str] = set()
    for value in values:
        token = _normalize_token(value)
        if not token or token in seen:
            continue
        seen.add(token)
        normalized.append(token)
    return normalized


def _safe_int(value: Any, default: int = 0) -> int:
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return int(default)


def _read_json(path: Path) -> Any:
    if not path.exists() or not path.is_file():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None


def _qualify_fragment_id(raw_fragment_id: Any, namespace: str) -> str:
    token = _normalize_token(raw_fragment_id)
    if not token:
        return ""
    if ":" in token:
        return token
    normalized_namespace = _normalize_token(namespace)
    if not normalized_namespace:
        return token
    return f"{normalized_namespace}:{token}"


class FragmentRegistry:
    def __init__(
        self,
        *,
        builtin_fragments_dir: Optional[Path] = None,
        version: str = "fragment_registry_v1",
    ) -> None:
        self.version = str(version or "fragment_registry_v1").strip() or "fragment_registry_v1"
        self._builtin_fragments_dir = (
            Path(builtin_fragments_dir)
            if isinstance(builtin_fragments_dir, Path)
            else DEFAULT_FRAGMENTS_DIR
        )

        self.fragments: Dict[str, Dict[str, Any]] = {}
        self.enabled_packs: List[str] = []

        self._load_builtin_fragments()
        self._merge_pack_fragments()
        self._recalculate_counts()

    @staticmethod
    def _normalize_fragment_payload(
        *,
        fragment_id: str,
        raw_fragment: Dict[str, Any],
        source_pack: str,
        priority: Optional[int] = None,
    ) -> Dict[str, Any]:
        source_pack_token = _normalize_token(source_pack) or "builtin"

        raw_size = raw_fragment.get("size")
        if isinstance(raw_size, list) and len(raw_size) >= 2:
            size = [
                max(1, _safe_int(raw_size[0], 3)),
                max(1, _safe_int(raw_size[1], 3)),
            ]
        else:
            size = [3, 3]

        theme_keywords = [str(item) for item in (raw_fragment.get("theme_keywords") or []) if str(item).strip()]

        structures: List[Dict[str, Any]] = []
        if isinstance(raw_fragment.get("structures"), list):
            for structure in raw_fragment.get("structures") or []:
                if isinstance(structure, dict):
                    structures.append(dict(structure))

        npcs: List[Dict[str, Any]] = []
        if isinstance(raw_fragment.get("npcs"), list):
            for npc in raw_fragment.get("npcs") or []:
                if isinstance(npc, dict):
                    npcs.append(dict(npc))

        events: List[Dict[str, Any]] = []
        if isinstance(raw_fragment.get("events"), list):
            for event in raw_fragment.get("events") or []:
                if isinstance(event, dict):
                    events.append(dict(event))

        normalized_priority = _safe_int(priority, _safe_int(raw_fragment.get("priority"), 0))
        source_value = str(raw_fragment.get("source") or "").strip() or (
            "builtin" if source_pack_token == "builtin" else f"pack:{source_pack_token}"
        )

        return {
            "id": _normalize_token(fragment_id),
            "root": bool(raw_fragment.get("root", False)),
            "priority": int(normalized_priority),
            "tags": _normalize_token_list(raw_fragment.get("tags")),
            "requires": _normalize_token_list(raw_fragment.get("requires")),
            "optional_resources": _normalize_token_list(raw_fragment.get("optional_resources")),
            "size": size,
            "layout_anchor": str(raw_fragment.get("layout_anchor") or "center").strip().lower() or "center",
            "structures": structures,
            "npcs": npcs,
            "connections": _normalize_token_list(raw_fragment.get("connections")),
            "theme_keywords": theme_keywords,
            "events": events,
            "source": source_value,
            "source_pack": source_pack_token,
        }

    @staticmethod
    def _iter_pack_fragments(raw_payload: Any) -> List[tuple[str, Dict[str, Any]]]:
        rows: List[tuple[str, Dict[str, Any]]] = []

        if isinstance(raw_payload, list):
            payload = {"fragments": raw_payload}
        elif isinstance(raw_payload, dict):
            payload = dict(raw_payload)
        else:
            payload = {}

        raw_fragments = payload.get("fragments")

        if isinstance(raw_fragments, dict):
            for raw_fragment_id, raw_fragment in raw_fragments.items():
                if isinstance(raw_fragment, dict):
                    rows.append((str(raw_fragment_id), dict(raw_fragment)))
            return rows

        if isinstance(raw_fragments, list):
            for row in raw_fragments:
                if not isinstance(row, dict):
                    continue
                raw_fragment_id = row.get("fragment_id") or row.get("id")
                if not raw_fragment_id:
                    continue
                rows.append((str(raw_fragment_id), dict(row)))

        return rows

    def _load_builtin_fragments(self) -> None:
        builtin_dir = self._builtin_fragments_dir
        if not builtin_dir.exists() or not builtin_dir.is_dir():
            return

        for file_path in sorted(builtin_dir.glob("*.json"), key=lambda path: path.name):
            payload = _read_json(file_path)
            if not isinstance(payload, dict):
                continue

            fragment_id = _normalize_token(payload.get("id") or file_path.stem)
            if not fragment_id:
                continue

            self.fragments[fragment_id] = self._normalize_fragment_payload(
                fragment_id=fragment_id,
                raw_fragment=payload,
                source_pack="builtin",
                priority=_safe_int(payload.get("priority"), 0),
            )

    def _merge_one_pack_fragment(
        self,
        *,
        fragment_id: str,
        fragment_payload: Dict[str, Any],
        pack_id: str,
        namespace: str,
        pack_priority: int,
    ) -> None:
        full_fragment_id = _qualify_fragment_id(fragment_id, namespace)
        if not full_fragment_id:
            return

        normalized_pack_id = _normalize_token(pack_id)
        incoming_priority = _safe_int(fragment_payload.get("priority"), pack_priority)
        incoming = self._normalize_fragment_payload(
            fragment_id=full_fragment_id,
            raw_fragment={
                **dict(fragment_payload),
                "source": str(fragment_payload.get("source") or f"pack:{normalized_pack_id}"),
            },
            source_pack=normalized_pack_id,
            priority=incoming_priority,
        )

        existing = self.fragments.get(full_fragment_id)
        if not isinstance(existing, dict):
            self.fragments[full_fragment_id] = incoming
            return

        existing_priority = _safe_int(existing.get("priority"), 0)
        existing_pack = _normalize_token(existing.get("source_pack") or "builtin")

        if incoming_priority > existing_priority:
            self.fragments[full_fragment_id] = incoming
            return

        if incoming_priority < existing_priority:
            return

        if existing_pack != normalized_pack_id:
            raise FragmentRegistryConflictError(
                f"fragment conflict: equal priority collision for '{full_fragment_id}' between '{existing_pack}' and '{normalized_pack_id}'"
            )

        self.fragments[full_fragment_id] = incoming

    def _merge_pack_fragments(self) -> None:
        try:
            from app.core.packs.pack_registry import get_pack_registry
        except Exception:
            return

        try:
            pack_registry = get_pack_registry()
            enabled = pack_registry.enabled() if hasattr(pack_registry, "enabled") else []
        except Exception:
            enabled = []

        pack_rows = [row for row in enabled if hasattr(row, "pack_id")]
        self.enabled_packs = [
            _normalize_token(getattr(row, "pack_id", ""))
            for row in pack_rows
            if _normalize_token(getattr(row, "pack_id", ""))
        ]

        for pack_meta in pack_rows:
            pack_id = _normalize_token(getattr(pack_meta, "pack_id", ""))
            namespace = _normalize_token(getattr(pack_meta, "namespace", "")) or pack_id
            pack_priority = _safe_int(getattr(pack_meta, "priority", 0), 0)
            pack_path = Path(str(getattr(pack_meta, "pack_path", "") or ""))
            if not pack_id or not pack_path.exists() or not pack_path.is_dir():
                continue

            fragments_path = pack_path / "fragments.json"
            payload = _read_json(fragments_path)
            if payload is None:
                continue

            for raw_fragment_id, raw_fragment in self._iter_pack_fragments(payload):
                self._merge_one_pack_fragment(
                    fragment_id=raw_fragment_id,
                    fragment_payload=raw_fragment,
                    pack_id=pack_id,
                    namespace=namespace,
                    pack_priority=pack_priority,
                )

    def _recalculate_counts(self) -> None:
        builtin = 0
        pack_fragments = 0

        for fragment in self.fragments.values():
            source_pack = _normalize_token(fragment.get("source_pack") or "builtin")
            if source_pack == "builtin":
                builtin += 1
            else:
                pack_fragments += 1

        self.builtin_fragment_count = int(builtin)
        self.pack_fragment_count = int(pack_fragments)

    def get(self, fragment_id: str) -> Optional[Dict[str, Any]]:
        token = _normalize_token(fragment_id)
        if not token:
            return None
        row = self.fragments.get(token)
        if not isinstance(row, dict):
            return None
        return deepcopy(row)

    def list_fragments(self) -> List[str]:
        return sorted(self.fragments.keys())

    def fragment_map(self) -> Dict[str, Dict[str, Any]]:
        return {fragment_id: deepcopy(fragment) for fragment_id, fragment in self.fragments.items()}

    def sources_for_fragments(self, fragment_ids: Iterable[str]) -> List[str]:
        sources: List[str] = []
        seen: set[str] = set()

        for raw_fragment_id in fragment_ids:
            fragment = self.get(str(raw_fragment_id))
            if not isinstance(fragment, dict):
                continue
            source = str(fragment.get("source") or "unknown").strip() or "unknown"
            normalized_source = _normalize_token(source)
            if not normalized_source or normalized_source in seen:
                continue
            seen.add(normalized_source)
            sources.append(source)

        return sources
