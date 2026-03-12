from __future__ import annotations

from typing import Any, Dict, Iterable, List

from .evolution_rules import collect_event_keys, load_evolution_rules
from .layout_engine import place_new_nodes
from .scene_diff import build_scene_diff
from .scene_library import build_event_plan, get_fragment_map
from .scene_state import SceneState


def _copy_positions(raw_positions: Dict[str, Dict[str, Any]]) -> Dict[str, Dict[str, int]]:
    copied: Dict[str, Dict[str, int]] = {}
    if not isinstance(raw_positions, dict):
        return copied

    for key, value in raw_positions.items():
        if not isinstance(value, dict):
            continue
        copied[str(key)] = {
            "x": int(value.get("x", 0)),
            "z": int(value.get("z", 0)),
        }

    return copied


def _normalize_rule_events(raw_events: Iterable[Dict[str, Any]] | None) -> List[Dict[str, Any]]:
    normalized: List[Dict[str, Any]] = []
    if raw_events is None:
        return normalized

    for row in raw_events:
        if isinstance(row, dict):
            normalized.append(dict(row))

    return normalized


def _append_unique(rows: List[str], token: str) -> None:
    text = str(token or "").strip().lower()
    if text and text not in rows:
        rows.append(text)


def evolve_scene_state(
    *,
    scene_state: SceneState,
    rule_events: Iterable[Dict[str, Any]] | None,
    scene_hint: str | None,
    anchor_position: Dict[str, Any] | None,
) -> Dict[str, Any]:
    rules = load_evolution_rules()
    fragment_map = get_fragment_map()

    previous_state = SceneState.from_dict(scene_state.to_dict(), fallback_level_id=scene_state.level_id)
    next_state = SceneState.from_dict(scene_state.to_dict(), fallback_level_id=scene_state.level_id)

    event_keys: List[str] = []
    target_nodes: List[str] = []

    for event in _normalize_rule_events(rule_events):
        keys = collect_event_keys(event)
        for key in keys:
            _append_unique(event_keys, key)
            for target in rules.targets_for(next_state.root, key):
                if target in next_state.nodes or target in target_nodes:
                    continue
                if target not in fragment_map:
                    continue

                target_nodes.append(target)
                next_state.add_edge(next_state.root, target)

    if target_nodes:
        added_positions = place_new_nodes(
            existing_positions=_copy_positions(previous_state.positions),
            parent_node=next_state.root,
            new_nodes=target_nodes,
            fragments=fragment_map,
        )

        merged_positions = _copy_positions(previous_state.positions)
        for node, position in added_positions.items():
            merged_positions[node] = {
                "x": int(position.get("x", 0)),
                "z": int(position.get("z", 0)),
            }

        next_state.positions = merged_positions

        spawned = list(next_state.spawned_nodes)
        for node in target_nodes:
            if node not in spawned:
                spawned.append(node)
        next_state.spawned_nodes = spawned
        next_state.version = int(previous_state.version) + 1
    else:
        next_state.positions = _copy_positions(previous_state.positions)
        next_state.version = int(previous_state.version)

    diff = build_scene_diff(previous_state, next_state, trigger_event_keys=event_keys)

    layout = next_state.to_layout_dict(strategy="radial_v1")
    incremental_event_plan = build_event_plan(
        diff.added_nodes,
        anchor_position=anchor_position,
        scene_hint=scene_hint,
        layout=layout,
    )
    full_event_plan = build_event_plan(
        next_state.nodes,
        anchor_position=anchor_position,
        scene_hint=scene_hint,
        layout=layout,
    )

    return {
        "scene_state": next_state,
        "scene_diff": diff,
        "scene_graph": next_state.to_scene_graph_dict(),
        "layout": layout,
        "fragments": list(next_state.nodes),
        "event_plan": full_event_plan,
        "incremental_event_plan": incremental_event_plan,
    }
