from __future__ import annotations

from typing import Any, Dict, List


MATERIAL_ROLE_MAP: Dict[str, Dict[str, str]] = {
    "wood": {
        "FLOOR": "oak_planks",
        "WALL": "oak_planks",
        "ROOF": "oak_slab",
        "WINDOW": "glass_pane",
        "DOOR_AIR": "air",
        "BRIDGE_DECK": "oak_planks",
        "SUPPORT": "oak_log",
    },
    "stone": {
        "FLOOR": "stone",
        "WALL": "stone_bricks",
        "ROOF": "stone_slab",
        "WINDOW": "glass_pane",
        "DOOR_AIR": "air",
        "BRIDGE_DECK": "stone",
        "SUPPORT": "stone_bricks",
    },
    "brick": {
        "FLOOR": "bricks",
        "WALL": "bricks",
        "ROOF": "brick_slab",
        "WINDOW": "glass_pane",
        "DOOR_AIR": "air",
        "BRIDGE_DECK": "bricks",
        "SUPPORT": "bricks",
    },
}

BLOCK_ID_WHITELIST = {
    "oak_planks",
    "oak_slab",
    "oak_log",
    "stone",
    "stone_bricks",
    "stone_slab",
    "bricks",
    "brick_slab",
    "glass_pane",
    "air",
}


def _reject(failure_code: str) -> Dict[str, Any]:
    return {
        "status": "REJECTED",
        "failure_code": failure_code,
        "blocks": [],
    }


def map_roles_to_blocks(role_blocks: list[dict], material_preference: str) -> dict:
    if not isinstance(role_blocks, list) or len(role_blocks) == 0:
        return _reject("EMPTY_BLOCKS")

    if not isinstance(material_preference, str):
        return _reject("INVALID_MATERIAL_PREFERENCE")

    material_key = material_preference.strip().lower()
    role_mapping = MATERIAL_ROLE_MAP.get(material_key)
    if role_mapping is None:
        return _reject("INVALID_MATERIAL_PREFERENCE")

    mapped_blocks: List[Dict[str, Any]] = []

    for entry in role_blocks:
        if not isinstance(entry, dict):
            return _reject("INVALID_MAPPING")

        role = entry.get("role")
        if not isinstance(role, str) or role not in role_mapping:
            return _reject("UNKNOWN_ROLE")

        block_id = role_mapping[role]
        if block_id not in BLOCK_ID_WHITELIST:
            return _reject("INVALID_MAPPING")

        x = entry.get("x")
        y = entry.get("y")
        z = entry.get("z")
        if not isinstance(x, int) or not isinstance(y, int) or not isinstance(z, int):
            return _reject("INVALID_MAPPING")

        mapped_blocks.append({"x": x, "y": y, "z": z, "block": block_id})

    return {
        "status": "SUCCESS",
        "failure_code": "NONE",
        "blocks": mapped_blocks,
    }
