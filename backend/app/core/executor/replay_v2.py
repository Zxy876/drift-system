from __future__ import annotations

from app.core.executor.canonical_v2 import canonicalize_final_commands, stable_hash_v2


def _split_commands(commands: list[dict]) -> tuple[list[dict], list[dict]]:
    block_ops: list[dict] = []
    entity_ops: list[dict] = []

    for command in commands:
        if not isinstance(command, dict):
            continue
        command_type = str(command.get("type") or command.get("op") or "").strip().lower()
        if command_type == "setblock":
            block_ops.append(
                {
                    "x": command.get("x"),
                    "y": command.get("y"),
                    "z": command.get("z"),
                    "block": command.get("block"),
                }
            )
        elif command_type == "summon":
            entity_ops.append(
                {
                    "type": "summon",
                    "entity_type": command.get("entity_type"),
                    "x": command.get("x"),
                    "y": command.get("y"),
                    "z": command.get("z"),
                    "name": command.get("name"),
                    "profession": command.get("profession"),
                    "no_ai": command.get("no_ai"),
                    "silent": command.get("silent"),
                    "rotation": command.get("rotation"),
                }
            )

    return block_ops, entity_ops


def replay_payload_v2(payload: dict) -> dict:
    if not isinstance(payload, dict):
        return {"status": "REJECTED", "failure_code": "INVALID_PAYLOAD"}

    if str(payload.get("version", "")).strip() != "plugin_payload_v2":
        return {"status": "REJECTED", "failure_code": "INVALID_PAYLOAD_VERSION"}

    commands = payload.get("commands")
    if not isinstance(commands, list):
        return {"status": "REJECTED", "failure_code": "INVALID_COMMANDS"}

    block_ops, entity_ops = _split_commands(commands)
    canonical_commands = canonicalize_final_commands(block_ops, entity_ops)
    actual_hash = stable_hash_v2(canonical_commands)

    expected_hash = ""
    hash_data = payload.get("hash")
    if isinstance(hash_data, dict):
        expected_hash = str(hash_data.get("final_commands") or "")
    if not expected_hash:
        expected_hash = str(payload.get("final_commands_hash_v2") or "")

    if expected_hash and expected_hash != actual_hash:
        return {
            "status": "REJECTED",
            "failure_code": "FINAL_COMMANDS_HASH_MISMATCH",
            "expected_final_commands_hash": expected_hash,
            "actual_final_commands_hash": actual_hash,
        }

    world_blocks = {}
    world_entities = []

    for command in canonical_commands:
        command_type = command.get("type")
        if command_type == "setblock":
            key = (int(command["x"]), int(command["y"]), int(command["z"]))
            world_blocks[key] = str(command["block"])
            continue

        if command_type == "summon":
            world_entities.append(
                {
                    "type": "summon",
                    "entity_type": str(command.get("entity_type")),
                    "x": int(command.get("x")),
                    "y": int(command.get("y")),
                    "z": int(command.get("z")),
                    "name": str(command.get("name")),
                    "profession": str(command.get("profession")),
                    "no_ai": bool(command.get("no_ai")),
                    "silent": bool(command.get("silent")),
                    "rotation": int(command.get("rotation")),
                }
            )

    normalized_blocks = [
        {"x": x, "y": y, "z": z, "block": block}
        for (x, y, z), block in sorted(world_blocks.items(), key=lambda kv: (kv[0][0], kv[0][1], kv[0][2], kv[1]))
    ]
    normalized_entities = sorted(
        world_entities,
        key=lambda item: (
            item["entity_type"],
            item["x"],
            item["y"],
            item["z"],
            item["name"],
            item["rotation"],
        ),
    )

    world_state = {
        "blocks": normalized_blocks,
        "entities": normalized_entities,
    }

    return {
        "status": "SUCCESS",
        "failure_code": "NONE",
        "final_commands_hash_v2": actual_hash,
        "world_state_hash": stable_hash_v2(world_state),
        "world_block_count": len(normalized_blocks),
        "world_entity_count": len(normalized_entities),
        "world_state_preview": {
            "blocks": normalized_blocks[:5],
            "entities": normalized_entities[:3],
        },
    }
