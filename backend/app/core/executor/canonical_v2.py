from __future__ import annotations

import hashlib
import json
from typing import Any


def stable_hash_v2(value: Any) -> str:
    payload = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def canonicalize_block_ops(block_ops: list[dict]) -> list[dict]:
    normalized: list[dict] = []
    for entry in block_ops:
        if not isinstance(entry, dict):
            continue
        x = entry.get("x")
        y = entry.get("y")
        z = entry.get("z")
        block = entry.get("block")
        if not isinstance(x, int) or not isinstance(y, int) or not isinstance(z, int):
            continue
        if not isinstance(block, str) or not block:
            continue
        normalized.append(
            {
                "type": "setblock",
                "x": x,
                "y": y,
                "z": z,
                "block": block,
            }
        )
    normalized.sort(key=lambda item: (item["x"], item["y"], item["z"], item["block"]))
    return normalized


def canonicalize_entity_ops(entity_ops: list[dict]) -> list[dict]:
    normalized: list[dict] = []
    for entry in entity_ops:
        if not isinstance(entry, dict):
            continue
        if str(entry.get("type", "")).strip().lower() != "summon":
            continue

        entity_type = str(entry.get("entity_type", "")).strip().lower()
        x = entry.get("x")
        y = entry.get("y")
        z = entry.get("z")
        name = str(entry.get("name", "")).strip()
        profession = str(entry.get("profession", "")).strip().lower()
        no_ai = entry.get("no_ai")
        silent = entry.get("silent")
        rotation = entry.get("rotation")

        if entity_type != "villager":
            continue
        if not isinstance(x, int) or not isinstance(y, int) or not isinstance(z, int):
            continue
        if not isinstance(name, str) or not name:
            continue
        if profession != "none":
            continue
        if no_ai is not True or silent is not True:
            continue
        if not isinstance(rotation, int):
            continue

        normalized.append(
            {
                "type": "summon",
                "entity_type": "villager",
                "x": x,
                "y": y,
                "z": z,
                "name": name,
                "profession": "none",
                "no_ai": True,
                "silent": True,
                "rotation": rotation,
            }
        )

    normalized.sort(
        key=lambda item: (
            item["entity_type"],
            item["x"],
            item["y"],
            item["z"],
            item["name"],
            item["profession"],
            item["rotation"],
        )
    )
    return normalized


def canonicalize_final_commands(block_ops: list[dict], entity_ops: list[dict]) -> list[dict]:
    canonical_blocks = canonicalize_block_ops(block_ops)
    canonical_entities = canonicalize_entity_ops(entity_ops)

    merged = [*canonical_blocks, *canonical_entities]
    merged.sort(
        key=lambda item: (
            0 if item.get("type") == "setblock" else 1,
            int(item.get("x", 0)),
            int(item.get("y", 0)),
            int(item.get("z", 0)),
            stable_hash_v2(item),
        )
    )
    return merged


def final_commands_hash_v2(block_ops: list[dict], entity_ops: list[dict]) -> str:
    return stable_hash_v2(canonicalize_final_commands(block_ops, entity_ops))
