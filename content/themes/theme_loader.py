from __future__ import annotations

from functools import lru_cache
from typing import Any, Dict

from .theme_registry import ThemeRegistry


@lru_cache(maxsize=1)
def get_theme_registry() -> ThemeRegistry:
    return ThemeRegistry()


def reset_theme_registry_cache() -> None:
    get_theme_registry.cache_clear()


def theme_registry_info() -> Dict[str, Any]:
    try:
        registry = get_theme_registry()
        return {
            "version": registry.version,
            "theme_count": len(registry.list_themes()),
            "builtin_theme_count": int(getattr(registry, "builtin_theme_count", 0)),
            "pack_theme_count": int(getattr(registry, "pack_theme_count", 0)),
            "enabled_packs": list(getattr(registry, "enabled_packs", [])),
        }
    except Exception:
        return {
            "version": None,
            "theme_count": 0,
            "builtin_theme_count": 0,
            "pack_theme_count": 0,
            "enabled_packs": [],
        }
