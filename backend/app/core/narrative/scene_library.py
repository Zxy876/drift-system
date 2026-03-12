from __future__ import annotations

import json
from copy import deepcopy
from functools import lru_cache
from pathlib import Path
from typing import Any, Dict, Iterable, List

from app.core.assets.asset_loader import get_asset_registry
from app.core.semantic.semantic_adapter import resolve_semantics
from app.core.semantic.semantic_registry import semantic_registry_info

from .layout_engine import event_offset_for_fragment, layout_scene_graph
from .scene_graph import SceneGraph


SCENE_CONTENT_DIR = Path(__file__).resolve().parents[2] / "content" / "scenes"
FRAGMENTS_DIR = SCENE_CONTENT_DIR / "fragments"
SEMANTIC_TAGS_FILE = SCENE_CONTENT_DIR / "semantic_tags.json"
FRAGMENT_GRAPH_FILE = SCENE_CONTENT_DIR / "fragment_graph.json"
SEMANTIC_SCORING_FILE = SCENE_CONTENT_DIR / "semantic_scoring.json"


def _safe_int(value: Any, default: int = 0) -> int:
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return int(default)


def _safe_float(value: Any, default: float) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return float(default)


def _normalize_token(raw_value: Any) -> str:
    token = str(raw_value or "").strip().lower()
    if not token:
        return ""
    token = token.replace("-", "_").replace(" ", "_")
    return token.strip("_")


def _normalize_token_list(raw_values: Any) -> List[str]:
    if not isinstance(raw_values, list):
        return []

    normalized: List[str] = []
    seen: set[str] = set()
    for value in raw_values:
        token = _normalize_token(value)
        if not token or token in seen:
            continue
        seen.add(token)
        normalized.append(token)
    return normalized


def _compose_theme_with_hint(story_theme: str, scene_hint: str | None) -> str:
    hint = str(scene_hint or "").strip()
    base_theme = str(story_theme or "").strip()
    if not hint:
        return base_theme
    if not base_theme:
        return hint
    return f"{base_theme} {hint}"


def _default_theme_context(combined_theme: str) -> Dict[str, Any]:
    normalized_theme = str(combined_theme or "").strip()
    return {
        "theme": normalized_theme or None,
        "applied": False,
        "matched_themes": [],
        "allowed_fragments": [],
        "bonus_tags": {},
        "selected_theme": None,
        "theme_registry_version": None,
        "theme_count": 0,
        "builtin_theme_count": 0,
        "pack_theme_count": 0,
        "theme_registry_enabled_packs": [],
    }


def _resolve_theme_context(combined_theme: str) -> Dict[str, Any]:
    context = _default_theme_context(combined_theme)
    try:
        from app.core.themes.theme_loader import get_theme_registry, theme_registry_info

        info = theme_registry_info()
        if isinstance(info, dict):
            context["theme_registry_version"] = info.get("version")
            context["theme_count"] = _safe_int(info.get("theme_count"), 0)
            context["builtin_theme_count"] = _safe_int(info.get("builtin_theme_count"), 0)
            context["pack_theme_count"] = _safe_int(info.get("pack_theme_count"), 0)
            raw_enabled = info.get("enabled_packs") if isinstance(info.get("enabled_packs"), list) else []
            context["theme_registry_enabled_packs"] = [
                _normalize_token(row)
                for row in raw_enabled
                if _normalize_token(row)
            ]

        normalized_theme = str(combined_theme or "").strip()
        if not normalized_theme:
            return context

        registry = get_theme_registry()
        matched = registry.match_theme(normalized_theme) if hasattr(registry, "match_theme") else {}
        if isinstance(matched, dict):
            context["theme"] = matched.get("theme") or context.get("theme")
            context["applied"] = bool(matched.get("applied"))
            context["matched_themes"] = list(matched.get("matched_themes") or [])
            context["allowed_fragments"] = [
                _normalize_token(row)
                for row in (matched.get("allowed_fragments") or [])
                if _normalize_token(row)
            ]
            context["selected_theme"] = matched.get("selected_theme")
            raw_bonus_tags = matched.get("bonus_tags") if isinstance(matched.get("bonus_tags"), dict) else {}
            context["bonus_tags"] = {
                _normalize_token(key): _safe_float(value, 0.0)
                for key, value in raw_bonus_tags.items()
                if _normalize_token(key)
            }
    except Exception:
        return context

    return context


def _theme_allowed_fragment_set(theme_context: Dict[str, Any] | None) -> set[str]:
    if not isinstance(theme_context, dict):
        return set()
    rows = theme_context.get("allowed_fragments") if isinstance(theme_context.get("allowed_fragments"), list) else []
    allowed: set[str] = set()
    for row in rows:
        token = _normalize_token(row)
        if token:
            allowed.add(token)
    return allowed


def _fragment_in_theme_filter(fragment: Dict[str, Any], theme_context: Dict[str, Any] | None) -> bool:
    allowed = _theme_allowed_fragment_set(theme_context)
    if not allowed:
        return True

    fragment_id = _normalize_token(fragment.get("id"))
    if not fragment_id:
        return False
    if fragment_id in allowed:
        return True
    if ":" in fragment_id:
        suffix = fragment_id.split(":", 1)[1]
        if suffix and suffix in allowed:
            return True
    return False


def _scene_hint_variant(scene_hint: str | None) -> str | None:
    hint = str(scene_hint or "").strip().lower()
    if not hint:
        return None

    if any(token in hint for token in ("森林", "林", "forest")):
        return "forest"
    if any(token in hint for token in ("海", "岸", "滩", "coast", "beach", "sea")):
        return "coastal"
    return None


def _build_anchor_payload(anchor_position: Dict[str, Any] | None, *, anchor_ref: str) -> Dict[str, Any]:
    if not isinstance(anchor_position, dict):
        return {
            "mode": "player",
            "ref": anchor_ref,
        }

    return {
        "mode": "absolute",
        "ref": anchor_ref,
        "world": str(anchor_position.get("world") or "world"),
        "x": _safe_float(anchor_position.get("x"), 0.0),
        "y": _safe_float(anchor_position.get("y"), 64.0),
        "z": _safe_float(anchor_position.get("z"), 0.0),
    }


def _read_json_file(path: Path) -> Any:
    if not path.exists() or not path.is_file():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None


def _asset_registry_observability_payload(
    *,
    selected_fragments: List[str],
    semantic_scores: Dict[str, int],
    combined_theme: str,
    theme_context: Dict[str, Any] | None = None,
) -> Dict[str, Any]:
    resolved_theme_context = theme_context if isinstance(theme_context, dict) else _default_theme_context(combined_theme)
    payload: Dict[str, Any] = {
        "asset_registry_version": None,
        "fragment_registry_version": None,
        "fragment_count": 0,
        "builtin_fragment_count": 0,
        "pack_fragment_count": 0,
        "fragment_registry_enabled_packs": [],
        "theme_registry_version": resolved_theme_context.get("theme_registry_version"),
        "theme_count": _safe_int(resolved_theme_context.get("theme_count"), 0),
        "builtin_theme_count": _safe_int(resolved_theme_context.get("builtin_theme_count"), 0),
        "pack_theme_count": _safe_int(resolved_theme_context.get("pack_theme_count"), 0),
        "theme_registry_enabled_packs": list(resolved_theme_context.get("theme_registry_enabled_packs") or []),
        "selected_assets": [],
        "asset_sources": [],
        "asset_selection": {
            "selected_assets": [],
            "candidate_assets": [],
        },
        "fragment_source": [],
        "theme_filter": {
            "theme": resolved_theme_context.get("theme") or (str(combined_theme or "").strip() or None),
            "applied": bool(resolved_theme_context.get("applied")),
            "allowed_fragments": list(resolved_theme_context.get("allowed_fragments") or []),
            "matched_themes": list(resolved_theme_context.get("matched_themes") or []),
            "selected_theme": resolved_theme_context.get("selected_theme"),
        },
    }

    try:
        from app.core.fragments.fragment_loader import fragment_registry_info

        fragment_info = fragment_registry_info()
        if isinstance(fragment_info, dict):
            payload["fragment_registry_version"] = fragment_info.get("version")
            payload["fragment_count"] = _safe_int(fragment_info.get("fragment_count"), 0)
            payload["builtin_fragment_count"] = _safe_int(fragment_info.get("builtin_fragment_count"), 0)
            payload["pack_fragment_count"] = _safe_int(fragment_info.get("pack_fragment_count"), 0)
            raw_enabled_packs = fragment_info.get("enabled_packs") if isinstance(fragment_info.get("enabled_packs"), list) else []
            payload["fragment_registry_enabled_packs"] = [
                _normalize_token(row)
                for row in raw_enabled_packs
                if _normalize_token(row)
            ]
    except Exception:
        payload["fragment_registry_version"] = None
        payload["fragment_count"] = 0
        payload["builtin_fragment_count"] = 0
        payload["pack_fragment_count"] = 0
        payload["fragment_registry_enabled_packs"] = []

    try:
        registry = get_asset_registry()
    except Exception:
        return payload

    payload["asset_registry_version"] = registry.version

    ranked_semantics: List[tuple[str, int]] = []
    for raw_key, raw_value in (semantic_scores or {}).items():
        token = _normalize_token(raw_key)
        amount = _safe_int(raw_value, 0)
        if token and amount > 0:
            ranked_semantics.append((token, amount))

    ranked_semantics.sort(key=lambda item: (-item[1], item[0]))
    semantic_query = [token for token, _ in ranked_semantics[:2]]

    if semantic_query:
        candidate_assets = registry.filter_by_semantics(semantic_query)
        if not candidate_assets:
            candidate_assets = registry.filter_by_any_semantics(semantic_query)
    else:
        candidate_assets = registry.list_assets()

    candidate_assets = list(candidate_assets)[:20]

    selected_assets: List[str] = []
    seen_selected: set[str] = set()
    fragment_source: List[Dict[str, Any]] = []

    for fragment_id in selected_fragments:
        normalized_fragment = _normalize_token(fragment_id)
        if not normalized_fragment or normalized_fragment in seen_selected:
            continue
        asset = registry.get(normalized_fragment)
        if not isinstance(asset, dict):
            continue
        seen_selected.add(normalized_fragment)
        selected_assets.append(normalized_fragment)
        fragment_source.append(
            {
                "asset_id": normalized_fragment,
                "source": str(asset.get("source") or "unknown"),
            }
        )

    if not selected_assets and candidate_assets:
        selected_assets = list(candidate_assets[:5])
        fragment_source = [
            {
                "asset_id": asset_id,
                "source": str((registry.get(asset_id) or {}).get("source") or "unknown"),
            }
            for asset_id in selected_assets
        ]

    asset_sources = registry.sources_for_assets(selected_assets)
    payload["selected_assets"] = selected_assets
    payload["asset_sources"] = list(asset_sources)
    payload["asset_selection"] = {
        "selected_assets": list(selected_assets),
        "candidate_assets": list(candidate_assets),
    }
    payload["fragment_source"] = fragment_source

    theme_filter = payload.get("theme_filter") if isinstance(payload.get("theme_filter"), dict) else {}
    if not isinstance(theme_filter.get("allowed_fragments"), list) or not list(theme_filter.get("allowed_fragments") or []):
        theme_filter["allowed_fragments"] = list(candidate_assets)
    payload["theme_filter"] = theme_filter

    return payload


def _normalize_float_map(raw_values: Any) -> Dict[str, float]:
    if not isinstance(raw_values, dict):
        return {}

    normalized: Dict[str, float] = {}
    for key, value in raw_values.items():
        token = _normalize_token(key)
        if not token:
            continue
        normalized[token] = _safe_float(value, 0.0)
    return normalized


def _normalize_nested_float_map(raw_values: Any) -> Dict[str, Dict[str, float]]:
    if not isinstance(raw_values, dict):
        return {}

    normalized: Dict[str, Dict[str, float]] = {}
    for outer_key, inner_value in raw_values.items():
        outer_token = _normalize_token(outer_key)
        if not outer_token:
            continue
        normalized_inner = _normalize_float_map(inner_value)
        if normalized_inner:
            normalized[outer_token] = normalized_inner
    return normalized


def _default_semantic_scoring_profile() -> Dict[str, Any]:
    return {
        "weights": {
            "priority_weight": 2.0,
            "semantic_weight": 5.0,
            "requirement_weight": 3.0,
            "optional_weight": 1.25,
            "tag_weight": 0.75,
            "root_bonus": 1.5,
            "theme_keyword_bonus": 4.0,
        },
        "resource_weights": {},
        "fragment_semantic_weights": {},
    }


@lru_cache(maxsize=1)
def _load_semantic_scoring_profile() -> Dict[str, Any]:
    default_profile = _default_semantic_scoring_profile()
    raw = _read_json_file(SEMANTIC_SCORING_FILE)
    if not isinstance(raw, dict):
        return default_profile

    weights = dict(default_profile["weights"])
    raw_weights = raw.get("weights")
    if isinstance(raw_weights, dict):
        for key, fallback in weights.items():
            weights[key] = _safe_float(raw_weights.get(key), fallback)

    return {
        "weights": weights,
        "resource_weights": _normalize_float_map(raw.get("resource_weights")),
        "fragment_semantic_weights": _normalize_nested_float_map(raw.get("fragment_semantic_weights")),
    }


@lru_cache(maxsize=1)
def _load_semantic_tags() -> Dict[str, tuple[str, ...]]:
    raw = _read_json_file(SEMANTIC_TAGS_FILE)
    if not isinstance(raw, dict):
        return {}

    normalized: Dict[str, tuple[str, ...]] = {}
    for key, value in raw.items():
        token = _normalize_token(key)
        if not token:
            continue

        if isinstance(value, list):
            tags = _normalize_token_list(value)
        else:
            tags = _normalize_token_list([value])

        if tags:
            normalized[token] = tuple(tags)

    return normalized


@lru_cache(maxsize=1)
def _load_fragment_graph() -> Dict[str, Dict[str, Any]]:
    raw = _read_json_file(FRAGMENT_GRAPH_FILE)
    if not isinstance(raw, dict):
        return {}

    normalized: Dict[str, Dict[str, Any]] = {}
    for key, value in raw.items():
        parent = _normalize_token(key)
        if not parent:
            continue

        if isinstance(value, dict):
            children = _normalize_token_list(value.get("children"))
            max_children = _safe_int(value.get("max_children"), len(children))
        else:
            children = _normalize_token_list(value)
            max_children = len(children)

        normalized[parent] = {
            "children": tuple(children),
            "max_children": max(0, max_children),
        }

    return normalized


@lru_cache(maxsize=1)
def _load_fragments() -> Dict[str, Dict[str, Any]]:
    try:
        from app.core.fragments.fragment_loader import get_fragment_registry

        registry = get_fragment_registry()
        if hasattr(registry, "fragment_map"):
            fragment_map = registry.fragment_map()
            if isinstance(fragment_map, dict):
                return fragment_map
    except Exception:
        return {}

    return {}


def _semantic_resolution_from_resources(resources: Dict[str, int]) -> Dict[str, Any]:
    scores: Dict[str, int] = {}
    resolution: List[Dict[str, Any]] = []
    source_hits: Dict[str, int] = {
        "vanilla_registry": 0,
        "mod_map": 0,
        "fallback": 0,
    }
    semantic_registry_version = None
    semantic_registry_item_count = 0
    semantic_registry_enabled_packs: List[str] = []

    try:
        registry_info = semantic_registry_info()
        if isinstance(registry_info, dict):
            semantic_registry_version = registry_info.get("version")
            semantic_registry_item_count = _safe_int(registry_info.get("semantic_item_count"), 0)
            raw_enabled = registry_info.get("enabled_packs") if isinstance(registry_info.get("enabled_packs"), list) else []
            semantic_registry_enabled_packs = [
                _normalize_token(row)
                for row in raw_enabled
                if _normalize_token(row)
            ]
    except Exception:
        semantic_registry_version = None
        semantic_registry_item_count = 0
        semantic_registry_enabled_packs = []

    for raw_key, raw_value in resources.items():
        token = _normalize_token(raw_key)
        amount = _safe_int(raw_value, 0)
        if not token or amount <= 0:
            continue

        try:
            resolved = resolve_semantics(token)
        except Exception:
            resolved = {
                "item_id": token,
                "semantic_tags": [token],
                "source": "fallback",
                "adapter_hit": False,
            }

        tags = _normalize_token_list(resolved.get("semantic_tags"))
        if not tags:
            tags = [token]

        source = str(resolved.get("source") or "fallback").strip().lower() or "fallback"
        if source not in source_hits:
            source_hits[source] = 0
        source_hits[source] = int(source_hits.get(source, 0)) + 1

        adapter_hit = bool(resolved.get("adapter_hit")) and source != "fallback"
        resolution.append(
            {
                "item": token,
                "semantic_tags": list(tags),
                "source": source,
                "adapter_hit": adapter_hit,
            }
        )

        for tag in tags:
            if not tag:
                continue
            scores[tag] = int(scores.get(tag, 0)) + amount

    adapter_hit_count = 0
    for row in resolution:
        if bool(row.get("adapter_hit")):
            adapter_hit_count += 1

    return {
        "semantic_scores": scores,
        "semantic_resolution": resolution,
        "semantic_source": source_hits,
        "semantic_adapter_hits": adapter_hit_count,
        "semantic_registry_version": semantic_registry_version,
        "semantic_registry_item_count": semantic_registry_item_count,
        "semantic_registry_enabled_packs": semantic_registry_enabled_packs,
    }


def _semantic_scores_from_resources(resources: Dict[str, int]) -> Dict[str, int]:
    payload = _semantic_resolution_from_resources(resources)
    return dict(payload.get("semantic_scores") or {})


def _fragment_theme_allowed(fragment: Dict[str, Any], combined_theme: str) -> bool:
    keywords = fragment.get("theme_keywords") or []
    if not isinstance(keywords, list) or not keywords:
        return True

    theme_text = str(combined_theme or "")
    if not theme_text:
        return False

    return any(str(keyword) in theme_text for keyword in keywords if str(keyword).strip())


def _fragment_missing_requirements(fragment: Dict[str, Any], semantic_scores: Dict[str, int]) -> List[str]:
    missing: List[str] = []
    requires = fragment.get("requires")
    if not isinstance(requires, list):
        return missing

    for required in requires:
        token = _normalize_token(required)
        if not token:
            continue
        if int(semantic_scores.get(token, 0)) <= 0:
            missing.append(token)
    return missing


def _fragment_requirements_met(fragment: Dict[str, Any], semantic_scores: Dict[str, int]) -> bool:
    return len(_fragment_missing_requirements(fragment, semantic_scores)) == 0


def _resource_weight(token: str, profile: Dict[str, Any]) -> float:
    resource_weights = profile.get("resource_weights")
    if not isinstance(resource_weights, dict):
        return 1.0
    return _safe_float(resource_weights.get(token), 1.0)


def _fragment_theme_score(
    fragment: Dict[str, Any],
    combined_theme: str,
    *,
    theme_keyword_bonus: float,
    theme_context: Dict[str, Any] | None = None,
) -> float:
    score = 0.0

    keywords = fragment.get("theme_keywords")
    theme_text = str(combined_theme or "")
    if isinstance(keywords, list) and keywords and theme_text:
        matched = 0
        for keyword in keywords:
            keyword_text = str(keyword).strip()
            if keyword_text and keyword_text in theme_text:
                matched += 1
        score += float(matched) * float(theme_keyword_bonus)

    bonus_tags = theme_context.get("bonus_tags") if isinstance(theme_context, dict) and isinstance(theme_context.get("bonus_tags"), dict) else {}
    if isinstance(bonus_tags, dict):
        for tag in fragment.get("tags") or []:
            token = _normalize_token(tag)
            if not token:
                continue
            score += _safe_float(bonus_tags.get(token), 0.0)

    return score


def _fragment_semantic_score(
    fragment: Dict[str, Any],
    *,
    fragment_id: str,
    semantic_scores: Dict[str, int],
    profile: Dict[str, Any],
) -> float:
    score = 0.0

    fragment_weights = profile.get("fragment_semantic_weights")
    weighted_tags: Dict[str, float] = {}
    if isinstance(fragment_weights, dict):
        weighted_tags = fragment_weights.get(fragment_id) or {}

    if isinstance(weighted_tags, dict) and weighted_tags:
        for tag, tag_weight in weighted_tags.items():
            token = _normalize_token(tag)
            if not token:
                continue
            semantic_amount = int(semantic_scores.get(token, 0))
            if semantic_amount <= 0:
                continue
            score += float(semantic_amount) * _safe_float(tag_weight, 0.0) * _resource_weight(token, profile)
        return score

    for tag in fragment.get("tags") or []:
        token = _normalize_token(tag)
        if not token:
            continue
        semantic_amount = int(semantic_scores.get(token, 0))
        if semantic_amount <= 0:
            continue
        score += float(semantic_amount) * _resource_weight(token, profile)

    return score


def _fragment_reason_tokens(
    fragment: Dict[str, Any],
    *,
    fragment_id: str,
    semantic_scores: Dict[str, int],
    combined_theme: str,
    profile: Dict[str, Any],
    theme_context: Dict[str, Any] | None = None,
) -> List[str]:
    tokens: List[str] = []
    seen: set[str] = set()

    def _push(token: str) -> None:
        normalized = _normalize_token(token)
        if not normalized or normalized in seen:
            return
        seen.add(normalized)
        tokens.append(normalized)

    weighted_semantics = profile.get("fragment_semantic_weights") if isinstance(profile, dict) else {}
    weighted_map = {}
    if isinstance(weighted_semantics, dict):
        weighted_map = weighted_semantics.get(fragment_id) or {}

    if isinstance(weighted_map, dict) and weighted_map:
        ranked = []
        for tag, tag_weight in weighted_map.items():
            token = _normalize_token(tag)
            if not token:
                continue
            amount = int(semantic_scores.get(token, 0))
            if amount <= 0:
                continue
            ranked.append((amount * _safe_float(tag_weight, 0.0), token))
        ranked.sort(key=lambda item: (-item[0], item[1]))
        for _, token in ranked[:4]:
            _push(token)

    for required in fragment.get("requires") or []:
        token = _normalize_token(required)
        if token and int(semantic_scores.get(token, 0)) > 0:
            _push(token)

    for optional in fragment.get("optional_resources") or []:
        token = _normalize_token(optional)
        if token and int(semantic_scores.get(token, 0)) > 0:
            _push(token)

    for tag in fragment.get("tags") or []:
        token = _normalize_token(tag)
        if token and int(semantic_scores.get(token, 0)) > 0:
            _push(token)

    keywords = fragment.get("theme_keywords")
    if isinstance(keywords, list) and keywords and combined_theme:
        for keyword in keywords:
            keyword_text = str(keyword).strip()
            if keyword_text and keyword_text in combined_theme:
                _push("theme")
                break

    if bool((theme_context or {}).get("applied")) and _fragment_in_theme_filter(fragment, theme_context):
        _push("theme")

    return tokens


def _fragment_reason_text(
    fragment: Dict[str, Any],
    *,
    fragment_id: str,
    semantic_scores: Dict[str, int],
    combined_theme: str,
    profile: Dict[str, Any],
    theme_context: Dict[str, Any] | None = None,
) -> str:
    tokens = _fragment_reason_tokens(
        fragment,
        fragment_id=fragment_id,
        semantic_scores=semantic_scores,
        combined_theme=combined_theme,
        profile=profile,
        theme_context=theme_context,
    )
    if not tokens:
        return "priority"
    return " + ".join(tokens)


def _fragment_score_details(
    fragment: Dict[str, Any],
    semantic_scores: Dict[str, int],
    combined_theme: str,
    *,
    theme_context: Dict[str, Any] | None = None,
) -> Dict[str, Any]:
    profile = _load_semantic_scoring_profile()
    weights = profile.get("weights") or {}

    priority_weight = _safe_float(weights.get("priority_weight"), 2.0)
    semantic_weight = _safe_float(weights.get("semantic_weight"), 5.0)
    requirement_weight = _safe_float(weights.get("requirement_weight"), 3.0)
    optional_weight = _safe_float(weights.get("optional_weight"), 1.25)
    tag_weight = _safe_float(weights.get("tag_weight"), 0.75)
    root_bonus = _safe_float(weights.get("root_bonus"), 1.5)
    theme_keyword_bonus = _safe_float(weights.get("theme_keyword_bonus"), 4.0)

    fragment_id = _normalize_token(fragment.get("id"))
    score = float(_safe_int(fragment.get("priority"), 0)) * priority_weight
    if bool(fragment.get("root")):
        score += root_bonus

    semantic_score = _fragment_semantic_score(
        fragment,
        fragment_id=fragment_id,
        semantic_scores=semantic_scores,
        profile=profile,
    )
    score += semantic_score * semantic_weight

    for required in fragment.get("requires") or []:
        token = _normalize_token(required)
        if not token:
            continue
        semantic_amount = int(semantic_scores.get(token, 0))
        if semantic_amount > 0:
            score += float(semantic_amount) * requirement_weight * _resource_weight(token, profile)

    for optional in fragment.get("optional_resources") or []:
        token = _normalize_token(optional)
        if not token:
            continue
        semantic_amount = int(semantic_scores.get(token, 0))
        if semantic_amount > 0:
            score += float(semantic_amount) * optional_weight * _resource_weight(token, profile)

    for tag in fragment.get("tags") or []:
        token = _normalize_token(tag)
        if not token:
            continue
        semantic_amount = int(semantic_scores.get(token, 0))
        if semantic_amount > 0:
            score += float(semantic_amount) * tag_weight * _resource_weight(token, profile)

    score += _fragment_theme_score(
        fragment,
        combined_theme,
        theme_keyword_bonus=theme_keyword_bonus,
        theme_context=theme_context,
    )

    return {
        "score": int(round(score * 1000)),
        "reason": _fragment_reason_text(
            fragment,
            fragment_id=fragment_id,
            semantic_scores=semantic_scores,
            combined_theme=combined_theme,
            profile=profile,
            theme_context=theme_context,
        ),
    }


def _fragment_score(
    fragment: Dict[str, Any],
    semantic_scores: Dict[str, int],
    combined_theme: str,
    *,
    theme_context: Dict[str, Any] | None = None,
) -> int:
    return int(
        _fragment_score_details(
            fragment,
            semantic_scores,
            combined_theme,
            theme_context=theme_context,
        ).get("score", 0)
    )


def _blocked_reason(
    fragment: Dict[str, Any],
    semantic_scores: Dict[str, int],
    combined_theme: str,
    *,
    theme_context: Dict[str, Any] | None = None,
) -> str:
    missing = _fragment_missing_requirements(fragment, semantic_scores)
    if missing:
        return "missing_required: " + ", ".join(missing)
    if not _fragment_in_theme_filter(fragment, theme_context):
        return "theme_filter"
    if not _fragment_theme_allowed(fragment, combined_theme):
        return "theme_mismatch"
    return "blocked"


def _candidate_score_entry(
    fragment: Dict[str, Any],
    *,
    semantic_scores: Dict[str, int],
    combined_theme: str,
    theme_context: Dict[str, Any] | None = None,
) -> Dict[str, Any]:
    fragment_id = _normalize_token(fragment.get("id"))
    details = _fragment_score_details(
        fragment,
        semantic_scores,
        combined_theme,
        theme_context=theme_context,
    )
    score = int(details.get("score", 0))
    reason = str(details.get("reason") or "priority")
    return {
        "fragment": fragment_id,
        "score": round(float(score) / 1000.0, 3),
        "_score_int": score,
        "reason": reason,
    }


def _choose_root_fragment_with_debug(
    fragments: Dict[str, Dict[str, Any]],
    *,
    semantic_scores: Dict[str, int],
    combined_theme: str,
    theme_context: Dict[str, Any] | None = None,
) -> Dict[str, Any]:
    root_pool = [fragment for fragment in fragments.values() if bool(fragment.get("root"))]

    def _evaluate(pool: List[Dict[str, Any]], stage: str) -> tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
        candidates: List[Dict[str, Any]] = []
        blocked: List[Dict[str, Any]] = []
        for fragment in pool:
            fragment_id = _normalize_token(fragment.get("id"))
            if not fragment_id:
                continue

            reason = _blocked_reason(
                fragment,
                semantic_scores,
                combined_theme,
                theme_context=theme_context,
            )
            if reason != "blocked":
                blocked.append(
                    {
                        "fragment": fragment_id,
                        "stage": stage,
                        "reason": reason,
                    }
                )
                continue

            candidates.append(
                _candidate_score_entry(
                    fragment,
                    semantic_scores=semantic_scores,
                    combined_theme=combined_theme,
                    theme_context=theme_context,
                )
            )
        return candidates, blocked

    selection_stage = "root_candidates"
    candidate_scores, blocked = _evaluate(root_pool, "root")

    if not candidate_scores:
        selection_stage = "fallback_all"
        fallback_candidates, fallback_blocked = _evaluate(list(fragments.values()), "fallback")
        candidate_scores = fallback_candidates
        blocked.extend(fallback_blocked)

    if not candidate_scores:
        return {
            "selected_root": None,
            "candidate_scores": [],
            "blocked": blocked,
            "reasons": {
                "selection_stage": selection_stage,
                "selected_root": "no_candidate",
            },
        }

    candidate_scores.sort(key=lambda item: (-int(item.get("_score_int", 0)), str(item.get("fragment") or "")))
    selected = candidate_scores[0]

    formatted_scores: List[Dict[str, Any]] = []
    for item in candidate_scores:
        formatted_scores.append(
            {
                "fragment": item.get("fragment"),
                "score": item.get("score"),
                "reason": item.get("reason"),
            }
        )

    return {
        "selected_root": str(selected.get("fragment") or ""),
        "candidate_scores": formatted_scores,
        "blocked": blocked,
        "reasons": {
            "selection_stage": selection_stage,
            "selected_root": str(selected.get("reason") or "priority"),
        },
    }


def _choose_root_fragment(
    fragments: Dict[str, Dict[str, Any]],
    *,
    semantic_scores: Dict[str, int],
    combined_theme: str,
    theme_context: Dict[str, Any] | None = None,
) -> str | None:
    debug_result = _choose_root_fragment_with_debug(
        fragments,
        semantic_scores=semantic_scores,
        combined_theme=combined_theme,
        theme_context=theme_context,
    )
    selected_root = _normalize_token(debug_result.get("selected_root"))
    return selected_root or None


def _graph_children_spec(
    fragment_id: str,
    fragment: Dict[str, Any],
    graph: Dict[str, Dict[str, Any]],
) -> tuple[List[str], int]:
    graph_entry = graph.get(fragment_id)
    if isinstance(graph_entry, dict):
        children = list(graph_entry.get("children") or tuple())
        max_children = _safe_int(graph_entry.get("max_children"), len(children))
        return children, max(0, max_children)

    fallback_children = [_normalize_token(item) for item in (fragment.get("connections") or [])]
    normalized: List[str] = []
    seen: set[str] = set()
    for child in fallback_children:
        if not child or child in seen:
            continue
        seen.add(child)
        normalized.append(child)
    return normalized, len(normalized)


def _expand_scene_graph_with_debug(
    root_fragment: str,
    *,
    fragments: Dict[str, Dict[str, Any]],
    semantic_scores: Dict[str, int],
    combined_theme: str,
    theme_context: Dict[str, Any] | None = None,
) -> tuple[SceneGraph, List[str], List[Dict[str, Any]]]:
    graph_spec = _load_fragment_graph()
    scene_graph = SceneGraph(root=root_fragment)
    scene_graph.add_node(root_fragment)

    blocked: List[Dict[str, Any]] = []
    root = fragments.get(root_fragment)
    if not isinstance(root, dict):
        blocked.append(
            {
                "fragment": root_fragment,
                "stage": "expand",
                "reason": "missing_fragment",
            }
        )
        return scene_graph, [], blocked

    child_ids, max_children = _graph_children_spec(root_fragment, root, graph_spec)
    candidate_children: List[Dict[str, Any]] = []

    for child_id in child_ids:
        child_fragment = fragments.get(child_id)
        if not isinstance(child_fragment, dict):
            blocked.append(
                {
                    "fragment": child_id,
                    "stage": "expand",
                    "reason": "missing_fragment",
                }
            )
            continue

        reason = _blocked_reason(
            child_fragment,
            semantic_scores,
            combined_theme,
            theme_context=theme_context,
        )
        if reason != "blocked":
            blocked.append(
                {
                    "fragment": child_id,
                    "stage": "expand",
                    "reason": reason,
                }
            )
            continue

        candidate_children.append(
            _candidate_score_entry(
                child_fragment,
                semantic_scores=semantic_scores,
                combined_theme=combined_theme,
                theme_context=theme_context,
            )
        )

    candidate_children.sort(key=lambda item: (-int(item.get("_score_int", 0)), str(item.get("fragment") or "")))

    if max_children <= 0:
        selected_rows: List[Dict[str, Any]] = []
    else:
        selected_rows = candidate_children[:max_children]

    if max_children >= 0 and len(candidate_children) > len(selected_rows):
        for row in candidate_children[len(selected_rows) :]:
            blocked.append(
                {
                    "fragment": str(row.get("fragment") or ""),
                    "stage": "expand",
                    "reason": "pruned_by_max_children",
                }
            )

    selected_children: List[str] = []
    for row in selected_rows:
        child = _normalize_token(row.get("fragment"))
        if not child:
            continue
        scene_graph.add_edge(root_fragment, child)
        selected_children.append(child)

    return scene_graph, selected_children, blocked


def _expand_fragment_graph_with_debug(
    root_fragment: str,
    *,
    fragments: Dict[str, Dict[str, Any]],
    semantic_scores: Dict[str, int],
    combined_theme: str,
    theme_context: Dict[str, Any] | None = None,
) -> tuple[List[str], List[Dict[str, Any]]]:
    scene_graph, _, blocked = _expand_scene_graph_with_debug(
        root_fragment,
        fragments=fragments,
        semantic_scores=semantic_scores,
        combined_theme=combined_theme,
        theme_context=theme_context,
    )
    return list(scene_graph.nodes), blocked


def _expand_fragment_graph(
    root_fragment: str,
    *,
    fragments: Dict[str, Dict[str, Any]],
    semantic_scores: Dict[str, int],
    combined_theme: str,
    theme_context: Dict[str, Any] | None = None,
) -> List[str]:
    selected, _ = _expand_fragment_graph_with_debug(
        root_fragment,
        fragments=fragments,
        semantic_scores=semantic_scores,
        combined_theme=combined_theme,
        theme_context=theme_context,
    )
    return selected


def select_fragments_with_debug(
    resources: Dict[str, int],
    story_theme: str,
    scene_hint: str | None = None,
) -> Dict[str, Any]:
    combined_theme = _compose_theme_with_hint(str(story_theme or ""), scene_hint)
    theme_context = _resolve_theme_context(combined_theme)
    theme_filter_payload = {
        "theme": theme_context.get("theme"),
        "applied": bool(theme_context.get("applied")),
        "allowed_fragments": list(theme_context.get("allowed_fragments") or []),
        "matched_themes": list(theme_context.get("matched_themes") or []),
        "selected_theme": theme_context.get("selected_theme"),
    }

    normalized_resources: Dict[str, int] = {}
    for key, value in (resources or {}).items():
        token = _normalize_token(key)
        amount = _safe_int(value, 0)
        if token and amount > 0:
            normalized_resources[token] = amount

    semantic_payload = _semantic_resolution_from_resources(normalized_resources)
    semantic_scores = dict(semantic_payload.get("semantic_scores") or {})
    semantic_resolution = list(semantic_payload.get("semantic_resolution") or [])
    semantic_source = dict(semantic_payload.get("semantic_source") or {})
    semantic_adapter_hits = _safe_int(semantic_payload.get("semantic_adapter_hits"), 0)
    semantic_registry_version = semantic_payload.get("semantic_registry_version")
    semantic_registry_item_count = _safe_int(semantic_payload.get("semantic_registry_item_count"), 0)
    semantic_registry_enabled_packs = list(semantic_payload.get("semantic_registry_enabled_packs") or [])

    fragments = _load_fragments()
    if not fragments:
        debug_payload = {
            "selected_root": None,
            "candidate_scores": [],
            "selected_children": [],
            "blocked": [],
            "reasons": {"selected_root": "no_fragments"},
            "semantic_scores": dict(semantic_scores),
            "semantic_resolution": list(semantic_resolution),
            "semantic_source": dict(semantic_source),
            "semantic_adapter_hits": semantic_adapter_hits,
            "semantic_registry_version": semantic_registry_version,
            "semantic_registry_item_count": semantic_registry_item_count,
            "semantic_registry_enabled_packs": list(semantic_registry_enabled_packs),
            "theme_registry_version": theme_context.get("theme_registry_version"),
            "theme_count": _safe_int(theme_context.get("theme_count"), 0),
            "builtin_theme_count": _safe_int(theme_context.get("builtin_theme_count"), 0),
            "pack_theme_count": _safe_int(theme_context.get("pack_theme_count"), 0),
            "theme_registry_enabled_packs": list(theme_context.get("theme_registry_enabled_packs") or []),
            "theme_filter": dict(theme_filter_payload),
        }
        debug_payload.update(
            _asset_registry_observability_payload(
                selected_fragments=[],
                semantic_scores=semantic_scores,
                combined_theme=combined_theme,
                theme_context=theme_context,
            )
        )
        return {
            "fragments": [],
            "scene_graph": {
                "root": "",
                "nodes": [],
                "edges": [],
            },
            "layout": {
                "strategy": "radial_v1",
                "root": "",
                "positions": {},
            },
            "debug": debug_payload,
        }

    root_debug = _choose_root_fragment_with_debug(
        fragments,
        semantic_scores=semantic_scores,
        combined_theme=combined_theme,
        theme_context=theme_context,
    )
    root_fragment = _normalize_token(root_debug.get("selected_root"))
    if not root_fragment:
        debug_payload = {
            "selected_root": None,
            "candidate_scores": list(root_debug.get("candidate_scores") or []),
            "selected_children": [],
            "blocked": list(root_debug.get("blocked") or []),
            "reasons": dict(root_debug.get("reasons") or {}),
            "semantic_scores": dict(semantic_scores),
            "semantic_resolution": list(semantic_resolution),
            "semantic_source": dict(semantic_source),
            "semantic_adapter_hits": semantic_adapter_hits,
            "semantic_registry_version": semantic_registry_version,
            "semantic_registry_item_count": semantic_registry_item_count,
            "semantic_registry_enabled_packs": list(semantic_registry_enabled_packs),
            "theme_registry_version": theme_context.get("theme_registry_version"),
            "theme_count": _safe_int(theme_context.get("theme_count"), 0),
            "builtin_theme_count": _safe_int(theme_context.get("builtin_theme_count"), 0),
            "pack_theme_count": _safe_int(theme_context.get("pack_theme_count"), 0),
            "theme_registry_enabled_packs": list(theme_context.get("theme_registry_enabled_packs") or []),
            "theme_filter": dict(theme_filter_payload),
        }
        debug_payload.update(
            _asset_registry_observability_payload(
                selected_fragments=[],
                semantic_scores=semantic_scores,
                combined_theme=combined_theme,
                theme_context=theme_context,
            )
        )
        return {
            "fragments": [],
            "scene_graph": {
                "root": "",
                "nodes": [],
                "edges": [],
            },
            "layout": {
                "strategy": "radial_v1",
                "root": "",
                "positions": {},
            },
            "debug": debug_payload,
        }

    scene_graph, selected_children, expansion_blocked = _expand_scene_graph_with_debug(
        root_fragment,
        fragments=fragments,
        semantic_scores=semantic_scores,
        combined_theme=combined_theme,
        theme_context=theme_context,
    )
    selected = list(scene_graph.nodes)
    layout = layout_scene_graph(scene_graph, fragments=fragments)

    blocked_entries = list(root_debug.get("blocked") or []) + list(expansion_blocked or [])
    deduped_blocked: List[Dict[str, Any]] = []
    seen_blocked: set[str] = set()
    for row in blocked_entries:
        if not isinstance(row, dict):
            continue
        dedupe_key = json.dumps(row, ensure_ascii=False, sort_keys=True)
        if dedupe_key in seen_blocked:
            continue
        seen_blocked.add(dedupe_key)
        deduped_blocked.append(dict(row))

    debug_payload = {
        "selected_root": root_fragment,
        "candidate_scores": list(root_debug.get("candidate_scores") or []),
        "selected_children": list(selected_children),
        "blocked": deduped_blocked,
        "reasons": dict(root_debug.get("reasons") or {}),
        "semantic_scores": dict(semantic_scores),
        "semantic_resolution": list(semantic_resolution),
        "semantic_source": dict(semantic_source),
        "semantic_adapter_hits": semantic_adapter_hits,
        "semantic_registry_version": semantic_registry_version,
        "semantic_registry_item_count": semantic_registry_item_count,
        "semantic_registry_enabled_packs": list(semantic_registry_enabled_packs),
        "theme_registry_version": theme_context.get("theme_registry_version"),
        "theme_count": _safe_int(theme_context.get("theme_count"), 0),
        "builtin_theme_count": _safe_int(theme_context.get("builtin_theme_count"), 0),
        "pack_theme_count": _safe_int(theme_context.get("pack_theme_count"), 0),
        "theme_registry_enabled_packs": list(theme_context.get("theme_registry_enabled_packs") or []),
        "theme_filter": dict(theme_filter_payload),
    }
    debug_payload.update(
        _asset_registry_observability_payload(
            selected_fragments=selected,
            semantic_scores=semantic_scores,
            combined_theme=combined_theme,
            theme_context=theme_context,
        )
    )

    return {
        "fragments": selected,
        "scene_graph": scene_graph.to_dict(),
        "layout": layout,
        "debug": debug_payload,
    }


def select_fragments(resources: Dict[str, int], story_theme: str, scene_hint: str | None = None) -> List[str]:
    selection = select_fragments_with_debug(resources, story_theme, scene_hint=scene_hint)
    return list(selection.get("fragments") or [])


def get_fragment_map() -> Dict[str, Dict[str, Any]]:
    return deepcopy(_load_fragments())


def _fallback_events_from_fragment(fragment: Dict[str, Any]) -> List[Dict[str, Any]]:
    fragment_id = _normalize_token(fragment.get("id")) or "scene"
    events: List[Dict[str, Any]] = []

    for index, structure in enumerate(fragment.get("structures") or [], start=1):
        if not isinstance(structure, dict):
            continue

        structure_type = _normalize_token(structure.get("type"))
        template = str(structure.get("template") or "").strip()
        event_id = str(structure.get("event_id") or f"spawn_{fragment_id}_{index}")
        anchor_ref = str(structure.get("anchor_ref") or "player")

        if structure_type in {"fire", "campfire"}:
            events.append(
                {
                    "event_id": event_id,
                    "type": "spawn_block",
                    "anchor_ref": anchor_ref,
                    "data": {
                        "block": str(structure.get("block") or "campfire"),
                    },
                }
            )
            continue

        events.append(
            {
                "event_id": event_id,
                "type": "spawn_structure",
                "anchor_ref": anchor_ref,
                "data": {
                    "template": template or structure_type or fragment_id,
                },
            }
        )

    for npc in fragment.get("npcs") or []:
        if not isinstance(npc, dict):
            continue
        npc_id = _normalize_token(npc.get("id")) or "npc"
        events.append(
            {
                "event_id": str(npc.get("event_id") or f"spawn_{npc_id}"),
                "type": "spawn_npc",
                "anchor_ref": str(npc.get("anchor_ref") or "camp_edge"),
                "data": {
                    "npc_template": str(npc.get("template") or npc_id),
                },
            }
        )

    return events


def build_event_plan(
    fragments: Iterable[str],
    *,
    anchor_position: Dict[str, Any] | None = None,
    scene_hint: str | None = None,
    layout: Dict[str, Any] | None = None,
) -> List[Dict[str, Any]]:
    fragment_map = _load_fragments()

    events: List[Dict[str, Any]] = []
    normalized_hint = str(scene_hint or "").strip() or None
    hint_variant = _scene_hint_variant(normalized_hint)

    for fragment_name in fragments:
        fragment_id = _normalize_token(fragment_name)
        if not fragment_id:
            continue

        fragment = fragment_map.get(fragment_id)
        if not isinstance(fragment, dict):
            continue

        blueprints = fragment.get("events")
        if not isinstance(blueprints, list) or not blueprints:
            blueprints = _fallback_events_from_fragment(fragment)

        for index, blueprint in enumerate(blueprints, start=1):
            if not isinstance(blueprint, dict):
                continue

            event_id = str(blueprint.get("event_id") or f"spawn_{fragment_id}_{index}")
            event_type = str(blueprint.get("type") or "spawn_structure")
            anchor_ref = str(blueprint.get("anchor_ref") or "player")
            data = deepcopy(blueprint.get("data") or {})

            if normalized_hint is not None:
                data["scene_hint"] = normalized_hint
            if hint_variant is not None:
                data["scene_variant"] = hint_variant

            base_offset = event_offset_for_fragment(fragment_id, layout)
            blueprint_offset = blueprint.get("offset")
            if isinstance(blueprint_offset, dict):
                event_offset = {
                    "dx": _safe_float(blueprint_offset.get("dx"), base_offset["dx"]),
                    "dy": _safe_float(blueprint_offset.get("dy"), base_offset["dy"]),
                    "dz": _safe_float(blueprint_offset.get("dz"), base_offset["dz"]),
                }
            else:
                event_offset = dict(base_offset)

            events.append(
                {
                    "event_id": event_id,
                    "type": event_type,
                    "text": event_id,
                    "anchor": _build_anchor_payload(anchor_position, anchor_ref=anchor_ref),
                    "offset": event_offset,
                    "data": data,
                }
            )

    return events
