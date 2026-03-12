from __future__ import annotations

from typing import Any, Dict

from app.core.generation.spec_engine_v1 import generate_patch_from_text_v1
from app.core.patch.patch_merge_v1 import merge_blocks
from app.core.patch.patch_validate_v1 import validate_blocks
from app.core.scene.scene_engine_v1 import generate_scene_patch
from app.core.scene.scene_llm_v1 import generate_scene_spec_from_text_v1


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
        "compose_path": "scene_orchestrator_v1",
    }
    if metadata:
        payload.update(metadata)
    return payload


def compose_scene_and_structure(prompt: str) -> dict:
    scene_spec_result = generate_scene_spec_from_text_v1(prompt)
    if scene_spec_result.get("status") != "VALID":
        return _reject(scene_spec_result.get("failure_code", "INVALID_SCENE_SPEC"))

    scene_spec = scene_spec_result.get("scene_spec")
    if not isinstance(scene_spec, dict):
        return _reject("INVALID_SCENE_SPEC")

    scene_patch = generate_scene_patch(scene_spec)
    if scene_patch.get("build_status") != "SUCCESS":
        return _reject(
            scene_patch.get("failure_code", "SCENE_PATCH_FAILED"),
            {
                "scene_spec": scene_spec,
                "scene_patch": scene_patch,
            },
        )

    structure_patch = generate_patch_from_text_v1(prompt)
    if structure_patch.get("build_status") != "SUCCESS":
        return _reject(
            structure_patch.get("failure_code", "STRUCTURE_PATCH_FAILED"),
            {
                "scene_spec": scene_spec,
                "scene_patch": scene_patch,
                "structure_patch": structure_patch,
            },
        )

    scene_blocks = scene_patch.get("blocks") or []
    spec_blocks = structure_patch.get("blocks") or []

    merged = merge_blocks(scene_blocks, spec_blocks)
    if merged.get("status") != "SUCCESS":
        return _reject(
            merged.get("failure_code", "MERGE_FAILED"),
            {
                "scene_spec": scene_spec,
                "scene_patch": scene_patch,
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
                "scene_patch": scene_patch,
                "structure_patch": structure_patch,
                "merged": merged,
                "validation": validation,
                "scene_block_count": len(scene_blocks),
                "spec_block_count": len(spec_blocks),
                "merged_block_count": len(merged.get("blocks") or []),
            },
        )

    merged_blocks = merged.get("blocks") or []

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
        "compose_path": "scene_orchestrator_v1",
    }
