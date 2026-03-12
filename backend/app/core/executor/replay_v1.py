from __future__ import annotations

from app.core.executor.executor_v1 import _apply_v1_setblock_commands, _normalize_world, _stable_hash


def replay_payload_v1(payload: dict) -> dict:
    if not isinstance(payload, dict):
        return {
            "status": "REJECTED",
            "failure_code": "INVALID_PAYLOAD",
        }

    if str(payload.get("version") or "").strip() != "plugin_payload_v1":
        return {
            "status": "REJECTED",
            "failure_code": "UNSUPPORTED_REPLAY_VERSION",
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
