from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional


class AssetRegistryConflictError(RuntimeError):
    pass


def _normalize_token(value: Any) -> str:
    token = str(value or "").strip().lower()
    return token.replace("-", "_").replace(" ", "_").strip("_")


def _normalize_tokens(values: Iterable[Any]) -> List[str]:
    normalized: List[str] = []
    seen = set()
    for raw in values:
        token = _normalize_token(raw)
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


def _asset_namespace(asset_id: str) -> str:
    token = _normalize_token(asset_id)
    if ":" not in token:
        return ""
    return token.split(":", 1)[0]


def _qualify_asset_id(raw_asset_id: Any, namespace: str) -> str:
    token = _normalize_token(raw_asset_id)
    if not token:
        return ""
    if ":" in token:
        return token
    normalized_namespace = _normalize_token(namespace)
    if not normalized_namespace:
        return token
    return f"{normalized_namespace}:{token}"


class AssetRegistry:
    def __init__(self, file_path: Path) -> None:
        payload = _read_json(file_path)
        if not isinstance(payload, dict):
            payload = {}

        self.version = str(payload.get("version") or "").strip() or "unknown"
        raw_assets = payload.get("assets")
        if not isinstance(raw_assets, dict):
            raw_assets = {}

        self.assets: Dict[str, Dict[str, Any]] = {}
        self.enabled_packs: List[str] = []

        for raw_id, raw_data in raw_assets.items():
            if not isinstance(raw_data, dict):
                continue
            asset_id = _qualify_asset_id(raw_id, namespace="")
            if not asset_id:
                continue
            normalized_asset = self._normalize_asset_payload(
                asset_id=asset_id,
                raw_asset=raw_data,
                source_pack="builtin",
                priority=0,
            )
            self.assets[asset_id] = normalized_asset

        self._merge_pack_assets()
        self._recalculate_counts()

    @staticmethod
    def _normalize_asset_payload(
        *,
        asset_id: str,
        raw_asset: Dict[str, Any],
        source_pack: str,
        priority: int,
    ) -> Dict[str, Any]:
        normalized_asset = dict(raw_asset)
        normalized_asset["id"] = _normalize_token(asset_id)
        normalized_asset["namespace"] = _asset_namespace(asset_id)
        normalized_asset["type"] = _normalize_token(raw_asset.get("type") or "")
        normalized_asset["source"] = _normalize_token(raw_asset.get("source") or "unknown")
        normalized_asset["semantic_tags"] = _normalize_tokens(raw_asset.get("semantic_tags") or raw_asset.get("tags") or [])
        normalized_asset["spawn_method"] = _normalize_token(raw_asset.get("spawn_method") or "fragment")
        normalized_asset["priority"] = int(priority)
        normalized_asset["source_pack"] = _normalize_token(source_pack)
        return normalized_asset

    @staticmethod
    def _iter_pack_assets(raw_payload: Any) -> List[tuple[str, Dict[str, Any]]]:
        assets: List[tuple[str, Dict[str, Any]]] = []
        payload = raw_payload if isinstance(raw_payload, dict) else {}
        raw_assets = payload.get("assets")

        if isinstance(raw_assets, dict):
            for raw_asset_id, raw_asset in raw_assets.items():
                if isinstance(raw_asset, dict):
                    assets.append((str(raw_asset_id), dict(raw_asset)))
            return assets

        if isinstance(raw_assets, list):
            for row in raw_assets:
                if not isinstance(row, dict):
                    continue
                raw_asset_id = row.get("asset_id") or row.get("id")
                if not raw_asset_id:
                    continue
                assets.append((str(raw_asset_id), dict(row)))

        return assets

    def _merge_one_pack_asset(
        self,
        *,
        asset_id: str,
        asset_payload: Dict[str, Any],
        pack_id: str,
        namespace: str,
        priority: int,
    ) -> None:
        full_asset_id = _qualify_asset_id(asset_id, namespace)
        if not full_asset_id:
            return

        normalized_pack_id = _normalize_token(pack_id)
        incoming_asset = self._normalize_asset_payload(
            asset_id=full_asset_id,
            raw_asset={
                **dict(asset_payload),
                "source": str(asset_payload.get("source") or f"pack:{normalized_pack_id}"),
            },
            source_pack=normalized_pack_id,
            priority=priority,
        )

        existing = self.assets.get(full_asset_id)
        if not isinstance(existing, dict):
            self.assets[full_asset_id] = incoming_asset
            return

        existing_priority = _safe_int(existing.get("priority"), 0)
        existing_pack = _normalize_token(existing.get("source_pack") or "builtin")
        if priority > existing_priority:
            self.assets[full_asset_id] = incoming_asset
            return

        if priority < existing_priority:
            return

        if priority == existing_priority and existing_pack != normalized_pack_id:
            raise AssetRegistryConflictError(
                f"asset conflict: equal priority collision for '{full_asset_id}' between '{existing_pack}' and '{normalized_pack_id}'"
            )

    def _merge_pack_assets(self) -> None:
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
            priority = _safe_int(getattr(pack_meta, "priority", 0), 0)
            pack_path = Path(str(getattr(pack_meta, "pack_path", "") or ""))
            if not pack_id or not pack_path.exists() or not pack_path.is_dir():
                continue

            assets_path = pack_path / "assets.json"
            payload = _read_json(assets_path)
            if payload is None:
                continue

            for raw_asset_id, raw_asset in self._iter_pack_assets(payload):
                self._merge_one_pack_asset(
                    asset_id=raw_asset_id,
                    asset_payload=raw_asset,
                    pack_id=pack_id,
                    namespace=namespace,
                    priority=priority,
                )

    def _recalculate_counts(self) -> None:
        builtin = 0
        pack_assets = 0
        for row in self.assets.values():
            source_pack = _normalize_token(row.get("source_pack") or "builtin")
            if source_pack == "builtin":
                builtin += 1
            else:
                pack_assets += 1
        self.builtin_asset_count = int(builtin)
        self.pack_asset_count = int(pack_assets)

    def get(self, asset_id: str) -> Optional[Dict[str, Any]]:
        normalized_id = _normalize_token(asset_id)
        if not normalized_id:
            return None
        asset = self.assets.get(normalized_id)
        if asset is None:
            return None
        return dict(asset)

    def list_assets(self) -> List[str]:
        return sorted(self.assets.keys())

    def filter_by_semantics(self, tags: Iterable[str]) -> List[str]:
        normalized_tags = _normalize_tokens(tags)
        if not normalized_tags:
            return self.list_assets()
        selected: List[str] = []
        for asset_id, asset in self.assets.items():
            asset_tags = set(asset.get("semantic_tags") or [])
            if all(tag in asset_tags for tag in normalized_tags):
                selected.append(asset_id)
        return sorted(selected)

    def filter_by_any_semantics(self, tags: Iterable[str]) -> List[str]:
        normalized_tags = _normalize_tokens(tags)
        if not normalized_tags:
            return self.list_assets()
        selected: List[str] = []
        tag_set = set(normalized_tags)
        for asset_id, asset in self.assets.items():
            asset_tags = set(asset.get("semantic_tags") or [])
            if asset_tags.intersection(tag_set):
                selected.append(asset_id)
        return sorted(selected)

    def sources_for_assets(self, asset_ids: Iterable[str]) -> List[str]:
        sources: List[str] = []
        seen = set()
        for raw_id in asset_ids:
            asset = self.get(str(raw_id))
            if not isinstance(asset, dict):
                continue
            source = _normalize_token(asset.get("source") or "unknown")
            if not source or source in seen:
                continue
            seen.add(source)
            sources.append(source)
        return sources
