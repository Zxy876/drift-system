from __future__ import annotations

from dataclasses import dataclass
import re
from typing import Any

from app.core.executor.canonical_v2 import (
    canonicalize_block_ops,
    canonicalize_entity_ops,
    canonicalize_final_commands,
    final_commands_hash_v2,
    stable_hash_v2,
)
from app.core.mapping.projection_rule_registry import DEFAULT_RULE_VERSION, get_projection_rule
from app.core.patch.patch_validate_v1 import validate_blocks


ENGINE_VERSION = "engine_v2_1"
NPC_PLACEHOLDER_BLOCK = "npc_placeholder"
NPC_EFFECT_KEY = "npc_behavior.lake_guard"
DEFAULT_ANCHOR_ID = "home"
ANCHOR_ID_PATTERN = re.compile(r"^[a-z0-9][a-z0-9_-]{0,31}$")

DEFAULT_ORIGIN = {
    "base_x": 0,
    "base_y": 64,
    "base_z": 0,
    "anchor_mode": "fixed",
}


@dataclass
class PayloadV2BuildTrace:
    status: str
    failure_code: str
    degrade_reason: str | None
    lost_semantics: list[str]

    def to_dict(self) -> dict:
        return {
            "status": self.status,
            "failure_code": self.failure_code,
            "degrade_reason": self.degrade_reason,
            "lost_semantics": list(self.lost_semantics),
        }


class PayloadV2BuildError(Exception):
    def __init__(self, failure_code: str, trace: dict | None = None):
        super().__init__(failure_code)
        self.failure_code = failure_code
        self.trace = trace or {}


def _normalize_anchor_id(anchor_id: str | None) -> str:
    if anchor_id is None:
        return DEFAULT_ANCHOR_ID
    if not isinstance(anchor_id, str) or not anchor_id.strip():
        raise ValueError("anchor must be non-empty string")

    normalized = anchor_id.strip().lower()
    if not ANCHOR_ID_PATTERN.fullmatch(normalized):
        raise ValueError("anchor must match ^[a-z0-9][a-z0-9_-]{0,31}$")

    return normalized


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


def _normalize_anchors(
    *,
    normalized_origin: dict,
    active_anchor: str,
    anchors: dict | None,
) -> dict[str, dict]:
    normalized_anchors: dict[str, dict] = {
        active_anchor: dict(normalized_origin),
    }

    if anchors is not None:
        if not isinstance(anchors, dict):
            raise ValueError("anchors must be dict[str, origin]")

        for raw_anchor_id, raw_origin in anchors.items():
            anchor_id = _normalize_anchor_id(str(raw_anchor_id))
            if not isinstance(raw_origin, dict):
                raise ValueError("anchors entries must be objects")
            normalized_anchors[anchor_id] = _normalize_origin(raw_origin)

    if active_anchor not in normalized_anchors:
        normalized_anchors[active_anchor] = dict(normalized_origin)

    return {key: normalized_anchors[key] for key in sorted(normalized_anchors.keys())}


def _resolve_rule_version(result: dict) -> str:
    mapping_result = result.get("mapping_result") if isinstance(result, dict) else {}
    trace = mapping_result.get("trace") if isinstance(mapping_result, dict) else {}
    rule_version = trace.get("rule_version") if isinstance(trace, dict) else None
    if isinstance(rule_version, str) and rule_version.strip():
        return rule_version.strip()
    return DEFAULT_RULE_VERSION


def _summon_template_from_rule(rule_version: str) -> dict:
    rule = get_projection_rule(rule_version, NPC_EFFECT_KEY) or {}
    return {
        "type": "summon",
        "entity_type": "villager",
        "name": str(rule.get("name") or "Lake Guard"),
        "profession": "none",
        "no_ai": True,
        "silent": True,
        "rotation": int(rule.get("rotation") or 90),
    }


def _build_id(final_hash: str, player_id: str, origin: dict) -> str:
    seed = {
        "final_commands_hash_v2": final_hash,
        "player_id": player_id,
        "base_x": origin["base_x"],
        "base_y": origin["base_y"],
        "base_z": origin["base_z"],
    }
    return stable_hash_v2(seed)


def _extract_entity_ops_from_merged(
    merged_blocks: list[dict],
    *,
    normalized_origin: dict,
    strict_mode: bool,
    rule_version: str,
) -> tuple[list[dict], list[dict], PayloadV2BuildTrace]:
    npc_placeholders = [
        block
        for block in merged_blocks
        if isinstance(block, dict) and str(block.get("block", "")).strip().lower() == NPC_PLACEHOLDER_BLOCK
    ]
    block_only = [
        block
        for block in merged_blocks
        if isinstance(block, dict) and str(block.get("block", "")).strip().lower() != NPC_PLACEHOLDER_BLOCK
    ]

    if len(npc_placeholders) > 1:
        if strict_mode:
            trace = PayloadV2BuildTrace(
                status="REJECTED",
                failure_code="MULTI_ENTITY_NOT_ALLOWED",
                degrade_reason=None,
                lost_semantics=["npc_behavior.multi_entity"],
            )
            return block_only, [], trace

        npc_placeholders = [npc_placeholders[0]]
        trace = PayloadV2BuildTrace(
            status="DEGRADED",
            failure_code="NONE",
            degrade_reason="ENTITY_CAPABILITY_GAP",
            lost_semantics=["npc_behavior.multi_entity"],
        )
    else:
        trace = PayloadV2BuildTrace(
            status="OK",
            failure_code="NONE",
            degrade_reason=None,
            lost_semantics=[],
        )

    entity_ops: list[dict] = []
    if npc_placeholders:
        placeholder = npc_placeholders[0]
        template = _summon_template_from_rule(rule_version)
        entity_ops.append(
            {
                **template,
                "x": int(placeholder["x"]) + normalized_origin["base_x"],
                "y": int(placeholder["y"]) + normalized_origin["base_y"],
                "z": int(placeholder["z"]) + normalized_origin["base_z"],
            }
        )

    return block_only, canonicalize_entity_ops(entity_ops), trace


def build_plugin_payload_v2_with_trace(
    result: dict,
    *,
    player_id: str,
    origin: dict | None = None,
    strict_mode: bool = True,
    anchor: str | None = None,
    anchors: dict | None = None,
) -> tuple[dict, dict]:
    if not isinstance(result, dict):
        raise ValueError("result must be dict")
    if result.get("status") != "SUCCESS":
        raise ValueError("compose result must be SUCCESS")
    if not isinstance(player_id, str) or not player_id.strip():
        raise ValueError("player_id must be non-empty string")

    normalized_origin = _normalize_origin(origin)
    active_anchor = _normalize_anchor_id(anchor)
    anchor_map = _normalize_anchors(
        normalized_origin=normalized_origin,
        active_anchor=active_anchor,
        anchors=anchors,
    )
    active_origin = dict(anchor_map[active_anchor])
    merged = result.get("merged") or {}
    merged_blocks = merged.get("blocks") or []

    validation = validate_blocks(merged_blocks)
    if validation.get("status") != "VALID":
        raise PayloadV2BuildError(
            validation.get("failure_code", "INVALID_BLOCKS"),
            {
                "status": "REJECTED",
                "failure_code": validation.get("failure_code", "INVALID_BLOCKS"),
                "lost_semantics": [],
            },
        )

    rule_version = _resolve_rule_version(result)
    merged_block_only, entity_ops, trace = _extract_entity_ops_from_merged(
        merged_blocks,
        normalized_origin=active_origin,
        strict_mode=bool(strict_mode),
        rule_version=rule_version,
    )
    if trace.status == "REJECTED":
        raise PayloadV2BuildError(trace.failure_code, trace.to_dict())

    relative_block_ops_canonical = canonicalize_block_ops(
        [
            {
                "x": int(block["x"]),
                "y": int(block["y"]),
                "z": int(block["z"]),
                "block": block["block"],
            }
            for block in merged_block_only
            if isinstance(block, dict)
        ]
    )

    block_ops_input = [
        {
            "x": int(block["x"]) + active_origin["base_x"],
            "y": int(block["y"]) + active_origin["base_y"],
            "z": int(block["z"]) + active_origin["base_z"],
            "block": block["block"],
        }
        for block in relative_block_ops_canonical
    ]
    block_ops = canonicalize_block_ops(block_ops_input)

    block_ops_payload = [
        {
            "anchor": active_anchor,
            "offset": [int(op["x"]), int(op["y"]), int(op["z"])],
            "block": op["block"],
        }
        for op in relative_block_ops_canonical
    ]

    entity_ops_payload = [
        {
            "type": "summon",
            "entity_type": str(entity_op.get("entity_type")),
            "anchor": active_anchor,
            "offset": [
                int(entity_op.get("x")) - active_origin["base_x"],
                int(entity_op.get("y")) - active_origin["base_y"],
                int(entity_op.get("z")) - active_origin["base_z"],
            ],
            "name": str(entity_op.get("name")),
            "profession": str(entity_op.get("profession")),
            "no_ai": bool(entity_op.get("no_ai")),
            "silent": bool(entity_op.get("silent")),
            "rotation": int(entity_op.get("rotation")),
        }
        for entity_op in entity_ops
        if isinstance(entity_op, dict)
    ]

    commands = canonicalize_final_commands(block_ops, entity_ops)
    final_hash = final_commands_hash_v2(block_ops, entity_ops)

    scene_spec = result.get("scene_spec") or {}
    structure_patch = result.get("structure_patch") or {}
    scene_patch = result.get("scene_patch") or {}

    payload = {
        "version": "plugin_payload_v2",
        "payload_version": "v2.1",
        "build_id": _build_id(final_hash, player_id.strip(), active_origin),
        "player_id": player_id.strip(),
        "build_path": structure_patch.get("build_path", "spec_engine_v1"),
        "patch_source": structure_patch.get("patch_source", "deterministic_engine"),
        "scene_path": scene_patch.get("scene_path", "scene_engine_v1"),
        "rule_version": rule_version,
        "engine_version": ENGINE_VERSION,
        "hash": {
            "scene_spec": stable_hash_v2(scene_spec),
            "spec": stable_hash_v2(structure_patch.get("blocks") or []),
            "final_commands": final_hash,
        },
        "final_commands_hash_v2": final_hash,
        "stats": {
            "scene_block_count": result.get("scene_block_count", len(scene_patch.get("blocks") or [])),
            "spec_block_count": result.get("spec_block_count", len(structure_patch.get("blocks") or [])),
            "merged_block_count": len(block_ops),
            "entity_command_count": len(entity_ops),
            "conflicts_total": merged.get("conflicts_total", 0),
            "spec_dropped_total": merged.get("spec_dropped_total", 0),
        },
        "origin": active_origin,
        "anchor": active_anchor,
        "anchors": anchor_map,
        "block_ops": block_ops_payload,
        "entity_ops": entity_ops_payload,
        "commands": commands,
    }
    return payload, trace.to_dict()


def build_plugin_payload_v2(
    result: dict,
    *,
    player_id: str,
    origin: dict | None = None,
    strict_mode: bool = True,
    anchor: str | None = None,
    anchors: dict | None = None,
) -> dict:
    payload, _trace = build_plugin_payload_v2_with_trace(
        result,
        player_id=player_id,
        origin=origin,
        strict_mode=strict_mode,
        anchor=anchor,
        anchors=anchors,
    )
    return payload
