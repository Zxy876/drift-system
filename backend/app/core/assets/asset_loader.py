from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Any, Dict

from .asset_registry import AssetRegistry


REGISTRY_FILE = (
    Path(__file__).resolve().parents[2] / "content" / "assets" / "asset_registry.json"
)


@lru_cache(maxsize=1)
def get_asset_registry() -> AssetRegistry:
    return AssetRegistry(REGISTRY_FILE)


def reset_asset_registry_cache() -> None:
    get_asset_registry.cache_clear()


def asset_registry_info() -> Dict[str, Any]:
    try:
        registry = get_asset_registry()
        return {
            "version": registry.version,
            "asset_count": len(registry.list_assets()),
            "builtin_asset_count": int(getattr(registry, "builtin_asset_count", 0)),
            "pack_asset_count": int(getattr(registry, "pack_asset_count", 0)),
            "enabled_packs": list(getattr(registry, "enabled_packs", [])),
        }
    except Exception:
        return {
            "version": None,
            "asset_count": 0,
            "builtin_asset_count": 0,
            "pack_asset_count": 0,
            "enabled_packs": [],
        }
