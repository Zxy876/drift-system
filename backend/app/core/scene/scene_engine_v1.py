from __future__ import annotations

from typing import Any, Dict, List

from app.core.generation.deterministic_build_engine import build_from_spec
from app.core.generation.material_alias_mapper import map_roles_to_blocks
from app.core.scene.scene_spec_validator import validate_scene_spec


def _reject(failure_code: str) -> Dict[str, Any]:
    return {
        "build_status": "REJECTED",
        "failure_code": failure_code,
        "blocks": [],
        "scene_path": "scene_engine_v1",
    }


def _lake_blocks() -> List[Dict[str, Any]]:
    blocks: List[Dict[str, Any]] = []

    for x in range(12):
        for z in range(12):
            blocks.append({"x": x, "y": 0, "z": z, "block": "water"})

    for x in range(-1, 13):
        blocks.append({"x": x, "y": 0, "z": -1, "block": "grass_block"})
        blocks.append({"x": x, "y": 0, "z": 12, "block": "grass_block"})
    for z in range(0, 12):
        blocks.append({"x": -1, "y": 0, "z": z, "block": "grass_block"})
        blocks.append({"x": 12, "y": 0, "z": z, "block": "grass_block"})

    blocks.append({"x": 1, "y": 1, "z": 1, "block": "lantern"})
    blocks.append({"x": 10, "y": 1, "z": 10, "block": "lantern"})
    return blocks


def _village_blocks() -> List[Dict[str, Any]] | None:
    house_spec = {
        "structure_type": "house",
        "width": 7,
        "depth": 5,
        "height": 4,
        "material_preference": "wood",
        "roof_type": "flat",
        "orientation": "south",
        "features": {
            "door": {"enabled": True, "side": "front"},
            "windows": {"enabled": True, "count": 2},
        },
    }

    first = build_from_spec(house_spec)
    second = build_from_spec(house_spec)
    if first.get("build_status") != "SUCCESS" or second.get("build_status") != "SUCCESS":
        return None

    first_mapped = map_roles_to_blocks(first.get("blocks") or [], "wood")
    second_mapped = map_roles_to_blocks(second.get("blocks") or [], "wood")
    if first_mapped.get("status") != "SUCCESS" or second_mapped.get("status") != "SUCCESS":
        return None

    blocks: List[Dict[str, Any]] = []
    for b in first_mapped.get("blocks") or []:
        blocks.append(dict(b))
    for b in second_mapped.get("blocks") or []:
        blocks.append({"x": b["x"] + 20, "y": b["y"], "z": b["z"], "block": b["block"]})

    blocks.append({"x": 10, "y": 1, "z": 8, "block": "npc_placeholder"})
    return blocks


def _forest_blocks() -> List[Dict[str, Any]]:
    tree_bases = [
        (0, 0),
        (4, 1),
        (8, 2),
        (2, 6),
        (6, 7),
        (10, 4),
        (12, 8),
        (14, 3),
    ]

    blocks: List[Dict[str, Any]] = []
    for x, z in tree_bases:
        blocks.append({"x": x, "y": 0, "z": z, "block": "oak_log"})
        blocks.append({"x": x, "y": 1, "z": z, "block": "oak_log"})
        blocks.append({"x": x, "y": 2, "z": z, "block": "oak_log"})
        blocks.append({"x": x, "y": 3, "z": z, "block": "oak_leaves"})
    return blocks


def generate_scene_patch(scene_spec: dict) -> dict:
    validation = validate_scene_spec(scene_spec)
    if validation.get("status") != "VALID":
        return _reject(validation.get("failure_code", "INVALID_SCENE_SPEC"))

    normalized = validation.get("scene_spec")
    if not isinstance(normalized, dict):
        return _reject("INVALID_SCENE_SPEC")

    scene_type = normalized["scene_type"]
    if scene_type == "lake":
        blocks = _lake_blocks()
    elif scene_type == "village":
        blocks = _village_blocks()
        if blocks is None:
            return _reject("INVALID_SCENE_SPEC")
    elif scene_type == "forest":
        blocks = _forest_blocks()
        normalized = dict(normalized)
        normalized["time_of_day"] = "night"
    elif scene_type == "plain":
        blocks = []
    else:
        return _reject("INVALID_SCENE_TYPE")

    return {
        "build_status": "SUCCESS",
        "failure_code": "NONE",
        "blocks": blocks,
        "scene_path": "scene_engine_v1",
        "scene_spec": normalized,
    }
