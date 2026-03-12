from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict

from app.core.executor.canonical_v2 import stable_hash_v2


NPC_STATE_VERSION = "npc_state_v1"


@dataclass(frozen=True)
class NPCState:
    version: str
    npc_id: str
    relationship_value: float
    threshold: float
    npc_available: bool
    anchor: Dict[str, Any]


def evaluate_npc_availability(*, relationship_value: float, threshold: float) -> bool:
    return float(relationship_value) >= float(threshold)


def _normalize_anchor(anchor: Dict[str, Any] | None) -> Dict[str, Any]:
    payload = anchor if isinstance(anchor, dict) else {}
    return {
        "base_x": int(payload.get("base_x", 0)),
        "base_y": int(payload.get("base_y", 64)),
        "base_z": int(payload.get("base_z", 0)),
        "anchor_mode": str(payload.get("anchor_mode", "fixed")),
    }


def create_npc_state(
    *,
    npc_id: str,
    relationship_value: float = 0.0,
    threshold: float = 0.6,
    anchor: Dict[str, Any] | None = None,
    version: str = NPC_STATE_VERSION,
) -> NPCState:
    normalized_npc_id = str(npc_id or "").strip()
    if not normalized_npc_id:
        raise ValueError("INVALID_NPC_ID")

    normalized_relationship = float(relationship_value)
    normalized_threshold = float(threshold)
    normalized_anchor = _normalize_anchor(anchor)
    available = evaluate_npc_availability(
        relationship_value=normalized_relationship,
        threshold=normalized_threshold,
    )

    return NPCState(
        version=str(version or NPC_STATE_VERSION),
        npc_id=normalized_npc_id,
        relationship_value=round(normalized_relationship, 6),
        threshold=round(normalized_threshold, 6),
        npc_available=bool(available),
        anchor=normalized_anchor,
    )


def npc_state_to_dict(state: NPCState) -> Dict[str, Any]:
    return {
        "version": state.version,
        "npc_id": state.npc_id,
        "relationship_value": float(state.relationship_value),
        "threshold": float(state.threshold),
        "npc_available": bool(state.npc_available),
        "anchor": dict(state.anchor),
    }


def normalize_npc_state(value: NPCState | Dict[str, Any]) -> Dict[str, Any]:
    if isinstance(value, NPCState):
        return npc_state_to_dict(value)
    if not isinstance(value, dict):
        raise ValueError("INVALID_NPC_STATE")

    return npc_state_to_dict(
        create_npc_state(
            npc_id=str(value.get("npc_id") or ""),
            relationship_value=float(value.get("relationship_value", 0.0)),
            threshold=float(value.get("threshold", 0.6)),
            anchor=value.get("anchor") if isinstance(value.get("anchor"), dict) else None,
            version=str(value.get("version", NPC_STATE_VERSION)),
        )
    )


def apply_relationship_delta(
    state: NPCState | Dict[str, Any],
    *,
    delta: float,
    threshold: float | None = None,
    anchor: Dict[str, Any] | None = None,
) -> Dict[str, Any]:
    current = normalize_npc_state(state)
    next_threshold = float(threshold) if threshold is not None else float(current["threshold"])
    next_anchor = anchor if isinstance(anchor, dict) else dict(current.get("anchor") or {})

    next_state = create_npc_state(
        npc_id=str(current["npc_id"]),
        relationship_value=float(current["relationship_value"]) + float(delta),
        threshold=next_threshold,
        anchor=next_anchor,
        version=str(current.get("version") or NPC_STATE_VERSION),
    )
    return npc_state_to_dict(next_state)


def npc_state_hash(state: NPCState | Dict[str, Any]) -> str:
    return stable_hash_v2(normalize_npc_state(state))
