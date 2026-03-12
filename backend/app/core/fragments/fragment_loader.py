from __future__ import annotations

from functools import lru_cache
from typing import Any, Dict

from .fragment_registry import FragmentRegistry


@lru_cache(maxsize=1)
def get_fragment_registry() -> FragmentRegistry:
    return FragmentRegistry()


def reset_fragment_registry_cache() -> None:
    get_fragment_registry.cache_clear()


def fragment_registry_info() -> Dict[str, Any]:
    try:
        registry = get_fragment_registry()
        return {
            "version": registry.version,
            "fragment_count": len(registry.list_fragments()),
            "builtin_fragment_count": int(getattr(registry, "builtin_fragment_count", 0)),
            "pack_fragment_count": int(getattr(registry, "pack_fragment_count", 0)),
            "enabled_packs": list(getattr(registry, "enabled_packs", [])),
        }
    except Exception:
        return {
            "version": None,
            "fragment_count": 0,
            "builtin_fragment_count": 0,
            "pack_fragment_count": 0,
            "enabled_packs": [],
        }
