from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional


BASE_CONTENT_DIR = Path(__file__).resolve().parents[2] / "content"
VANILLA_PATH = BASE_CONTENT_DIR / "scenes" / "semantic_tags.json"
MOD_MAP_PATH = BASE_CONTENT_DIR / "semantic" / "mod_semantic_map.json"
SOURCES_PATH = BASE_CONTENT_DIR / "semantic" / "semantic_sources.json"


class SemanticRegistryConflictError(RuntimeError):
    pass


def normalize_semantic_item_id(value: Any) -> str:
    token = str(value or "").strip().lower()
    if not token:
        return ""
    return token.replace("-", "_").replace(" ", "_")


def _normalize_tag(value: Any) -> str:
    token = str(value or "").strip().lower()
    if not token:
        return ""
    return token.replace("-", "_").replace(" ", "_")


def _normalize_tags(raw_values: Any) -> List[str]:
    rows: List[str] = []
    seen = set()

    values: List[Any]
    if isinstance(raw_values, list):
        values = list(raw_values)
    else:
        values = [raw_values]

    for value in values:
        token = _normalize_tag(value)
        if not token or token in seen:
            continue
        seen.add(token)
        rows.append(token)

    return rows


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


def _with_aliases(mapping: Dict[str, List[str]], *, item_id: str, tags: List[str]) -> None:
    if not item_id or not tags:
        return

    if item_id not in mapping:
        mapping[item_id] = list(tags)

    if ":" in item_id:
        suffix = item_id.split(":", 1)[1]
        if suffix and suffix not in mapping:
            mapping[suffix] = list(tags)
    else:
        minecraft_alias = f"minecraft:{item_id}"
        if minecraft_alias not in mapping:
            mapping[minecraft_alias] = list(tags)


def _qualify_item_id(raw_item_id: Any, namespace: str) -> str:
    token = normalize_semantic_item_id(raw_item_id)
    if not token:
        return ""
    if ":" in token:
        return token

    normalized_namespace = normalize_semantic_item_id(namespace)
    if not normalized_namespace:
        return token

    return f"{normalized_namespace}:{token}"


def _iter_aliases(item_id: str) -> List[str]:
    aliases: List[str] = []
    seen: set[str] = set()

    def _append(value: str) -> None:
        token = normalize_semantic_item_id(value)
        if not token or token in seen:
            return
        seen.add(token)
        aliases.append(token)

    _append(item_id)

    if ":" in item_id:
        suffix = item_id.split(":", 1)[1]
        if suffix:
            _append(suffix)
    else:
        _append(f"minecraft:{item_id}")

    return aliases


def _extract_semantic_mapping(raw_payload: Any) -> Dict[str, Any]:
    if isinstance(raw_payload, dict):
        semantic_map = raw_payload.get("semantic_map")
        if isinstance(semantic_map, dict):
            return dict(semantic_map)

        items = raw_payload.get("items")
        if isinstance(items, dict):
            return dict(items)

        return dict(raw_payload)

    if isinstance(raw_payload, list):
        mapping: Dict[str, Any] = {}
        for row in raw_payload:
            if not isinstance(row, dict):
                continue
            item_id = row.get("item_id") or row.get("id")
            if not item_id:
                continue
            mapping[str(item_id)] = dict(row)
        return mapping

    return {}


def _parse_entry(raw_value: Any) -> tuple[List[str], int]:
    if isinstance(raw_value, dict):
        tags = _normalize_tags(raw_value.get("semantic_tags") or raw_value.get("tags"))
        bonus = _safe_int(raw_value.get("priority"), 0)
        return tags, bonus

    tags = _normalize_tags(raw_value)
    return tags, 0


def _source_label_pack(pack_id: str) -> str:
    token = normalize_semantic_item_id(pack_id)
    return f"pack:{token}" if token else "pack:unknown"


class SemanticRegistry:
    def __init__(
        self,
        *,
        vanilla_path: Optional[Path] = None,
        mod_map_path: Optional[Path] = None,
        sources_path: Optional[Path] = None,
    ) -> None:
        self._vanilla_path = Path(vanilla_path) if isinstance(vanilla_path, Path) else VANILLA_PATH
        self._mod_map_path = Path(mod_map_path) if isinstance(mod_map_path, Path) else MOD_MAP_PATH
        self._sources_path = Path(sources_path) if isinstance(sources_path, Path) else SOURCES_PATH

        self.version = "1.0"
        self.vanilla: Dict[str, List[str]] = {}
        self.mod: Dict[str, List[str]] = {}
        self.pack: Dict[str, List[str]] = {}
        self.merged: Dict[str, List[str]] = {}
        self.enabled_packs: List[str] = []

        self._entries: Dict[str, Dict[str, Any]] = {}

        source_scores = self._load_source_scores()
        self._load_builtin_sources(source_scores)
        self._load_pack_sources(source_scores)
        self._finalize_maps()

    def _load_source_scores(self) -> Dict[str, int]:
        payload = _read_json(self._sources_path)
        if isinstance(payload, dict):
            version = str(payload.get("version") or "").strip()
            if version:
                self.version = version

        sources = payload.get("sources") if isinstance(payload, dict) else {}
        if not isinstance(sources, dict):
            sources = {}

        def _rank(source_name: str, default_rank: int) -> int:
            row = sources.get(source_name)
            if not isinstance(row, dict):
                return int(default_rank)
            return _safe_int(row.get("priority"), default_rank)

        vanilla_rank = max(1, _rank("vanilla_registry", 1))
        mod_rank = max(1, _rank("mod_map", 2))

        vanilla_score = 10_000 - vanilla_rank
        mod_score = 10_000 - mod_rank
        pack_base = max(vanilla_score, mod_score) + 100

        return {
            "vanilla_registry": int(vanilla_score),
            "mod_map": int(mod_score),
            "pack_base": int(pack_base),
        }

    @staticmethod
    def _read_map_file(path: Path) -> Dict[str, Any]:
        payload = _read_json(path)
        return _extract_semantic_mapping(payload)

    def _merge_entry(
        self,
        *,
        item_id: str,
        tags: List[str],
        source: str,
        priority: int,
    ) -> None:
        if not item_id or not tags:
            return

        existing = self._entries.get(item_id)
        if not isinstance(existing, dict):
            self._entries[item_id] = {
                "tags": list(tags),
                "source": str(source),
                "priority": int(priority),
            }
            return

        existing_priority = _safe_int(existing.get("priority"), 0)
        existing_source = str(existing.get("source") or "unknown")
        existing_tags = _normalize_tags(existing.get("tags") or [])
        incoming_tags = _normalize_tags(tags)

        if int(priority) > existing_priority:
            self._entries[item_id] = {
                "tags": list(incoming_tags),
                "source": str(source),
                "priority": int(priority),
            }
            return

        if int(priority) < existing_priority:
            return

        if existing_source != str(source) and existing_tags != incoming_tags:
            raise SemanticRegistryConflictError(
                f"semantic conflict: equal priority collision for '{item_id}' between '{existing_source}' and '{source}'"
            )

    def _ingest_mapping(
        self,
        *,
        mapping: Dict[str, Any],
        source: str,
        base_priority: int,
        namespace: str,
        target_map: Dict[str, List[str]],
    ) -> None:
        for raw_key, raw_value in mapping.items():
            full_item_id = _qualify_item_id(raw_key, namespace)
            if not full_item_id:
                continue

            tags, bonus_priority = _parse_entry(raw_value)
            if not tags:
                continue

            _with_aliases(target_map, item_id=full_item_id, tags=tags)

            priority = int(base_priority) + int(bonus_priority)
            for alias in _iter_aliases(full_item_id):
                self._merge_entry(
                    item_id=alias,
                    tags=tags,
                    source=source,
                    priority=priority,
                )

    def _load_builtin_sources(self, source_scores: Dict[str, int]) -> None:
        vanilla_map = self._read_map_file(self._vanilla_path)
        self._ingest_mapping(
            mapping=vanilla_map,
            source="vanilla_registry",
            base_priority=_safe_int(source_scores.get("vanilla_registry"), 9_999),
            namespace="minecraft",
            target_map=self.vanilla,
        )

        mod_map = self._read_map_file(self._mod_map_path)
        self._ingest_mapping(
            mapping=mod_map,
            source="mod_map",
            base_priority=_safe_int(source_scores.get("mod_map"), 9_998),
            namespace="",
            target_map=self.mod,
        )

    def _load_pack_sources(self, source_scores: Dict[str, int]) -> None:
        try:
            from app.core.packs.pack_registry import get_pack_registry
        except Exception:
            return

        try:
            pack_registry = get_pack_registry()
            enabled_packs = pack_registry.enabled() if hasattr(pack_registry, "enabled") else []
        except Exception:
            enabled_packs = []

        pack_rows = [row for row in enabled_packs if hasattr(row, "pack_id")]
        self.enabled_packs = [
            normalize_semantic_item_id(getattr(row, "pack_id", ""))
            for row in pack_rows
            if normalize_semantic_item_id(getattr(row, "pack_id", ""))
        ]

        for pack_meta in pack_rows:
            pack_id = normalize_semantic_item_id(getattr(pack_meta, "pack_id", ""))
            namespace = normalize_semantic_item_id(getattr(pack_meta, "namespace", "")) or pack_id
            pack_priority = _safe_int(getattr(pack_meta, "priority", 0), 0)
            pack_path = Path(str(getattr(pack_meta, "pack_path", "") or ""))

            if not pack_id or not pack_path.exists() or not pack_path.is_dir():
                continue

            semantic_map_path = pack_path / "semantic_map.json"
            mapping = self._read_map_file(semantic_map_path)
            if not mapping:
                continue

            self._ingest_mapping(
                mapping=mapping,
                source=_source_label_pack(pack_id),
                base_priority=_safe_int(source_scores.get("pack_base"), 10_100) + pack_priority,
                namespace=namespace,
                target_map=self.pack,
            )

    def _finalize_maps(self) -> None:
        merged: Dict[str, List[str]] = {}
        for item_id, row in self._entries.items():
            tags = _normalize_tags(row.get("tags") or [])
            if not item_id or not tags:
                continue
            merged[item_id] = list(tags)

        self.merged = merged
        self.vanilla_count = len(self.vanilla)
        self.mod_count = len(self.mod)
        self.pack_count = len(self.pack)
        self.merged_count = len(self.merged)

    @staticmethod
    def _load_map(path: Path) -> Dict[str, List[str]]:
        payload = _read_json(path)
        if not isinstance(payload, dict):
            return {}

        mapping: Dict[str, List[str]] = {}
        for raw_key, raw_value in payload.items():
            item_id = normalize_semantic_item_id(raw_key)
            if not item_id:
                continue
            tags = _normalize_tags(raw_value)
            if not tags:
                continue
            _with_aliases(mapping, item_id=item_id, tags=tags)

        return mapping

    def resolve(self, item_id: str) -> Optional[Dict[str, Any]]:
        normalized = normalize_semantic_item_id(item_id)
        if not normalized:
            return None

        row = self._entries.get(normalized)
        if not isinstance(row, dict):
            return None

        tags = _normalize_tags(row.get("tags") or [])
        if not tags:
            return None

        return {
            "item_id": normalized,
            "semantic_tags": list(tags),
            "source": str(row.get("source") or "fallback"),
            "priority": _safe_int(row.get("priority"), 0),
        }

    def get_vanilla(self, item_id: str) -> Optional[List[str]]:
        normalized = normalize_semantic_item_id(item_id)
        if not normalized:
            return None
        values = self.vanilla.get(normalized)
        if not isinstance(values, list):
            return None
        return list(values)

    def get_pack(self, item_id: str) -> Optional[List[str]]:
        normalized = normalize_semantic_item_id(item_id)
        if not normalized:
            return None
        values = self.pack.get(normalized)
        if not isinstance(values, list):
            return None
        return list(values)

    def source_for(self, item_id: str) -> Optional[str]:
        normalized = normalize_semantic_item_id(item_id)
        if not normalized:
            return None
        row = self._entries.get(normalized)
        if not isinstance(row, dict):
            return None
        return str(row.get("source") or "") or None

    def list_items(self) -> List[str]:
        return sorted(self.merged.keys())

    def sources_for_items(self, item_ids: Iterable[str]) -> List[str]:
        sources: List[str] = []
        seen: set[str] = set()
        for raw_item_id in item_ids:
            source = self.source_for(str(raw_item_id))
            token = normalize_semantic_item_id(source)
            if not token or token in seen:
                continue
            seen.add(token)
            sources.append(str(source))
        return sources

    def get_mod(self, item_id: str) -> Optional[List[str]]:
        normalized = normalize_semantic_item_id(item_id)
        if not normalized:
            return None
        values = self.mod.get(normalized)
        if not isinstance(values, list):
            return None
        return list(values)


@lru_cache(maxsize=1)
def get_semantic_registry() -> SemanticRegistry:
    return SemanticRegistry()


def reset_semantic_registry_cache() -> None:
    get_semantic_registry.cache_clear()


def semantic_registry_info() -> Dict[str, Any]:
    try:
        registry = get_semantic_registry()
        return {
            "version": registry.version,
            "semantic_item_count": int(getattr(registry, "merged_count", len(registry.list_items()))),
            "vanilla_count": int(getattr(registry, "vanilla_count", 0)),
            "mod_count": int(getattr(registry, "mod_count", 0)),
            "pack_count": int(getattr(registry, "pack_count", 0)),
            "enabled_packs": list(getattr(registry, "enabled_packs", [])),
        }
    except Exception:
        return {
            "version": None,
            "semantic_item_count": 0,
            "vanilla_count": 0,
            "mod_count": 0,
            "pack_count": 0,
            "enabled_packs": [],
        }
