from __future__ import annotations

import json
from copy import deepcopy
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional


SCENE_CONTENT_DIR = Path(__file__).resolve().parents[2] / "content" / "scenes"
DEFAULT_THEME_REGISTRY_PATH = SCENE_CONTENT_DIR / "theme_registry.json"


class ThemeRegistryConflictError(RuntimeError):
    pass


def _normalize_token(value: Any) -> str:
    token = str(value or "").strip().lower()
    if not token:
        return ""
    return token.replace("-", "_").replace(" ", "_").strip("_")


def _normalize_tokens(values: Any) -> List[str]:
    if not isinstance(values, list):
        return []

    rows: List[str] = []
    seen: set[str] = set()
    for value in values:
        token = _normalize_token(value)
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


def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return float(default)


def _read_json(path: Path) -> Any:
    if not path.exists() or not path.is_file():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None


def _qualify_theme_id(raw_theme_id: Any, namespace: str) -> str:
    token = _normalize_token(raw_theme_id)
    if not token:
        return ""
    if ":" in token:
        return token

    normalized_namespace = _normalize_token(namespace)
    if not normalized_namespace:
        return token
    return f"{normalized_namespace}:{token}"


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


class ThemeRegistry:
    def __init__(self, *, builtin_theme_path: Optional[Path] = None) -> None:
        self._builtin_theme_path = (
            Path(builtin_theme_path)
            if isinstance(builtin_theme_path, Path)
            else DEFAULT_THEME_REGISTRY_PATH
        )
        self.version = "theme_registry_v1"
        self.themes: Dict[str, Dict[str, Any]] = {}
        self.enabled_packs: List[str] = []

        self._load_builtin_themes()
        self._merge_pack_themes()
        self._recalculate_counts()

    @staticmethod
    def _iter_theme_rows(raw_payload: Any) -> List[tuple[str, Dict[str, Any]]]:
        rows: List[tuple[str, Dict[str, Any]]] = []

        if isinstance(raw_payload, list):
            payload = {"themes": raw_payload}
        elif isinstance(raw_payload, dict):
            payload = dict(raw_payload)
        else:
            payload = {}

        raw_themes = payload.get("themes")
        if isinstance(raw_themes, dict):
            for raw_theme_id, raw_theme in raw_themes.items():
                if isinstance(raw_theme, dict):
                    rows.append((str(raw_theme_id), dict(raw_theme)))
            return rows

        if isinstance(raw_themes, list):
            for row in raw_themes:
                if not isinstance(row, dict):
                    continue
                raw_theme_id = row.get("theme_id") or row.get("id")
                if not raw_theme_id:
                    continue
                rows.append((str(raw_theme_id), dict(row)))
            return rows

        for raw_theme_id, raw_theme in payload.items():
            if raw_theme_id in {"version", "description", "source"}:
                continue
            if isinstance(raw_theme, dict):
                rows.append((str(raw_theme_id), dict(raw_theme)))

        return rows

    @staticmethod
    def _normalize_bonus_tags(raw_bonus_tags: Any) -> Dict[str, float]:
        bonus_tags: Dict[str, float] = {}

        if isinstance(raw_bonus_tags, dict):
            for key, value in raw_bonus_tags.items():
                token = _normalize_token(key)
                if not token:
                    continue
                bonus_tags[token] = _safe_float(value, 0.0)
            return bonus_tags

        if isinstance(raw_bonus_tags, list):
            for key in raw_bonus_tags:
                token = _normalize_token(key)
                if not token:
                    continue
                bonus_tags[token] = 1.0

        return bonus_tags

    def _normalize_theme_payload(
        self,
        *,
        theme_id: str,
        raw_theme: Dict[str, Any],
        namespace: str,
        source_pack: str,
        default_priority: int,
    ) -> Dict[str, Any]:
        full_theme_id = _qualify_theme_id(theme_id, namespace)
        normalized_namespace = _normalize_token(namespace)
        normalized_source_pack = _normalize_token(source_pack) or "builtin"

        keywords = _normalize_tokens(raw_theme.get("keywords") or raw_theme.get("theme_keywords") or [])

        allowed_fragments: List[str] = []
        seen_allowed: set[str] = set()
        for raw_fragment in raw_theme.get("allowed_fragments") or []:
            full_fragment = _qualify_fragment_id(raw_fragment, namespace)
            if not full_fragment or full_fragment in seen_allowed:
                continue
            seen_allowed.add(full_fragment)
            allowed_fragments.append(full_fragment)

        bonus_tags = self._normalize_bonus_tags(raw_theme.get("bonus_tags") or raw_theme.get("preferred_tags") or {})
        bonus_weight = _safe_float(raw_theme.get("bonus_weight"), 1.0)
        priority = _safe_int(raw_theme.get("priority"), default_priority)

        source = str(raw_theme.get("source") or "").strip() or (
            "builtin" if normalized_source_pack == "builtin" else f"pack:{normalized_source_pack}"
        )

        return {
            "id": full_theme_id,
            "namespace": normalized_namespace,
            "keywords": list(keywords),
            "allowed_fragments": list(allowed_fragments),
            "bonus_tags": dict(bonus_tags),
            "bonus_weight": float(bonus_weight),
            "priority": int(priority),
            "source": source,
            "source_pack": normalized_source_pack,
        }

    def _merge_theme(
        self,
        *,
        normalized_theme: Dict[str, Any],
    ) -> None:
        theme_id = _normalize_token(normalized_theme.get("id"))
        if not theme_id:
            return

        existing = self.themes.get(theme_id)
        if not isinstance(existing, dict):
            self.themes[theme_id] = dict(normalized_theme)
            return

        incoming_priority = _safe_int(normalized_theme.get("priority"), 0)
        existing_priority = _safe_int(existing.get("priority"), 0)
        incoming_source = str(normalized_theme.get("source_pack") or "builtin")
        existing_source = str(existing.get("source_pack") or "builtin")

        if incoming_priority > existing_priority:
            self.themes[theme_id] = dict(normalized_theme)
            return

        if incoming_priority < existing_priority:
            return

        if incoming_source != existing_source:
            raise ThemeRegistryConflictError(
                f"theme conflict: equal priority collision for '{theme_id}' between '{existing_source}' and '{incoming_source}'"
            )

        self.themes[theme_id] = dict(normalized_theme)

    def _load_builtin_themes(self) -> None:
        payload = _read_json(self._builtin_theme_path)
        if isinstance(payload, dict):
            version = str(payload.get("version") or "").strip()
            if version:
                self.version = version

        for raw_theme_id, raw_theme in self._iter_theme_rows(payload):
            if not isinstance(raw_theme, dict):
                continue

            normalized = self._normalize_theme_payload(
                theme_id=raw_theme_id,
                raw_theme=raw_theme,
                namespace="",
                source_pack="builtin",
                default_priority=0,
            )
            self._merge_theme(normalized_theme=normalized)

    def _merge_pack_themes(self) -> None:
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

            themes_path = pack_path / "themes.json"
            payload = _read_json(themes_path)
            if payload is None:
                continue

            for raw_theme_id, raw_theme in self._iter_theme_rows(payload):
                if not isinstance(raw_theme, dict):
                    continue

                normalized = self._normalize_theme_payload(
                    theme_id=raw_theme_id,
                    raw_theme=raw_theme,
                    namespace=namespace,
                    source_pack=pack_id,
                    default_priority=pack_priority,
                )
                self._merge_theme(normalized_theme=normalized)

    def _recalculate_counts(self) -> None:
        builtin = 0
        pack = 0

        for row in self.themes.values():
            source_pack = _normalize_token(row.get("source_pack") or "builtin")
            if source_pack == "builtin":
                builtin += 1
            else:
                pack += 1

        self.builtin_theme_count = int(builtin)
        self.pack_theme_count = int(pack)

    def list_themes(self) -> List[str]:
        return sorted(self.themes.keys())

    def get(self, theme_id: str) -> Optional[Dict[str, Any]]:
        token = _normalize_token(theme_id)
        if not token:
            return None
        row = self.themes.get(token)
        if not isinstance(row, dict):
            return None
        return deepcopy(row)

    def theme_map(self) -> Dict[str, Dict[str, Any]]:
        return {theme_id: deepcopy(row) for theme_id, row in self.themes.items()}

    def match_theme(self, theme_text: str) -> Dict[str, Any]:
        normalized_theme = _normalize_token(theme_text)
        if not normalized_theme:
            return {
                "theme": None,
                "applied": False,
                "matched_themes": [],
                "allowed_fragments": [],
                "bonus_tags": {},
                "selected_theme": None,
            }

        matched_rows: List[Dict[str, Any]] = []
        for theme_id, row in self.themes.items():
            keywords = row.get("keywords") if isinstance(row.get("keywords"), list) else []
            if not keywords:
                continue

            hits = 0
            for keyword in keywords:
                keyword_token = _normalize_token(keyword)
                if keyword_token and keyword_token in normalized_theme:
                    hits += 1

            if hits <= 0:
                continue

            matched_rows.append(
                {
                    "theme_id": theme_id,
                    "hits": int(hits),
                    "priority": _safe_int(row.get("priority"), 0),
                    "allowed_fragments": list(row.get("allowed_fragments") or []),
                    "bonus_tags": dict(row.get("bonus_tags") or {}),
                    "bonus_weight": _safe_float(row.get("bonus_weight"), 1.0),
                }
            )

        matched_rows.sort(
            key=lambda row: (
                -_safe_int(row.get("hits"), 0),
                -_safe_int(row.get("priority"), 0),
                str(row.get("theme_id") or ""),
            )
        )

        if not matched_rows:
            return {
                "theme": normalized_theme,
                "applied": False,
                "matched_themes": [],
                "allowed_fragments": [],
                "bonus_tags": {},
                "selected_theme": None,
            }

        allowed_fragments: List[str] = []
        seen_allowed: set[str] = set()
        bonus_tags: Dict[str, float] = {}

        for row in matched_rows:
            for fragment_id in row.get("allowed_fragments") or []:
                token = _normalize_token(fragment_id)
                if not token or token in seen_allowed:
                    continue
                seen_allowed.add(token)
                allowed_fragments.append(token)

            weight = _safe_float(row.get("bonus_weight"), 1.0)
            for tag, value in (row.get("bonus_tags") or {}).items():
                token = _normalize_token(tag)
                if not token:
                    continue
                bonus = _safe_float(value, 0.0) * weight
                bonus_tags[token] = float(bonus_tags.get(token, 0.0)) + float(bonus)

        matched_theme_ids = [str(row.get("theme_id") or "") for row in matched_rows if str(row.get("theme_id") or "")]

        return {
            "theme": normalized_theme,
            "applied": True,
            "matched_themes": matched_theme_ids,
            "allowed_fragments": allowed_fragments,
            "bonus_tags": bonus_tags,
            "selected_theme": matched_theme_ids[0] if matched_theme_ids else None,
        }

    def sources_for_themes(self, theme_ids: Iterable[str]) -> List[str]:
        sources: List[str] = []
        seen: set[str] = set()
        for raw_theme_id in theme_ids:
            theme = self.get(str(raw_theme_id))
            if not isinstance(theme, dict):
                continue
            source = str(theme.get("source") or "unknown")
            source_token = _normalize_token(source)
            if not source_token or source_token in seen:
                continue
            seen.add(source_token)
            sources.append(source)
        return sources
