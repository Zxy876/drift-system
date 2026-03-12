from __future__ import annotations

import math
import os
from typing import Any, Dict, Iterable, Tuple

from .scene_graph import SceneGraph


def _safe_int(value: Any, default: int) -> int:
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return int(default)


def _layout_min_gap(default: int = 2) -> int:
    raw = os.environ.get("DRIFT_LAYOUT_MIN_GAP")
    if raw is None:
        raw = os.environ.get("MIN_LAYOUT_GAP")

    if raw is None:
        return int(default)

    parsed = _safe_int(raw, default)
    return max(0, min(64, parsed))


def _clamp_min_gap(value: Any, default: int = 2) -> int:
    parsed = _safe_int(value, default)
    return max(0, min(64, parsed))


def _fragment_size(fragment: Dict[str, Any] | None) -> Tuple[int, int]:
    if not isinstance(fragment, dict):
        return (3, 3)

    raw_size = fragment.get("size")
    if isinstance(raw_size, (list, tuple)) and len(raw_size) >= 2:
        width = max(1, _safe_int(raw_size[0], 3))
        depth = max(1, _safe_int(raw_size[1], 3))
        return (width, depth)

    return (3, 3)


def _base_radial_slots() -> list[tuple[int, int]]:
    return [
        (4, 0),
        (-4, 0),
        (0, 4),
        (0, -4),
        (6, 3),
        (-6, 3),
        (6, -3),
        (-6, -3),
    ]


def _scaled_slot(slot: tuple[int, int], spacing_x: int, spacing_z: int) -> tuple[int, int]:
    base_x, base_z = slot
    scale_x = max(1, spacing_x // 4)
    scale_z = max(1, spacing_z // 4)
    return (int(base_x * scale_x), int(base_z * scale_z))


def _axis_clearance(size_a: int, size_b: int, min_gap: int) -> int:
    return int(math.ceil((float(size_a) + float(size_b)) / 2.0 + float(min_gap)))


def _overlaps_any(
    *,
    position: tuple[int, int],
    size: tuple[int, int],
    placed: Dict[str, Dict[str, int]],
    min_gap: int,
) -> bool:
    x, z = position
    width, depth = size

    for item in placed.values():
        other_x = _safe_int(item.get("x"), 0)
        other_z = _safe_int(item.get("z"), 0)
        other_width = max(1, _safe_int(item.get("width"), 3))
        other_depth = max(1, _safe_int(item.get("depth"), 3))

        clearance_x = _axis_clearance(width, other_width, min_gap)
        clearance_z = _axis_clearance(depth, other_depth, min_gap)

        if abs(x - other_x) < clearance_x and abs(z - other_z) < clearance_z:
            return True

    return False


def _resolve_collision(
    *,
    seed: tuple[int, int],
    size: tuple[int, int],
    placed: Dict[str, Dict[str, int]],
    spacing_x: int,
    spacing_z: int,
    min_gap: int,
) -> tuple[int, int]:
    x, z = seed
    if not _overlaps_any(position=(x, z), size=size, placed=placed, min_gap=min_gap):
        return (x, z)

    direction_x = 0
    if x > 0:
        direction_x = 1
    elif x < 0:
        direction_x = -1

    direction_z = 0
    if z > 0:
        direction_z = 1
    elif z < 0:
        direction_z = -1

    if direction_x == 0 and direction_z == 0:
        direction_x = 1

    step_x = max(1, spacing_x // 2)
    step_z = max(1, spacing_z // 2)

    for _ in range(64):
        x += direction_x * step_x
        z += direction_z * step_z
        if not _overlaps_any(position=(x, z), size=size, placed=placed, min_gap=min_gap):
            return (x, z)

    # deterministic fallback: keep radial direction and increase radius gradually.
    radius = max(spacing_x, spacing_z, 4)
    for _ in range(1, 129):
        candidate_x = direction_x * radius
        candidate_z = direction_z * radius
        if not _overlaps_any(position=(candidate_x, candidate_z), size=size, placed=placed, min_gap=min_gap):
            return (candidate_x, candidate_z)
        radius += max(step_x, step_z, 1)

    return (x, z)


def _placed_from_positions(
    *,
    positions: Dict[str, Dict[str, Any]],
    fragments: Dict[str, Dict[str, Any]],
) -> Dict[str, Dict[str, int]]:
    placed: Dict[str, Dict[str, int]] = {}

    for node_id, point in (positions or {}).items():
        node = str(node_id or "").strip().lower()
        if not node or not isinstance(point, dict):
            continue

        width, depth = _fragment_size(fragments.get(node))
        placed[node] = {
            "x": _safe_int(point.get("x"), 0),
            "z": _safe_int(point.get("z"), 0),
            "width": width,
            "depth": depth,
        }

    return placed


def layout_scene_graph(scene_graph: SceneGraph, fragments: Dict[str, Dict[str, Any]] | None = None) -> Dict[str, Any]:
    fragment_map = fragments if isinstance(fragments, dict) else {}
    root = str(scene_graph.root or "").strip().lower()

    positions: Dict[str, Dict[str, int]] = {}
    if not root:
        return {
            "strategy": "radial_v1",
            "root": "",
            "positions": positions,
        }

    positions[root] = {"x": 0, "z": 0}
    min_gap = _layout_min_gap(default=2)
    placed: Dict[str, Dict[str, int]] = {}

    children: list[str] = []
    for source, target in scene_graph.edges:
        if source == root:
            children.append(target)

    root_fragment = fragment_map.get(root)
    root_width, root_depth = _fragment_size(root_fragment)
    placed[root] = {
        "x": 0,
        "z": 0,
        "width": root_width,
        "depth": root_depth,
    }

    slots = _base_radial_slots()
    for index, child in enumerate(children):
        child_fragment = fragment_map.get(child)
        child_width, child_depth = _fragment_size(child_fragment)

        spacing_x = max(4, _axis_clearance(root_width, child_width, min_gap))
        spacing_z = max(4, _axis_clearance(root_depth, child_depth, min_gap))

        slot = slots[index] if index < len(slots) else (8 + index * 2, 0)
        seed = _scaled_slot(slot, spacing_x, spacing_z)
        dx, dz = _resolve_collision(
            seed=seed,
            size=(child_width, child_depth),
            placed=placed,
            spacing_x=spacing_x,
            spacing_z=spacing_z,
            min_gap=min_gap,
        )
        positions[child] = {"x": int(dx), "z": int(dz)}
        placed[child] = {
            "x": int(dx),
            "z": int(dz),
            "width": child_width,
            "depth": child_depth,
        }

    return {
        "strategy": "radial_v1",
        "root": root,
        "positions": positions,
    }


def event_offset_for_fragment(fragment_id: str, layout: Dict[str, Any] | None) -> Dict[str, float]:
    fragment = str(fragment_id or "").strip().lower()
    if not fragment or not isinstance(layout, dict):
        return {"dx": 0.0, "dy": 0.0, "dz": 0.0}

    positions = layout.get("positions")
    if not isinstance(positions, dict):
        return {"dx": 0.0, "dy": 0.0, "dz": 0.0}

    position = positions.get(fragment)
    if not isinstance(position, dict):
        return {"dx": 0.0, "dy": 0.0, "dz": 0.0}

    return {
        "dx": float(_safe_int(position.get("x"), 0)),
        "dy": 0.0,
        "dz": float(_safe_int(position.get("z"), 0)),
    }


def place_new_nodes(
    *,
    existing_positions: Dict[str, Dict[str, Any]] | None,
    parent_node: str,
    new_nodes: Iterable[str],
    fragments: Dict[str, Dict[str, Any]] | None = None,
    min_gap: int | None = None,
) -> Dict[str, Dict[str, int]]:
    fragment_map = fragments if isinstance(fragments, dict) else {}
    parent = str(parent_node or "").strip().lower()
    if not parent:
        return {}

    positions_map = existing_positions if isinstance(existing_positions, dict) else {}
    parent_position = positions_map.get(parent)
    parent_x = _safe_int(parent_position.get("x"), 0) if isinstance(parent_position, dict) else 0
    parent_z = _safe_int(parent_position.get("z"), 0) if isinstance(parent_position, dict) else 0

    normalized_gap = _layout_min_gap(default=2) if min_gap is None else _clamp_min_gap(min_gap, default=2)

    placed = _placed_from_positions(positions=positions_map, fragments=fragment_map)

    parent_width, parent_depth = _fragment_size(fragment_map.get(parent))
    if parent not in placed:
        placed[parent] = {
            "x": parent_x,
            "z": parent_z,
            "width": parent_width,
            "depth": parent_depth,
        }

    output: Dict[str, Dict[str, int]] = {}
    slots = _base_radial_slots()

    ordered_nodes: list[str] = []
    seen: set[str] = set()
    for raw_node in list(new_nodes or []):
        node = str(raw_node or "").strip().lower()
        if not node or node in seen:
            continue
        seen.add(node)
        ordered_nodes.append(node)

    for index, node in enumerate(ordered_nodes):
        if node in placed:
            continue

        width, depth = _fragment_size(fragment_map.get(node))

        spacing_x = max(4, _axis_clearance(parent_width, width, normalized_gap))
        spacing_z = max(4, _axis_clearance(parent_depth, depth, normalized_gap))

        if index < len(slots):
            slot = slots[index]
        else:
            extra_index = index - len(slots) + 1
            slot = (8 + extra_index * 2, 0)

        local_seed = _scaled_slot(slot, spacing_x, spacing_z)
        seed = (parent_x + int(local_seed[0]), parent_z + int(local_seed[1]))

        resolved_x, resolved_z = _resolve_collision(
            seed=seed,
            size=(width, depth),
            placed=placed,
            spacing_x=spacing_x,
            spacing_z=spacing_z,
            min_gap=normalized_gap,
        )

        placed[node] = {
            "x": int(resolved_x),
            "z": int(resolved_z),
            "width": width,
            "depth": depth,
        }
        output[node] = {
            "x": int(resolved_x),
            "z": int(resolved_z),
        }

    return output


def graph_nodes(scene_graph: SceneGraph) -> Iterable[str]:
    return list(scene_graph.nodes)
