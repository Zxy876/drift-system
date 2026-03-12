from __future__ import annotations

import json
import logging
import os
from typing import Any, Dict

from .scene_library import build_event_plan, select_fragments_with_debug


TEMPLATE_VERSION = "scene_template_v1"
logger = logging.getLogger("uvicorn.error")


def _as_bool_env(name: str, default: bool = False) -> bool:
    raw = os.environ.get(name)
    if raw is None:
        return default
    return str(raw).strip().lower() in {"1", "true", "yes", "on"}


def _scene_debug_enabled() -> bool:
    return _as_bool_env("DRIFT_DEBUG_TRACE", default=False) or _as_bool_env("DRIFT_SCENE_DEBUG", default=False)


def _emit_scene_debug_log(
    *,
    inventory_state: Dict[str, Any],
    story_theme: str,
    scene_hint: str | None,
    fragments: list[str],
    scene_graph: Dict[str, Any],
    layout: Dict[str, Any],
    event_plan: list[Dict[str, Any]],
    scoring_debug: Dict[str, Any],
) -> None:
    if not _scene_debug_enabled():
        return

    payload = {
        "inventory_state": {
            "player_id": str(inventory_state.get("player_id") or "default"),
            "resources": dict(inventory_state.get("resources") or {}),
            "updated_at_ms": _safe_int(inventory_state.get("updated_at_ms"), 0),
        },
        "story_theme": str(story_theme or ""),
        "scene_hint": str(scene_hint) if scene_hint else None,
        "fragments": list(fragments),
        "scene_graph": dict(scene_graph or {}),
        "layout": dict(layout or {}),
        "event_count": len(event_plan),
        "event_ids": [str(evt.get("event_id") or "") for evt in event_plan if isinstance(evt, dict)],
        "event_types": [str(evt.get("type") or "") for evt in event_plan if isinstance(evt, dict)],
        "asset_registry_version": scoring_debug.get("asset_registry_version"),
        "selected_assets": list(scoring_debug.get("selected_assets") or []),
        "asset_sources": list(scoring_debug.get("asset_sources") or []),
        "scoring_debug": dict(scoring_debug or {}),
    }

    if _scene_debug_enabled():
        rendered = f"[SceneAssembler] {json.dumps(payload, ensure_ascii=False, sort_keys=True)}"
        logger.info("[SceneAssembler] %s", json.dumps(payload, ensure_ascii=False, sort_keys=True))
        print(rendered, flush=True)
        return

    summary_payload = {
        "resources": payload["inventory_state"]["resources"],
        "fragments": payload["fragments"],
        "event_ids": payload["event_ids"],
        "event_count": payload["event_count"],
    }
    rendered_summary = f"[SceneAssembler] summary={json.dumps(summary_payload, ensure_ascii=False, sort_keys=True)}"
    logger.warning("[SceneAssembler] summary=%s", json.dumps(summary_payload, ensure_ascii=False, sort_keys=True))
    print(rendered_summary, flush=True)


def _safe_int(value: Any, default: int) -> int:
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return int(default)


def _normalize_resources(raw_resources: Any) -> Dict[str, int]:
    if not isinstance(raw_resources, dict):
        return {}

    normalized: Dict[str, int] = {}
    for key, value in raw_resources.items():
        name = str(key).strip().lower()
        if not name:
            continue
        amount = _safe_int(value, 0)
        if amount > 0:
            normalized[name] = amount
    return normalized


def _normalize_inventory_state(inventory_state: Dict[str, Any] | None) -> Dict[str, Any]:
    payload = inventory_state if isinstance(inventory_state, dict) else {}
    resources = _normalize_resources(payload.get("resources"))
    return {
        "player_id": str(payload.get("player_id") or "default"),
        "resources": resources,
        "updated_at_ms": _safe_int(payload.get("updated_at_ms"), 0),
    }


def _normalize_scene_hint(scene_hint: str | None) -> str | None:
    normalized = str(scene_hint or "").strip()
    return normalized or None


def assemble_scene(
    inventory_state: Dict[str, Any] | None,
    story_theme: str | None,
    scene_hint: str | None = None,
    anchor_position: Dict[str, Any] | None = None,
) -> Dict[str, Any]:
    normalized_inventory = _normalize_inventory_state(inventory_state)
    normalized_theme = str(story_theme or "")
    normalized_hint = _normalize_scene_hint(scene_hint)

    selection = select_fragments_with_debug(
        normalized_inventory["resources"],
        normalized_theme,
        scene_hint=normalized_hint,
    )
    fragments = list(selection.get("fragments") or [])
    scene_graph = dict(selection.get("scene_graph") or {})
    layout = dict(selection.get("layout") or {})
    scoring_debug = dict(selection.get("debug") or {})
    selected_assets = scoring_debug.get("selected_assets") if isinstance(scoring_debug.get("selected_assets"), list) else []
    asset_sources = scoring_debug.get("asset_sources") if isinstance(scoring_debug.get("asset_sources"), list) else []
    asset_selection = scoring_debug.get("asset_selection") if isinstance(scoring_debug.get("asset_selection"), dict) else {}
    fragment_source = scoring_debug.get("fragment_source") if isinstance(scoring_debug.get("fragment_source"), list) else []
    theme_filter = scoring_debug.get("theme_filter") if isinstance(scoring_debug.get("theme_filter"), dict) else {}
    event_plan = build_event_plan(
        fragments,
        anchor_position=anchor_position,
        scene_hint=normalized_hint,
        layout=layout,
    )

    _emit_scene_debug_log(
        inventory_state=normalized_inventory,
        story_theme=normalized_theme,
        scene_hint=normalized_hint,
        fragments=fragments,
        scene_graph=scene_graph,
        layout=layout,
        event_plan=event_plan,
        scoring_debug=scoring_debug,
    )

    return {
        "inventory_state": normalized_inventory,
        "story_theme": normalized_theme,
        "scene_hint": normalized_hint,
        "scene_plan": {
            "template_version": TEMPLATE_VERSION,
            "fragments": fragments,
            "scene_graph": scene_graph,
            "layout": layout,
            "scene_hint": normalized_hint,
        },
        "scene_graph": scene_graph,
        "layout": layout,
        "scoring_debug": scoring_debug,
        "asset_registry_version": scoring_debug.get("asset_registry_version"),
        "selected_assets": list(selected_assets),
        "asset_sources": list(asset_sources),
        "asset_selection": dict(asset_selection),
        "fragment_source": list(fragment_source),
        "theme_filter": dict(theme_filter),
        "event_plan": event_plan,
    }
