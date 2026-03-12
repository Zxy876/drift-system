from __future__ import annotations

from threading import RLock

from .semantic_registry import get_semantic_registry, normalize_semantic_item_id
from .semantic_types import SemanticResult


_semantic_cache: dict[str, SemanticResult] = {}
_semantic_cache_lock = RLock()


def _copy_result(result: SemanticResult) -> SemanticResult:
    return {
        "item_id": str(result.get("item_id") or ""),
        "semantic_tags": list(result.get("semantic_tags") or []),
        "source": str(result.get("source") or "fallback"),
        "adapter_hit": bool(result.get("adapter_hit")),
    }


def _cache_get(item_id: str) -> SemanticResult | None:
    with _semantic_cache_lock:
        cached = _semantic_cache.get(item_id)
    if not isinstance(cached, dict):
        return None
    return _copy_result(cached)


def _cache_set(item_id: str, result: SemanticResult) -> None:
    if not item_id:
        return
    stored = _copy_result(result)
    with _semantic_cache_lock:
        _semantic_cache[item_id] = stored


def reset_semantic_cache() -> None:
    with _semantic_cache_lock:
        _semantic_cache.clear()


def resolve_semantics(item_id: str) -> SemanticResult:
    normalized_item = normalize_semantic_item_id(item_id)
    if not normalized_item:
        return {
            "item_id": "",
            "semantic_tags": ["generic"],
            "source": "fallback",
            "adapter_hit": False,
        }

    cached = _cache_get(normalized_item)
    if cached is not None:
        return cached

    registry = get_semantic_registry()

    resolved = registry.resolve(normalized_item) if hasattr(registry, "resolve") else None
    if isinstance(resolved, dict):
        source = str(resolved.get("source") or "fallback")
        tags = resolved.get("semantic_tags") if isinstance(resolved.get("semantic_tags"), list) else []
        if tags:
            result: SemanticResult = {
                "item_id": normalized_item,
                "semantic_tags": list(tags),
                "source": source,
                "adapter_hit": source != "fallback",
            }
            _cache_set(normalized_item, result)
            return _copy_result(result)

    vanilla_tags = registry.get_vanilla(normalized_item)
    if vanilla_tags:
        result: SemanticResult = {
            "item_id": normalized_item,
            "semantic_tags": list(vanilla_tags),
            "source": "vanilla_registry",
            "adapter_hit": True,
        }
        _cache_set(normalized_item, result)
        return _copy_result(result)

    mod_tags = registry.get_mod(normalized_item)
    if mod_tags:
        result = {
            "item_id": normalized_item,
            "semantic_tags": list(mod_tags),
            "source": "mod_map",
            "adapter_hit": True,
        }
        _cache_set(normalized_item, result)
        return _copy_result(result)

    result = {
        "item_id": normalized_item,
        "semantic_tags": [normalized_item],
        "source": "fallback",
        "adapter_hit": False,
    }
    _cache_set(normalized_item, result)
    return _copy_result(result)
