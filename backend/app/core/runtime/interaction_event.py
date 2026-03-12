from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any, Dict, Optional
from uuid import uuid4


INTERACTION_EVENT_VERSION = "interaction_event_v1"
SUPPORTED_INTERACTION_EVENT_TYPES = {"talk", "collect", "trigger"}


@dataclass(frozen=True)
class InteractionEvent:
    version: str
    event_id: str
    type: str
    player_id: str
    npc_id: Optional[str]
    anchor: Dict[str, Any]
    timestamp_ms: int
    data: Dict[str, Any] = field(default_factory=dict)


def normalize_anchor(anchor: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    payload = anchor if isinstance(anchor, dict) else {}
    base_x = payload.get("base_x", 0)
    base_y = payload.get("base_y", 64)
    base_z = payload.get("base_z", 0)
    anchor_mode = payload.get("anchor_mode", "fixed")
    return {
        "base_x": int(base_x),
        "base_y": int(base_y),
        "base_z": int(base_z),
        "anchor_mode": str(anchor_mode),
    }


def create_interaction_event(
    *,
    event_type: str,
    player_id: str,
    npc_id: Optional[str] = None,
    anchor: Optional[Dict[str, Any]] = None,
    data: Optional[Dict[str, Any]] = None,
    timestamp_ms: Optional[int] = None,
    event_id: Optional[str] = None,
    version: str = INTERACTION_EVENT_VERSION,
) -> InteractionEvent:
    normalized_type = str(event_type or "").strip().lower()
    if normalized_type not in SUPPORTED_INTERACTION_EVENT_TYPES:
        raise ValueError("UNSUPPORTED_INTERACTION_EVENT_TYPE")

    normalized_player_id = str(player_id or "").strip()
    if not normalized_player_id:
        raise ValueError("INVALID_PLAYER_ID")

    normalized_event_id = str(event_id or f"evt_{uuid4().hex[:12]}").strip()
    if not normalized_event_id:
        raise ValueError("INVALID_EVENT_ID")

    normalized_data = dict(data) if isinstance(data, dict) else {}
    normalized_npc_id = str(npc_id).strip() if isinstance(npc_id, str) and npc_id.strip() else None

    resolved_timestamp_ms = int(timestamp_ms) if timestamp_ms is not None else int(time.time() * 1000)

    return InteractionEvent(
        version=str(version or INTERACTION_EVENT_VERSION),
        event_id=normalized_event_id,
        type=normalized_type,
        player_id=normalized_player_id,
        npc_id=normalized_npc_id,
        anchor=normalize_anchor(anchor),
        timestamp_ms=resolved_timestamp_ms,
        data=normalized_data,
    )


def interaction_event_to_dict(event: InteractionEvent) -> Dict[str, Any]:
    return {
        "version": event.version,
        "event_id": event.event_id,
        "type": event.type,
        "player_id": event.player_id,
        "npc_id": event.npc_id,
        "anchor": dict(event.anchor),
        "timestamp_ms": int(event.timestamp_ms),
        "data": dict(event.data),
    }


def coerce_interaction_event(payload: InteractionEvent | Dict[str, Any]) -> InteractionEvent:
    if isinstance(payload, InteractionEvent):
        return payload
    if not isinstance(payload, dict):
        raise ValueError("INVALID_EVENT_PAYLOAD")

    return create_interaction_event(
        event_type=str(payload.get("type", "")),
        player_id=str(payload.get("player_id", "")),
        npc_id=payload.get("npc_id"),
        anchor=payload.get("anchor") if isinstance(payload.get("anchor"), dict) else None,
        data=payload.get("data") if isinstance(payload.get("data"), dict) else None,
        timestamp_ms=payload.get("timestamp_ms"),
        event_id=payload.get("event_id"),
        version=str(payload.get("version", INTERACTION_EVENT_VERSION)),
    )
