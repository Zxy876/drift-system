from __future__ import annotations

from typing import Any, Dict

from app.core.generation.spec_engine_v1 import generate_patch_from_text_v1
from app.core.generation.spec_llm_v1 import generate_spec_from_text_v1
from app.core.mapping.projection_rule_registry import (
    DEFAULT_RULE_VERSION,
    get_projection_rule,
    list_supported_projection_effects,
    projection_supported,
)
from app.core.mapping.v2_mapper import map_scene_v2
from app.core.patch.patch_merge_v1 import merge_blocks
from app.core.patch.patch_validate_v1 import validate_blocks
from app.core.scene.scene_llm_v1 import generate_scene_spec_from_text_v1


PROJECTION_ATMOSPHERE_FOG_EFFECT = "atmosphere.fog"
PROJECTION_NPC_LAKE_GUARD_EFFECT = "npc_behavior.lake_guard"
ENGINE_VERSION = "engine_v2_1"


def _reject(failure_code: str, metadata: Dict[str, Any] | None = None) -> Dict[str, Any]:
    payload = {
        "status": "REJECTED",
        "failure_code": failure_code,
        "scene_spec": None,
        "scene_patch": {"build_status": "REJECTED", "failure_code": "NONE", "blocks": []},
        "structure_patch": {"build_status": "REJECTED", "failure_code": "NONE", "blocks": []},
        "merged": {
            "status": "REJECTED",
            "failure_code": failure_code,
            "blocks": [],
            "conflicts_total": 0,
            "spec_dropped_total": 0,
            "hash": "",
        },
        "validation": {"status": "REJECTED", "failure_code": failure_code},
        "scene_block_count": 0,
        "spec_block_count": 0,
        "merged_block_count": 0,
        "compose_path": "scene_orchestrator_v2",
    }
    if metadata:
        payload.update(metadata)
    return payload


def _build_mapper_context(prompt: str, scene_spec: dict, *, strict_mode: bool) -> dict:
    projected_structure_spec: dict = {}
    spec_result = generate_spec_from_text_v1(prompt)
    if spec_result.get("status") == "VALID" and isinstance(spec_result.get("spec"), dict):
        projected_structure_spec = spec_result.get("spec") or {}

    semantic_effects = scene_spec.get("semantic_effects") if isinstance(scene_spec, dict) else []
    if not isinstance(semantic_effects, list):
        semantic_effects = []

    rule_version = DEFAULT_RULE_VERSION
    engine_version = ENGINE_VERSION
    supported_effects = list_supported_projection_effects(rule_version, engine_version)

    mapper_decisions = []
    for effect in semantic_effects:
        if not isinstance(effect, dict):
            continue
        effect_type = str(effect.get("type", "")).strip().lower()
        effect_value = str(effect.get("value", "")).strip().lower()
        if not effect_type or not effect_value:
            continue

        semantic_key = f"{effect_type}.{effect_value}"
        if semantic_key in supported_effects:
            continue

        mapper_decisions.append(
            {
                "decision": "UNSUPPORTED_EFFECT",
                "semantic": semantic_key,
                "priority": 1,
                "reason": "projection_not_supported",
                "confidence": effect.get("confidence"),
            }
        )

    mapper_decisions.sort(key=lambda item: (item.get("semantic", ""), item.get("decision", "")))

    return {
        "strict_mode": strict_mode,
        "input_text": prompt,
        "rule_version": rule_version,
        "catalog_version": "catalog_v2_1",
        "expected_catalog_version": "catalog_v2_1",
        "engine_version": engine_version,
        "rule_registry_has_version": True,
        "ruleset_integrity_ok": True,
        "catalog_loaded": True,
        "resource_id": "res/default",
        "catalog_resource_ids": ["res/default"],
        "max_structure_blocks": 5000,
        "predicted_blocks": 0,
        "structure_block_count": 0,
        "unsupported_semantics": [],
        "supported_effects": supported_effects,
        "projected_structure_spec": projected_structure_spec,
        "mapper_decisions": mapper_decisions,
    }


def _has_fog_effect(scene_spec: dict) -> bool:
    semantic_effects = scene_spec.get("semantic_effects") if isinstance(scene_spec, dict) else []
    if not isinstance(semantic_effects, list):
        return False

    for effect in semantic_effects:
        if not isinstance(effect, dict):
            continue
        effect_type = str(effect.get("type", "")).strip().lower()
        effect_value = str(effect.get("value", "")).strip().lower()
        if f"{effect_type}.{effect_value}" == PROJECTION_ATMOSPHERE_FOG_EFFECT:
            return True
    return False


def _has_npc_lake_guard_effect(scene_spec: dict) -> bool:
    semantic_effects = scene_spec.get("semantic_effects") if isinstance(scene_spec, dict) else []
    if not isinstance(semantic_effects, list):
        return False

    for effect in semantic_effects:
        if not isinstance(effect, dict):
            continue
        effect_type = str(effect.get("type", "")).strip().lower()
        effect_value = str(effect.get("value", "")).strip().lower()
        if f"{effect_type}.{effect_value}" == PROJECTION_NPC_LAKE_GUARD_EFFECT:
            return True
    return False


def _project_fog_blocks(spec_blocks: list[dict], projection_rule: dict) -> tuple[list[dict], int]:
    if not spec_blocks:
        return [], 0

    valid_blocks = [
        block
        for block in spec_blocks
        if isinstance(block, dict) and all(axis in block for axis in ("x", "y", "z"))
    ]
    if not valid_blocks:
        return [], 0

    min_x = min(int(block["x"]) for block in valid_blocks)
    max_x = max(int(block["x"]) for block in valid_blocks)
    min_z = min(int(block["z"]) for block in valid_blocks)
    max_z = max(int(block["z"]) for block in valid_blocks)
    min_y = min(int(block["y"]) for block in valid_blocks)
    y_offset = int(projection_rule.get("y_offset", 1))
    target_y = min_y + y_offset
    block_id = str(projection_rule.get("block", "glass_pane"))

    occupied = {(int(block["x"]), int(block["y"]), int(block["z"])) for block in valid_blocks}

    projected: list[dict] = []
    skipped_conflicts = 0
    for x in range(min_x, max_x + 1):
        for z in range(min_z, max_z + 1):
            key = (x, target_y, z)
            if key in occupied:
                skipped_conflicts += 1
                continue
            projected.append(
                {
                    "x": x,
                    "y": target_y,
                    "z": z,
                    "block": block_id,
                }
            )

    return projected, skipped_conflicts


def _project_npc_lake_guard_blocks(spec_blocks: list[dict], projection_rule: dict) -> tuple[list[dict], int]:
    if not spec_blocks:
        return [], 0

    valid_blocks = [
        block
        for block in spec_blocks
        if isinstance(block, dict) and all(axis in block for axis in ("x", "y", "z"))
    ]
    if not valid_blocks:
        return [], 0

    min_x = min(int(block["x"]) for block in valid_blocks)
    max_x = max(int(block["x"]) for block in valid_blocks)
    min_y = min(int(block["y"]) for block in valid_blocks)
    min_z = min(int(block["z"]) for block in valid_blocks)

    x_offset = int(projection_rule.get("x_offset", 2))
    y_offset = int(projection_rule.get("y_offset", 0))
    z_offset = int(projection_rule.get("z_offset", 0))
    block_id = str(projection_rule.get("block", "npc_placeholder"))

    target = (max_x + x_offset, min_y + y_offset, min_z + z_offset)
    occupied = {(int(block["x"]), int(block["y"]), int(block["z"])) for block in valid_blocks}
    if target in occupied:
        return [], 1

    return [
        {
            "x": target[0],
            "y": target[1],
            "z": target[2],
            "block": block_id,
        }
    ], 0


def compose_scene_and_structure_v2(prompt: str, *, strict_mode: bool = False) -> dict:
    scene_spec_result = generate_scene_spec_from_text_v1(prompt)
    if scene_spec_result.get("status") != "VALID":
        return _reject(scene_spec_result.get("failure_code", "INVALID_SCENE_SPEC"))

    scene_spec = scene_spec_result.get("scene_spec")
    if not isinstance(scene_spec, dict):
        return _reject("INVALID_SCENE_SPEC")

    mapper_context = _build_mapper_context(prompt, scene_spec, strict_mode=strict_mode)
    mapping_result = map_scene_v2(scene_spec, mapper_context)

    if mapping_result.get("status") == "REJECTED":
        return _reject(
            mapping_result.get("failure_code", "MAPPING_REJECTED"),
            {
                "scene_spec": scene_spec,
                "mapping_result": mapping_result,
                "decision_trace": mapping_result.get("trace") or {},
            },
        )

    structure_patch = generate_patch_from_text_v1(prompt)
    if structure_patch.get("build_status") != "SUCCESS":
        return _reject(
            structure_patch.get("failure_code", "STRUCTURE_PATCH_FAILED"),
            {
                "scene_spec": scene_spec,
                "mapping_result": mapping_result,
                "decision_trace": mapping_result.get("trace") or {},
                "structure_patch": structure_patch,
            },
        )

    spec_blocks = structure_patch.get("blocks") or []
    scene_blocks: list[dict] = []
    fog_projection_added = 0
    fog_conflict_skipped = 0
    npc_projection_added = 0
    npc_conflict_skipped = 0
    rule_version = str(mapper_context.get("rule_version", DEFAULT_RULE_VERSION))
    engine_version = str(mapper_context.get("engine_version", ENGINE_VERSION))

    if _has_fog_effect(scene_spec) and projection_supported(rule_version, engine_version, PROJECTION_ATMOSPHERE_FOG_EFFECT):
        fog_rule = get_projection_rule(rule_version, PROJECTION_ATMOSPHERE_FOG_EFFECT) or {}
        scene_blocks, fog_conflict_skipped = _project_fog_blocks(spec_blocks, fog_rule)
        fog_projection_added = len(scene_blocks)

        trace = mapping_result.get("trace") if isinstance(mapping_result.get("trace"), dict) else None
        if trace is not None:
            decisions = trace.get("mapper_decisions")
            if isinstance(decisions, list):
                decisions.append(
                    {
                        "rule_id": fog_rule.get("rule_id"),
                        "priority": fog_rule.get("priority"),
                        "effect": PROJECTION_ATMOSPHERE_FOG_EFFECT,
                        "projection_blocks_added": fog_projection_added,
                        "conflict_blocks_skipped": fog_conflict_skipped,
                        "stage": fog_rule.get("stage"),
                        "fill_mode": fog_rule.get("fill_mode"),
                        "y_offset": fog_rule.get("y_offset"),
                        "block_id": fog_rule.get("block"),
                        "conflict_policy": fog_rule.get("conflict_policy"),
                    }
                )
                decisions.sort(key=lambda item: (str(item.get("rule_id", "")), str(item.get("semantic", "")), str(item.get("decision", ""))))

    if _has_npc_lake_guard_effect(scene_spec) and projection_supported(rule_version, engine_version, PROJECTION_NPC_LAKE_GUARD_EFFECT):
        npc_rule = get_projection_rule(rule_version, PROJECTION_NPC_LAKE_GUARD_EFFECT) or {}
        npc_blocks, npc_conflict_skipped = _project_npc_lake_guard_blocks(spec_blocks, npc_rule)
        scene_blocks.extend(npc_blocks)
        npc_projection_added = len(npc_blocks)

        trace = mapping_result.get("trace") if isinstance(mapping_result.get("trace"), dict) else None
        if trace is not None:
            decisions = trace.get("mapper_decisions")
            if isinstance(decisions, list):
                decisions.append(
                    {
                        "rule_id": npc_rule.get("rule_id"),
                        "priority": npc_rule.get("priority"),
                        "effect": PROJECTION_NPC_LAKE_GUARD_EFFECT,
                        "projection_blocks_added": npc_projection_added,
                        "conflict_blocks_skipped": npc_conflict_skipped,
                        "stage": npc_rule.get("stage"),
                        "conflict_policy": npc_rule.get("conflict_policy"),
                        "block_id": npc_rule.get("block"),
                        "x_offset": npc_rule.get("x_offset"),
                        "y_offset": npc_rule.get("y_offset"),
                        "z_offset": npc_rule.get("z_offset"),
                        "entity_type": npc_rule.get("entity_type"),
                        "name": npc_rule.get("name"),
                        "profession": npc_rule.get("profession"),
                        "ai_disabled": npc_rule.get("ai_disabled"),
                        "silent": npc_rule.get("silent"),
                        "rotation": npc_rule.get("rotation"),
                    }
                )
                decisions.sort(key=lambda item: (str(item.get("rule_id", "")), str(item.get("semantic", "")), str(item.get("decision", ""))))

    merged = merge_blocks(scene_blocks, spec_blocks)
    if merged.get("status") != "SUCCESS":
        return _reject(
            merged.get("failure_code", "MERGE_FAILED"),
            {
                "scene_spec": scene_spec,
                "mapping_result": mapping_result,
                "decision_trace": mapping_result.get("trace") or {},
                "structure_patch": structure_patch,
                "merged": merged,
            },
        )

    validation = validate_blocks(merged.get("blocks") or [])
    if validation.get("status") != "VALID":
        return _reject(
            validation.get("failure_code", "INVALID_BLOCKS"),
            {
                "scene_spec": scene_spec,
                "mapping_result": mapping_result,
                "decision_trace": mapping_result.get("trace") or {},
                "structure_patch": structure_patch,
                "merged": merged,
                "validation": validation,
                "scene_block_count": 0,
                "spec_block_count": len(spec_blocks),
                "merged_block_count": len(merged.get("blocks") or []),
            },
        )

    merged_blocks = merged.get("blocks") or []
    scene_patch = {
        "build_status": "SUCCESS",
        "failure_code": "NONE",
        "blocks": scene_blocks,
        "scene_path": "decision_mapper_v2",
        "scene_spec": scene_spec,
    }

    return {
        "status": "SUCCESS",
        "failure_code": "NONE",
        "scene_spec": scene_spec,
        "scene_patch": scene_patch,
        "structure_patch": structure_patch,
        "merged": merged,
        "validation": validation,
        "scene_block_count": len(scene_blocks),
        "spec_block_count": len(spec_blocks),
        "merged_block_count": len(merged_blocks),
        "merge_hash": merged.get("hash", ""),
        "mapping_result": mapping_result,
        "decision_trace": mapping_result.get("trace") or {},
        "compose_path": "scene_orchestrator_v2",
    }
