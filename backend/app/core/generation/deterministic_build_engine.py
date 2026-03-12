from __future__ import annotations

from typing import Any, Dict, List

from app.core.generation.spec_validator import validate_spec


def _reject(failure_code: str) -> Dict[str, Any]:
    return {
        "build_status": "REJECTED",
        "failure_code": failure_code,
        "blocks": [],
    }


def _build_house(spec: Dict[str, Any]) -> List[Dict[str, int | str]]:
    width = spec["width"]
    depth = spec["depth"]
    height = spec["height"]
    roof_type = spec["roof_type"]
    orientation = spec.get("orientation", "south")
    features = spec.get("features") or {}
    door_cfg = features.get("door") or {"enabled": False, "side": "front"}
    windows_cfg = features.get("windows") or {"enabled": False, "count": 0}

    blocks: List[Dict[str, int | str]] = []

    for x in range(width):
        for z in range(depth):
            blocks.append({"x": x, "y": 0, "z": z, "role": "FLOOR"})

    for y in range(1, height):
        for x in range(width):
            for z in range(depth):
                if x == 0 or x == width - 1 or z == 0 or z == depth - 1:
                    blocks.append({"x": x, "y": y, "z": z, "role": "WALL"})

    if roof_type == "flat":
        for x in range(width):
            for z in range(depth):
                blocks.append({"x": x, "y": height, "z": z, "role": "ROOF"})
    elif roof_type == "gable":
        layers = (depth + 1) // 2
        for ridge in range(layers):
            z_front = ridge
            z_back = depth - 1 - ridge
            y = height + ridge
            start_x = ridge
            end_x = width - ridge

            if start_x >= end_x:
                start_x = 0
                end_x = width

            for x in range(start_x, end_x):
                blocks.append({"x": x, "y": y, "z": z_front, "role": "ROOF"})
                if z_back != z_front:
                    blocks.append({"x": x, "y": y, "z": z_back, "role": "ROOF"})

    if door_cfg.get("enabled"):
        door_slots = _door_positions(width, depth, orientation)
        blocks = [
            entry
            for entry in blocks
            if not (
                entry.get("role") == "WALL"
                and (entry["x"], entry["y"], entry["z"]) in door_slots
            )
        ]
        for x, y, z in sorted(door_slots, key=lambda p: (p[1], p[0], p[2])):
            blocks.append({"x": x, "y": y, "z": z, "role": "DOOR_AIR"})

    windows_count = windows_cfg.get("count", 0) if windows_cfg.get("enabled") else 0
    if windows_count:
        side_slots = _window_positions(width, depth, orientation, int(windows_count))
        if side_slots is None:
            return []

        blocks = [
            entry
            for entry in blocks
            if not (
                entry.get("role") == "WALL"
                and (entry["x"], entry["y"], entry["z"]) in side_slots
            )
        ]
        for x, y, z in sorted(side_slots, key=lambda p: (p[1], p[0], p[2])):
            blocks.append({"x": x, "y": y, "z": z, "role": "WINDOW"})

    return blocks


def _door_positions(width: int, depth: int, orientation: str) -> set[tuple[int, int, int]]:
    if orientation == "south":
        return {(width // 2, 1, 0), (width // 2, 2, 0)}
    if orientation == "north":
        return {(width // 2, 1, depth - 1), (width // 2, 2, depth - 1)}
    if orientation == "east":
        return {(width - 1, 1, depth // 2), (width - 1, 2, depth // 2)}
    return {(0, 1, depth // 2), (0, 2, depth // 2)}


def _window_positions(
    width: int,
    depth: int,
    orientation: str,
    count: int,
) -> set[tuple[int, int, int]] | None:
    y = 2

    if orientation in {"south", "north"}:
        left_side = [(0, y, z) for z in range(1, depth - 1)]
        right_side = [(width - 1, y, z) for z in range(1, depth - 1)]
    else:
        left_side = [(x, y, 0) for x in range(1, width - 1)]
        right_side = [(x, y, depth - 1) for x in range(1, width - 1)]

    ordered: List[tuple[int, int, int]] = []
    max_len = max(len(left_side), len(right_side))
    for idx in range(max_len):
        if idx < len(left_side):
            ordered.append(left_side[idx])
        if idx < len(right_side):
            ordered.append(right_side[idx])

    if count > len(ordered):
        return None
    return set(ordered[:count])


def _build_wall(spec: Dict[str, Any]) -> List[Dict[str, int | str]]:
    width = spec["width"]
    height = spec["height"]

    blocks: List[Dict[str, int | str]] = []
    for y in range(height):
        for x in range(width):
            blocks.append({"x": x, "y": y, "z": 0, "role": "WALL"})
    return blocks


def _build_tower(spec: Dict[str, Any]) -> List[Dict[str, int | str]]:
    width = spec["width"]
    depth = spec["depth"]
    height = spec["height"]

    blocks: List[Dict[str, int | str]] = []

    for x in range(width):
        for z in range(depth):
            blocks.append({"x": x, "y": 0, "z": z, "role": "FLOOR"})

    for y in range(1, height):
        for x in range(width):
            for z in range(depth):
                if x == 0 or x == width - 1 or z == 0 or z == depth - 1:
                    blocks.append({"x": x, "y": y, "z": z, "role": "WALL"})

    return blocks


def _build_bridge(spec: Dict[str, Any]) -> List[Dict[str, int | str]]:
    width = spec["width"]
    depth = spec["depth"]
    height = spec["height"]

    blocks: List[Dict[str, int | str]] = []

    for x in range(width):
        for z in range(depth):
            blocks.append({"x": x, "y": 0, "z": z, "role": "BRIDGE_DECK"})

    for y in range(1, height):
        blocks.append({"x": 0, "y": y, "z": 0, "role": "SUPPORT"})
        blocks.append({"x": 0, "y": y, "z": depth - 1, "role": "SUPPORT"})
        blocks.append({"x": width - 1, "y": y, "z": 0, "role": "SUPPORT"})
        blocks.append({"x": width - 1, "y": y, "z": depth - 1, "role": "SUPPORT"})

    return blocks


def build_from_spec(spec: dict) -> dict:
    if isinstance(spec, dict):
        raw_structure = spec.get("structure_type")
        if isinstance(raw_structure, str):
            structure_token = raw_structure.strip().lower()
            if structure_token and structure_token not in {"house", "wall", "tower", "bridge"}:
                return _reject("UNSUPPORTED_STRUCTURE")

    validation = validate_spec(spec)
    if validation.get("status") != "VALID":
        return _reject("INVALID_SPEC")

    normalized = validation.get("spec")
    if not isinstance(normalized, dict):
        return _reject("INVALID_SPEC")

    structure_type = normalized["structure_type"]

    if structure_type == "house":
        blocks = _build_house(normalized)
        if not blocks:
            return _reject("INVALID_FEATURE_CONFIG")
    elif structure_type == "wall":
        blocks = _build_wall(normalized)
    elif structure_type == "tower":
        blocks = _build_tower(normalized)
    elif structure_type == "bridge":
        blocks = _build_bridge(normalized)
    else:
        return _reject("UNSUPPORTED_STRUCTURE")

    return {
        "build_status": "SUCCESS",
        "failure_code": "NONE",
        "blocks": blocks,
    }
