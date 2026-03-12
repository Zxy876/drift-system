from __future__ import annotations

from copy import deepcopy
from typing import Any, Dict

from app.core.executor.canonical_v2 import stable_hash_v2

from .interaction_event import InteractionEvent


WORLD_PATCH_VERSION = "world_patch_v1"
WORLD_PATCH_HOME_ANCHOR = {
    "base_x": 0,
    "base_y": 64,
    "base_z": 0,
    "anchor_mode": "fixed",
}


def normalize_world_anchor(anchor: Dict[str, Any] | None) -> Dict[str, Any]:
    payload = anchor if isinstance(anchor, dict) else {}
    return {
        "base_x": int(payload.get("base_x", WORLD_PATCH_HOME_ANCHOR["base_x"])),
        "base_y": int(payload.get("base_y", WORLD_PATCH_HOME_ANCHOR["base_y"])),
        "base_z": int(payload.get("base_z", WORLD_PATCH_HOME_ANCHOR["base_z"])),
        "anchor_mode": str(payload.get("anchor_mode", WORLD_PATCH_HOME_ANCHOR["anchor_mode"])),
    }


def _event_data(source_event: InteractionEvent | None) -> Dict[str, Any]:
    if not isinstance(source_event, InteractionEvent):
        return {}
    return dict(source_event.data) if isinstance(source_event.data, dict) else {}


def _player_explicit_anchor(source_event: InteractionEvent | None) -> Dict[str, Any] | None:
    event_data = _event_data(source_event)

    for key in ("player_anchor", "set_anchor", "explicit_anchor"):
        candidate = event_data.get(key)
        if isinstance(candidate, dict):
            return normalize_world_anchor(candidate)

    if isinstance(source_event, InteractionEvent):
        event_anchor = source_event.anchor if isinstance(source_event.anchor, dict) else {}
        if str(event_anchor.get("anchor_mode") or "").strip().lower() == "player":
            return normalize_world_anchor(event_anchor)

    return None


def _scene_anchor_routing_anchor(
    source_event: InteractionEvent | None,
    runtime_state: Dict[str, Any],
) -> Dict[str, Any] | None:
    event_data = _event_data(source_event)

    if isinstance(event_data.get("scene_anchor"), dict):
        return normalize_world_anchor(event_data["scene_anchor"])

    if isinstance(runtime_state.get("scene_anchor"), dict):
        return normalize_world_anchor(runtime_state.get("scene_anchor"))

    scene_anchor_routing = runtime_state.get("scene_anchor_routing")
    if isinstance(scene_anchor_routing, dict):
        if isinstance(scene_anchor_routing.get("anchor"), dict):
            return normalize_world_anchor(scene_anchor_routing.get("anchor"))

        selected_anchor = str(scene_anchor_routing.get("selected_anchor") or "").strip().lower()
        scene_anchors = runtime_state.get("scene_anchors")
        if selected_anchor and isinstance(scene_anchors, dict) and isinstance(scene_anchors.get(selected_anchor), dict):
            return normalize_world_anchor(scene_anchors.get(selected_anchor))

    if isinstance(source_event, InteractionEvent):
        event_anchor = source_event.anchor if isinstance(source_event.anchor, dict) else {}
        if str(event_anchor.get("anchor_mode") or "").strip().lower() == "scene":
            return normalize_world_anchor(event_anchor)

    return None


def _npc_anchor(source_event: InteractionEvent | None, runtime_state: Dict[str, Any]) -> Dict[str, Any] | None:
    npc_state_map = runtime_state.get("npc_state")
    if not isinstance(npc_state_map, dict):
        return None

    event_data = _event_data(source_event)
    candidate_npc_ids: list[str] = []

    if isinstance(source_event, InteractionEvent) and isinstance(source_event.npc_id, str) and source_event.npc_id.strip():
        candidate_npc_ids.append(source_event.npc_id.strip())
    if isinstance(event_data.get("npc_id"), str) and event_data.get("npc_id").strip():
        candidate_npc_ids.append(event_data.get("npc_id").strip())

    for npc_id in candidate_npc_ids:
        candidate = npc_state_map.get(npc_id)
        if isinstance(candidate, dict) and isinstance(candidate.get("anchor"), dict):
            return normalize_world_anchor(candidate.get("anchor"))

    for npc_id, candidate in sorted(npc_state_map.items(), key=lambda item: str(item[0])):
        if not isinstance(candidate, dict) or not isinstance(candidate.get("anchor"), dict):
            continue
        if bool(candidate.get("npc_available", False)):
            return normalize_world_anchor(candidate.get("anchor"))

    for npc_id, candidate in sorted(npc_state_map.items(), key=lambda item: str(item[0])):
        if isinstance(candidate, dict) and isinstance(candidate.get("anchor"), dict):
            return normalize_world_anchor(candidate.get("anchor"))

    return None


def _home_anchor(runtime_state: Dict[str, Any]) -> Dict[str, Any]:
    if isinstance(runtime_state.get("home_anchor"), dict):
        return normalize_world_anchor(runtime_state.get("home_anchor"))
    return dict(WORLD_PATCH_HOME_ANCHOR)


def resolve_world_patch_anchor(
    *,
    source_event: InteractionEvent | None,
    runtime_state: Dict[str, Any],
) -> Dict[str, Any]:
    player_anchor = _player_explicit_anchor(source_event)
    if player_anchor is not None:
        return {"source": "player", "anchor": player_anchor}

    scene_anchor = _scene_anchor_routing_anchor(source_event, runtime_state)
    if scene_anchor is not None:
        return {"source": "scene", "anchor": scene_anchor}

    npc_anchor = _npc_anchor(source_event, runtime_state)
    if npc_anchor is not None:
        return {"source": "npc", "anchor": npc_anchor}

    return {"source": "home", "anchor": _home_anchor(runtime_state)}


def build_world_patch_payload(runtime_state: Dict[str, Any]) -> Dict[str, Any]:
    state_payload = deepcopy(runtime_state if isinstance(runtime_state, dict) else {})

    collected_resources = {
        str(key): int(value)
        for key, value in sorted(dict(state_payload.get("collected_resources") or {}).items(), key=lambda item: str(item[0]))
    }
    npc_available = {
        str(key): bool(value)
        for key, value in sorted(dict(state_payload.get("npc_available") or {}).items(), key=lambda item: str(item[0]))
    }
    triggers = {
        str(key): int(value)
        for key, value in sorted(dict(state_payload.get("triggers") or {}).items(), key=lambda item: str(item[0]))
    }

    inventory = state_payload.get("inventory") if isinstance(state_payload.get("inventory"), dict) else {}
    inventory_resources = list(inventory.get("resources") or [])

    return {
        "variables": {
            "runtime_talk_count": int(state_payload.get("talk_count") or 0),
            "runtime_collect_count": int(sum(collected_resources.values())),
            "runtime_trigger_count": int(sum(triggers.values())),
        },
        "npc_available": npc_available,
        "resources": collected_resources,
        "inventory_resources": inventory_resources,
    }


def generate_world_patch(
    *,
    source_event: InteractionEvent | None,
    runtime_state: Dict[str, Any],
    input_state_hash: str | None = None,
    version: str = WORLD_PATCH_VERSION,
) -> Dict[str, Any]:
    state_payload = deepcopy(runtime_state if isinstance(runtime_state, dict) else {})
    patch_payload = build_world_patch_payload(state_payload)
    payload_hash = stable_hash_v2(patch_payload)
    resolved_input_state_hash = str(input_state_hash or stable_hash_v2(state_payload))

    anchor_resolution = resolve_world_patch_anchor(
        source_event=source_event,
        runtime_state=state_payload,
    )

    if isinstance(source_event, InteractionEvent):
        source_event_id = str(source_event.event_id)
        resolved_timestamp = int(source_event.timestamp_ms)
    else:
        applied_event_ids = [str(v) for v in list(state_payload.get("applied_event_ids") or [])]
        source_event_id = applied_event_ids[-1] if applied_event_ids else ""
        resolved_timestamp = int(state_payload.get("timestamp_ms") or 0)

    return {
        "version": str(version or WORLD_PATCH_VERSION),
        "patch_id": f"patch_{payload_hash[:12]}",
        "source_event": source_event_id,
        "input_state_hash": resolved_input_state_hash,
        "payload_hash": payload_hash,
        "anchor": dict(anchor_resolution["anchor"]),
        "anchor_source": str(anchor_resolution["source"]),
        "timestamp": int(resolved_timestamp),
        "timestamp_ms": int(resolved_timestamp),
        "payload": patch_payload,
    }
