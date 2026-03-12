from __future__ import annotations

from copy import deepcopy
from typing import Any, Dict, Iterable, List


RESOURCE_FRAGMENT_RULES: tuple[tuple[str, int, str], ...] = (
    ("wood", 1, "camp"),
    ("torch", 1, "fire"),
    ("pork", 1, "cooking_area"),
)

THEME_FRAGMENT_RULES: tuple[tuple[str, str], ...] = (
    ("荒野", "wanderer_npc"),
    ("大风", "wanderer_npc"),
    ("风", "wanderer_npc"),
)

FRAGMENT_ORDER: tuple[str, ...] = (
    "camp",
    "fire",
    "wanderer_npc",
    "cooking_area",
)

FRAGMENT_EVENT_BLUEPRINTS: Dict[str, Dict[str, Any]] = {
    "camp": {
        "event_id": "spawn_camp",
        "type": "spawn_structure",
        "anchor_ref": "player",
        "data": {"template": "camp_small"},
    },
    "fire": {
        "event_id": "spawn_fire",
        "type": "spawn_block",
        "anchor_ref": "camp_center",
        "data": {"block": "campfire"},
    },
    "wanderer_npc": {
        "event_id": "spawn_npc",
        "type": "spawn_npc",
        "anchor_ref": "camp_edge",
        "data": {"npc_template": "wanderer"},
    },
    "cooking_area": {
        "event_id": "spawn_cooking_area",
        "type": "spawn_structure",
        "anchor_ref": "camp_center",
        "data": {"template": "cooking_area_basic"},
    },
}


def _safe_float(value: Any, default: float) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return float(default)


def _compose_theme_with_hint(story_theme: str, scene_hint: str | None) -> str:
    hint = str(scene_hint or "").strip()
    if not hint:
        return str(story_theme or "")
    base_theme = str(story_theme or "").strip()
    if not base_theme:
        return hint
    return f"{base_theme} {hint}"


def select_fragments(resources: Dict[str, int], story_theme: str, scene_hint: str | None = None) -> List[str]:
    selected: set[str] = set()

    for resource_key, minimum, fragment in RESOURCE_FRAGMENT_RULES:
        amount = int(resources.get(resource_key, 0) or 0)
        if amount >= minimum:
            selected.add(fragment)

    normalized_theme = _compose_theme_with_hint(story_theme, scene_hint)
    for keyword, fragment in THEME_FRAGMENT_RULES:
        if keyword in normalized_theme:
            selected.add(fragment)

    return [fragment for fragment in FRAGMENT_ORDER if fragment in selected]


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


def build_event_plan(
    fragments: Iterable[str],
    *,
    anchor_position: Dict[str, Any] | None = None,
    scene_hint: str | None = None,
) -> List[Dict[str, Any]]:
    events: List[Dict[str, Any]] = []
    normalized_hint = str(scene_hint or "").strip() or None
    hint_variant = _scene_hint_variant(normalized_hint)

    for fragment in fragments:
        blueprint = FRAGMENT_EVENT_BLUEPRINTS.get(str(fragment))
        if not blueprint:
            continue

        event_id = str(blueprint.get("event_id") or f"spawn_{fragment}")
        event_type = str(blueprint.get("type") or "spawn_structure")
        anchor_ref = str(blueprint.get("anchor_ref") or "player")
        data = deepcopy(blueprint.get("data") or {})
        if normalized_hint is not None:
            data["scene_hint"] = normalized_hint
        if hint_variant is not None:
            data["scene_variant"] = hint_variant

        events.append(
            {
                "event_id": event_id,
                "type": event_type,
                "text": event_id,
                "anchor": _build_anchor_payload(anchor_position, anchor_ref=anchor_ref),
                "data": data,
            }
        )

    return events
