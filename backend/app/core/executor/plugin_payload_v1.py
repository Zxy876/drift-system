from __future__ import annotations

import hashlib
import json
from typing import Any, Dict, List

from app.core.patch.patch_validate_v1 import validate_blocks


DEFAULT_ORIGIN = {
    "base_x": 0,
    "base_y": 64,
    "base_z": 0,
    "anchor_mode": "fixed",
}


def _stable_hash(value: Any) -> str:
    payload = json.dumps(value, ensure_ascii=False, sort_keys=True)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _normalize_origin(origin: dict | None) -> dict:
    merged = dict(DEFAULT_ORIGIN)
    if isinstance(origin, dict):
        merged.update({k: origin[k] for k in origin.keys() if k in merged})

    base_x = merged.get("base_x")
    base_y = merged.get("base_y")
    base_z = merged.get("base_z")
    anchor_mode = merged.get("anchor_mode")

    if not isinstance(base_x, int) or not isinstance(base_y, int) or not isinstance(base_z, int):
        raise ValueError("origin base coordinates must be integers")
    if anchor_mode not in {"player", "fixed"}:
        raise ValueError("origin.anchor_mode must be 'player' or 'fixed'")

    return {
        "base_x": base_x,
        "base_y": base_y,
        "base_z": base_z,
        "anchor_mode": anchor_mode,
    }


def _build_id(merged_blocks_hash: str, player_id: str, origin: dict) -> str:
    seed = {
        "merged_blocks_hash": merged_blocks_hash,
        "player_id": player_id,
        "base_x": origin["base_x"],
        "base_y": origin["base_y"],
        "base_z": origin["base_z"],
    }
    return _stable_hash(seed)


def _sorted_blocks(blocks: list[dict]) -> List[Dict[str, Any]]:
    normalized = [
        {
            "x": entry["x"],
            "y": entry["y"],
            "z": entry["z"],
            "block": entry["block"],
        }
        for entry in blocks
    ]
    normalized.sort(key=lambda item: (item["x"], item["y"], item["z"], item["block"]))
    return normalized


def build_plugin_payload_v1(result: dict, *, player_id: str, origin: dict | None = None) -> dict:
    if not isinstance(result, dict):
        raise ValueError("result must be dict")
    if result.get("status") != "SUCCESS":
        raise ValueError("compose result must be SUCCESS")
    if not isinstance(player_id, str) or not player_id.strip():
        raise ValueError("player_id must be non-empty string")

    normalized_origin = _normalize_origin(origin)

    merged = result.get("merged") or {}
    merged_blocks = merged.get("blocks") or []
    merged_blocks_sorted = _sorted_blocks(merged_blocks)

    validation = validate_blocks(merged_blocks_sorted)
    if validation.get("status") != "VALID":
        raise ValueError(f"merged blocks invalid: {validation.get('failure_code', 'INVALID_BLOCKS')}")

    commands = [
        {
            "op": "setblock",
            "x": block["x"] + normalized_origin["base_x"],
            "y": block["y"] + normalized_origin["base_y"],
            "z": block["z"] + normalized_origin["base_z"],
            "block": block["block"],
        }
        for block in merged_blocks_sorted
    ]

    scene_spec = result.get("scene_spec") or {}
    structure_patch = result.get("structure_patch") or {}
    scene_patch = result.get("scene_patch") or {}

    merged_blocks_hash = merged.get("hash") or _stable_hash(merged_blocks_sorted)
    payload = {
        "version": "plugin_payload_v1",
        "build_id": _build_id(merged_blocks_hash, player_id.strip(), normalized_origin),
        "player_id": player_id.strip(),
        "build_path": structure_patch.get("build_path", "spec_engine_v1"),
        "patch_source": structure_patch.get("patch_source", "deterministic_engine"),
        "scene_path": scene_patch.get("scene_path", "scene_engine_v1"),
        "hash": {
            "scene_spec": _stable_hash(scene_spec),
            "spec": _stable_hash(structure_patch.get("blocks") or []),
            "merged_blocks": merged_blocks_hash,
        },
        "stats": {
            "scene_block_count": result.get("scene_block_count", len(scene_patch.get("blocks") or [])),
            "spec_block_count": result.get("spec_block_count", len(structure_patch.get("blocks") or [])),
            "merged_block_count": result.get("merged_block_count", len(merged_blocks_sorted)),
            "conflicts_total": merged.get("conflicts_total", 0),
            "spec_dropped_total": merged.get("spec_dropped_total", 0),
        },
        "origin": normalized_origin,
        "commands": commands,
    }

    return payload
