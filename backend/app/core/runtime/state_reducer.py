from __future__ import annotations

from copy import deepcopy
from typing import Any, Dict, Iterable, List

from app.core.executor.canonical_v2 import stable_hash_v2

from .interaction_event import InteractionEvent
from .npc_state import apply_relationship_delta, create_npc_state, normalize_npc_state
from .resource_canonical import normalize_inventory_resource_token
from .resource_mapping import create_resource_inventory, normalize_resource_inventory
from .world_patch import WORLD_PATCH_VERSION, generate_world_patch


RUNTIME_STATE_VERSION = "runtime_state_v1"


def _default_runtime_state() -> Dict[str, Any]:
    return {
        "version": RUNTIME_STATE_VERSION,
        "player_id": "",
        "inventory": {
            "version": "resource_inventory_v1",
            "player_id": "",
            "resources": [],
            "timestamp_ms": 0,
        },
        "talk_count": 0,
        "collected_resources": {},
        "triggers": {},
        "npc_state": {},
        "npc_relationship_state": {},
        "npc_available": {},
        "last_anchor": {
            "base_x": 0,
            "base_y": 64,
            "base_z": 0,
            "anchor_mode": "fixed",
        },
        "applied_event_ids": [],
    }


def _normalize_runtime_state(value: Dict[str, Any]) -> Dict[str, Any]:
    payload = deepcopy(_default_runtime_state())
    if isinstance(value, dict):
        payload.update({k: deepcopy(v) for k, v in value.items() if k in payload})

    payload["player_id"] = str(payload.get("player_id") or "")

    raw_inventory = payload.get("inventory") if isinstance(payload.get("inventory"), dict) else {}
    inventory_player_id = str(raw_inventory.get("player_id") or payload["player_id"] or "runtime_player")
    payload["inventory"] = normalize_resource_inventory(
        create_resource_inventory(
            player_id=inventory_player_id,
            resources=raw_inventory.get("resources") if isinstance(raw_inventory.get("resources"), list) else [],
            timestamp_ms=int(raw_inventory.get("timestamp_ms") or 0),
            version=str(raw_inventory.get("version") or "resource_inventory_v1"),
        )
    )

    payload["collected_resources"] = {
        str(k): int(v) for k, v in dict(payload.get("collected_resources") or {}).items()
    }
    payload["triggers"] = {
        str(k): int(v) for k, v in dict(payload.get("triggers") or {}).items()
    }
    payload["npc_relationship_state"] = {
        str(k): float(v) for k, v in dict(payload.get("npc_relationship_state") or {}).items()
    }
    payload["npc_available"] = {
        str(k): bool(v) for k, v in dict(payload.get("npc_available") or {}).items()
    }

    raw_npc_state = dict(payload.get("npc_state") or {})
    normalized_npc_state: Dict[str, Dict[str, Any]] = {}
    for key, value in raw_npc_state.items():
        if isinstance(value, dict):
            candidate = dict(value)
        else:
            candidate = {}
        candidate.setdefault("npc_id", str(key))
        normalized = normalize_npc_state(candidate)
        normalized_npc_state[str(normalized["npc_id"])] = normalized

    if not normalized_npc_state and payload["npc_relationship_state"]:
        for npc_id, relationship_value in payload["npc_relationship_state"].items():
            normalized_npc_state[str(npc_id)] = normalize_npc_state(
                create_npc_state(
                    npc_id=str(npc_id),
                    relationship_value=float(relationship_value),
                    threshold=0.6,
                    anchor=payload.get("last_anchor") if isinstance(payload.get("last_anchor"), dict) else None,
                )
            )

    payload["npc_state"] = normalized_npc_state
    payload["npc_relationship_state"] = {
        npc_id: float(item.get("relationship_value", 0.0))
        for npc_id, item in sorted(payload["npc_state"].items(), key=lambda kv: kv[0])
    }
    payload["npc_available"] = {
        npc_id: bool(item.get("npc_available", False))
        for npc_id, item in sorted(payload["npc_state"].items(), key=lambda kv: kv[0])
    }

    if not payload["inventory"]["resources"] and payload["collected_resources"]:
        derived_resources: List[str] = []
        for resource_name, count in sorted(payload["collected_resources"].items(), key=lambda item: item[0]):
            if int(count) > 0:
                derived_resources.extend([str(resource_name)] * int(count))
        payload["inventory"] = normalize_resource_inventory(
            create_resource_inventory(
                player_id=payload["inventory"]["player_id"] or payload["player_id"] or "runtime_player",
                resources=derived_resources,
                timestamp_ms=int(payload["inventory"].get("timestamp_ms") or 0),
                version=str(payload["inventory"].get("version") or "resource_inventory_v1"),
            )
        )

    if payload["player_id"]:
        payload["inventory"]["player_id"] = payload["player_id"]

    payload["applied_event_ids"] = [str(v) for v in list(payload.get("applied_event_ids") or [])]
    payload["talk_count"] = int(payload.get("talk_count") or 0)
    payload["last_anchor"] = dict(payload.get("last_anchor") or _default_runtime_state()["last_anchor"])
    payload["version"] = str(payload.get("version") or RUNTIME_STATE_VERSION)
    return payload


def reduce_event_log(
    events: Iterable[InteractionEvent],
    *,
    initial_state: Dict[str, Any] | None = None,
) -> Dict[str, Any]:
    rows = list(events)
    state = _normalize_runtime_state(initial_state or {})

    for event in rows:
        if not isinstance(event, InteractionEvent):
            raise ValueError("INVALID_INTERACTION_EVENT")

        if not state["player_id"]:
            state["player_id"] = event.player_id
        if isinstance(state.get("inventory"), dict):
            state["inventory"]["player_id"] = state["player_id"]

        state["last_anchor"] = dict(event.anchor)
        state["applied_event_ids"].append(event.event_id)

        if event.type == "talk":
            state["talk_count"] += 1
            npc_id = event.npc_id or str(event.data.get("npc_id") or "unknown_npc")
            delta = float(event.data.get("relationship_delta", 0.1))
            threshold = float(event.data.get("threshold", 0.6))

            current_npc_state = (state.get("npc_state") or {}).get(npc_id)
            if not isinstance(current_npc_state, dict):
                current_npc_state = normalize_npc_state(
                    create_npc_state(
                        npc_id=npc_id,
                        relationship_value=float(state["npc_relationship_state"].get(npc_id, 0.0)),
                        threshold=threshold,
                        anchor=event.anchor,
                    )
                )

            next_npc_state = apply_relationship_delta(
                current_npc_state,
                delta=delta,
                threshold=threshold,
                anchor=event.anchor,
            )
            state["npc_state"][npc_id] = next_npc_state
            state["npc_relationship_state"][npc_id] = float(next_npc_state["relationship_value"])
            state["npc_available"][npc_id] = bool(next_npc_state["npc_available"])

        elif event.type == "collect":
            resource = normalize_inventory_resource_token(event.data.get("resource")) or "unknown_resource"
            amount = max(int(event.data.get("amount", 1)), 1)
            state["collected_resources"][resource] = int(state["collected_resources"].get(resource, 0)) + amount
            inventory_resources = []
            if isinstance(state.get("inventory"), dict):
                inventory_resources = list(state["inventory"].get("resources") or [])
            inventory_resources.extend([resource] * amount)
            if isinstance(state.get("inventory"), dict):
                state["inventory"]["resources"] = inventory_resources
                state["inventory"]["timestamp_ms"] = int(event.timestamp_ms)

        elif event.type == "trigger":
            trigger_key = str(event.data.get("trigger") or "unknown_trigger")
            state["triggers"][trigger_key] = int(state["triggers"].get(trigger_key, 0)) + 1

        else:
            raise ValueError("UNSUPPORTED_INTERACTION_EVENT_TYPE")

    return _normalize_runtime_state(state)


def runtime_state_hash(runtime_state: Dict[str, Any]) -> str:
    payload = _normalize_runtime_state(runtime_state)
    return stable_hash_v2(payload)


def build_world_patch_from_state(
    runtime_state: Dict[str, Any],
    *,
    source_event: InteractionEvent | None = None,
) -> Dict[str, Any]:
    state_payload = _normalize_runtime_state(runtime_state)
    input_state_hash = runtime_state_hash(state_payload)
    return generate_world_patch(
        source_event=source_event,
        runtime_state=state_payload,
        input_state_hash=input_state_hash,
        version=WORLD_PATCH_VERSION,
    )


def replay_event_log_to_patch(
    events: Iterable[InteractionEvent],
    *,
    initial_state: Dict[str, Any] | None = None,
) -> Dict[str, Any]:
    rows: List[InteractionEvent] = list(events)
    runtime_state = reduce_event_log(rows, initial_state=initial_state)
    world_patch = build_world_patch_from_state(
        runtime_state,
        source_event=rows[-1] if rows else None,
    )
    return {
        "runtime_state": runtime_state,
        "state_hash": runtime_state_hash(runtime_state),
        "world_patch": world_patch,
        "payload_hash": world_patch["payload_hash"],
    }
