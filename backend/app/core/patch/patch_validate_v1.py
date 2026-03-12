from __future__ import annotations

from typing import Any, Dict

from app.core.generation.material_alias_mapper import BLOCK_ID_WHITELIST


MIN_WORLD_Y = 0
MAX_WORLD_Y = 320
SCENE_BLOCK_ID_WHITELIST = {
    "water",
    "grass_block",
    "lantern",
    "npc_placeholder",
    "oak_leaves",
}
ALLOWED_BLOCK_IDS = set(BLOCK_ID_WHITELIST) | SCENE_BLOCK_ID_WHITELIST


def validate_blocks(blocks: list[dict], *, max_blocks: int = 5000) -> dict:
    if not isinstance(blocks, list) or len(blocks) == 0:
        return {"status": "REJECTED", "failure_code": "EMPTY_BLOCKS"}

    if len(blocks) > max_blocks:
        return {"status": "REJECTED", "failure_code": "TOO_MANY_BLOCKS"}

    for block in blocks:
        if not isinstance(block, dict):
            return {"status": "REJECTED", "failure_code": "INVALID_COORD"}

        x: Any = block.get("x")
        y: Any = block.get("y")
        z: Any = block.get("z")
        block_id: Any = block.get("block")

        if not isinstance(x, int) or not isinstance(y, int) or not isinstance(z, int):
            return {"status": "REJECTED", "failure_code": "INVALID_COORD"}

        if y < MIN_WORLD_Y or y > MAX_WORLD_Y:
            return {"status": "REJECTED", "failure_code": "INVALID_COORD"}

        if not isinstance(block_id, str) or not block_id.strip():
            return {"status": "REJECTED", "failure_code": "INVALID_BLOCK_ID"}

        if block_id not in ALLOWED_BLOCK_IDS:
            return {"status": "REJECTED", "failure_code": "INVALID_BLOCK_ID"}

    return {"status": "VALID", "failure_code": "NONE"}
