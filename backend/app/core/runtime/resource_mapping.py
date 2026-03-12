from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Any, Dict, Iterable, List

from app.core.executor.canonical_v2 import stable_hash_v2
from app.core.runtime.resource_canonical import normalize_inventory_resource_token


RESOURCE_INVENTORY_VERSION = "resource_inventory_v1"
RESOURCE_BINDING_VERSION = "resource_binding_v1"


@dataclass(frozen=True)
class ResourceInventory:
    version: str
    player_id: str
    resources: List[str]
    timestamp_ms: int


def _normalize_resource_name(value: Any) -> str:
    return normalize_inventory_resource_token(value)


def _normalize_resources(resources: Iterable[Any] | None) -> List[str]:
    normalized = [_normalize_resource_name(item) for item in list(resources or [])]
    filtered = [item for item in normalized if item]
    filtered.sort()
    return filtered


def create_resource_inventory(
    *,
    player_id: str,
    resources: Iterable[Any] | None = None,
    timestamp_ms: int | None = None,
    version: str = RESOURCE_INVENTORY_VERSION,
) -> ResourceInventory:
    normalized_player_id = str(player_id or "").strip()
    if not normalized_player_id:
        raise ValueError("INVALID_PLAYER_ID")

    resolved_timestamp_ms = int(timestamp_ms) if timestamp_ms is not None else int(time.time() * 1000)

    return ResourceInventory(
        version=str(version or RESOURCE_INVENTORY_VERSION),
        player_id=normalized_player_id,
        resources=_normalize_resources(resources),
        timestamp_ms=resolved_timestamp_ms,
    )


def resource_inventory_to_dict(inventory: ResourceInventory) -> Dict[str, Any]:
    return {
        "version": inventory.version,
        "player_id": inventory.player_id,
        "resources": list(inventory.resources),
        "timestamp_ms": int(inventory.timestamp_ms),
    }


def normalize_resource_inventory(value: ResourceInventory | Dict[str, Any]) -> Dict[str, Any]:
    if isinstance(value, ResourceInventory):
        return resource_inventory_to_dict(value)

    if not isinstance(value, dict):
        raise ValueError("INVALID_RESOURCE_INVENTORY")

    return resource_inventory_to_dict(
        create_resource_inventory(
            player_id=str(value.get("player_id") or ""),
            resources=value.get("resources") if isinstance(value.get("resources"), list) else [],
            timestamp_ms=int(value.get("timestamp_ms") or 0),
            version=str(value.get("version") or RESOURCE_INVENTORY_VERSION),
        )
    )


def _count_resources(resources: Iterable[str]) -> Dict[str, int]:
    counts: Dict[str, int] = {}
    for resource_name in resources:
        counts[resource_name] = int(counts.get(resource_name, 0)) + 1
    return counts


def detect_missing_resources(
    *,
    scene_requirements: Iterable[Any],
    inventory: ResourceInventory | Dict[str, Any],
) -> List[str]:
    inventory_payload = normalize_resource_inventory(inventory)
    required_resources = _normalize_resources(scene_requirements)

    inventory_counts = _count_resources(inventory_payload["resources"])
    required_counts = _count_resources(required_resources)

    missing = [
        resource_name
        for resource_name, required_count in sorted(required_counts.items(), key=lambda item: item[0])
        if int(inventory_counts.get(resource_name, 0)) < int(required_count)
    ]
    return missing


def resource_binding_hash(
    *,
    scene_requirements: Iterable[Any],
    inventory: ResourceInventory | Dict[str, Any],
) -> str:
    binding = bind_resources_to_scene(
        scene_requirements=scene_requirements,
        inventory=inventory,
    )
    return str(binding["binding_hash"])


def bind_resources_to_scene(
    *,
    scene_requirements: Iterable[Any],
    inventory: ResourceInventory | Dict[str, Any],
) -> Dict[str, Any]:
    inventory_payload = normalize_resource_inventory(inventory)
    required_resources = _normalize_resources(scene_requirements)

    inventory_counts = _count_resources(inventory_payload["resources"])
    required_counts = _count_resources(required_resources)

    missing_resource_counts = {
        resource_name: int(required_count - int(inventory_counts.get(resource_name, 0)))
        for resource_name, required_count in sorted(required_counts.items(), key=lambda item: item[0])
        if int(inventory_counts.get(resource_name, 0)) < int(required_count)
    }
    missing_resources = sorted(missing_resource_counts.keys())
    available_resources = sorted(
        [resource_name for resource_name in required_counts.keys() if int(inventory_counts.get(resource_name, 0)) > 0]
    )

    binding_status = "FULL" if not missing_resources else "DEGRADED"
    degrade_patch_type = "none" if binding_status == "FULL" else "text_patch"

    deterministic_payload = {
        "version": RESOURCE_BINDING_VERSION,
        "player_id": inventory_payload["player_id"],
        "inventory_resources": list(inventory_payload["resources"]),
        "scene_requirements": list(required_resources),
        "available_resources": list(available_resources),
        "missing_resources": list(missing_resources),
        "missing_resource_counts": dict(missing_resource_counts),
        "binding_status": binding_status,
        "degrade_patch_type": degrade_patch_type,
    }

    binding_hash = stable_hash_v2(deterministic_payload)

    return {
        **deterministic_payload,
        "inventory_hash": stable_hash_v2(inventory_payload["resources"]),
        "requirements_hash": stable_hash_v2(required_resources),
        "binding_hash": binding_hash,
    }
