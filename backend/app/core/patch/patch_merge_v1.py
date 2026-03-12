from __future__ import annotations

import hashlib
import json
from typing import Any, Dict, List, Tuple


def _reject(failure_code: str) -> Dict[str, Any]:
    return {
        "status": "REJECTED",
        "failure_code": failure_code,
        "blocks": [],
        "conflicts_total": 0,
        "spec_dropped_total": 0,
        "hash": "",
    }


def _is_valid_block_entry(entry: Any) -> bool:
    if not isinstance(entry, dict):
        return False
    x = entry.get("x")
    y = entry.get("y")
    z = entry.get("z")
    block = entry.get("block")
    return (
        isinstance(x, int)
        and isinstance(y, int)
        and isinstance(z, int)
        and isinstance(block, str)
        and bool(block.strip())
    )


def _canonicalize_blocks(blocks: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    normalized = [{"x": b["x"], "y": b["y"], "z": b["z"], "block": b["block"].strip()} for b in blocks]
    normalized.sort(key=lambda item: (item["x"], item["y"], item["z"], item["block"]))
    return normalized


def _payload_hash(blocks: List[Dict[str, Any]]) -> str:
    payload = json.dumps(blocks, ensure_ascii=False, sort_keys=True)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def merge_blocks(scene_blocks: list[dict], spec_blocks: list[dict]) -> dict:
    if not isinstance(scene_blocks, list) or not isinstance(spec_blocks, list):
        return _reject("INVALID_BLOCK")

    if len(scene_blocks) == 0 and len(spec_blocks) == 0:
        return _reject("EMPTY_INPUT")

    if any(not _is_valid_block_entry(entry) for entry in scene_blocks):
        return _reject("INVALID_BLOCK")
    if any(not _is_valid_block_entry(entry) for entry in spec_blocks):
        return _reject("INVALID_BLOCK")

    canonical_scene = _canonicalize_blocks(scene_blocks)
    canonical_spec = _canonicalize_blocks(spec_blocks)

    merged: Dict[Tuple[int, int, int], str] = {}
    for block in canonical_spec:
        key = (block["x"], block["y"], block["z"])
        merged[key] = block["block"]

    conflicts_total = 0
    spec_dropped_total = 0

    for block in canonical_scene:
        key = (block["x"], block["y"], block["z"])
        scene_block = block["block"]
        if key in merged:
            conflicts_total += 1
            spec_block = merged[key]
            if scene_block == "air" and spec_block != "air":
                continue
            merged[key] = scene_block
            spec_dropped_total += 1
            continue
        merged[key] = scene_block

    merged_blocks = [
        {"x": x, "y": y, "z": z, "block": block}
        for (x, y, z), block in merged.items()
    ]
    merged_blocks.sort(key=lambda item: (item["x"], item["y"], item["z"], item["block"]))

    return {
        "status": "SUCCESS",
        "failure_code": "NONE",
        "blocks": merged_blocks,
        "conflicts_total": conflicts_total,
        "spec_dropped_total": spec_dropped_total,
        "hash": _payload_hash(merged_blocks),
    }
