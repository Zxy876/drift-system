from __future__ import annotations

import hashlib
import json
from typing import Dict, List, Tuple


WorldState = Dict[Tuple[int, int, int], str]


def _stable_hash(value) -> str:
    payload = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _apply_v1_setblock_commands(commands: List[dict]) -> tuple[WorldState, int, int]:
    world: WorldState = {}
    executed = 0
    failed = 0

    for command in commands:
        if not isinstance(command, dict):
            failed += 1
            continue

        if command.get("op") != "setblock":
            failed += 1
            continue

        x = command.get("x")
        y = command.get("y")
        z = command.get("z")
        block = command.get("block")

        if not isinstance(x, int) or not isinstance(y, int) or not isinstance(z, int):
            failed += 1
            continue
        if not isinstance(block, str) or not block:
            failed += 1
            continue

        world[(x, y, z)] = block
        executed += 1

    return world, executed, failed


def _normalize_world(world: WorldState) -> list[dict]:
    return [
        {"x": x, "y": y, "z": z, "block": block}
        for (x, y, z), block in sorted(world.items(), key=lambda kv: (kv[0][0], kv[0][1], kv[0][2], kv[1]))
    ]


def execute_payload_v1(payload: dict) -> dict:
    if not isinstance(payload, dict):
        return {
            "status": "REJECTED",
            "failure_code": "INVALID_PAYLOAD",
        }

    if str(payload.get("version") or "").strip() != "plugin_payload_v1":
        return {
            "status": "REJECTED",
            "failure_code": "UNSUPPORTED_PAYLOAD_VERSION",
        }

    commands = payload.get("commands")
    if not isinstance(commands, list):
        return {
            "status": "REJECTED",
            "failure_code": "INVALID_COMMANDS",
        }

    world, executed, failed = _apply_v1_setblock_commands(commands)
    normalized = _normalize_world(world)

    return {
        "status": "SUCCESS",
        "failure_code": "NONE",
        "executed_commands": executed,
        "failed_commands": failed,
        "world_block_count": len(normalized),
        "world_state_hash": _stable_hash(normalized),
        "world_state_preview": normalized[:5],
    }
