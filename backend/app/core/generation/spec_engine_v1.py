from __future__ import annotations

from typing import Any, Dict, List

from app.core.generation.deterministic_build_engine import build_from_spec
from app.core.generation.material_alias_mapper import BLOCK_ID_WHITELIST, map_roles_to_blocks
from app.core.generation.spec_llm_v1 import generate_spec_from_text_v1


def _result(build_status: str, failure_code: str, blocks: List[Dict[str, Any]] | None = None) -> Dict[str, Any]:
    return {
        "build_status": build_status,
        "failure_code": failure_code,
        "build_path": "spec_engine_v1",
        "patch_source": "deterministic_engine",
        "blocks": blocks or [],
    }


def _validate_execution_blocks(blocks: Any) -> str:
    if not isinstance(blocks, list) or not blocks:
        return "EMPTY_BLOCKS"

    for entry in blocks:
        if not isinstance(entry, dict):
            return "INVALID_BLOCK_ENTRY"

        x = entry.get("x")
        y = entry.get("y")
        z = entry.get("z")
        block_id = entry.get("block")

        if not isinstance(x, int) or not isinstance(y, int) or not isinstance(z, int):
            return "INVALID_BLOCK_ENTRY"
        if not isinstance(block_id, str) or block_id not in BLOCK_ID_WHITELIST:
            return "INVALID_BLOCK_ID"

    return "NONE"


def generate_patch_from_text_v1(text: str) -> dict:
    spec_result = generate_spec_from_text_v1(text)
    if spec_result.get("status") != "VALID":
        return _result("REJECTED", spec_result.get("failure_code", "INVALID_SPEC"))

    normalized_spec = spec_result.get("spec")
    if not isinstance(normalized_spec, dict):
        return _result("REJECTED", "INVALID_SPEC")

    build_result = build_from_spec(normalized_spec)
    if build_result.get("build_status") != "SUCCESS":
        return _result("REJECTED", build_result.get("failure_code", "INVALID_SPEC"))

    role_blocks = build_result.get("blocks")
    material_preference = normalized_spec.get("material_preference")
    mapped = map_roles_to_blocks(role_blocks, material_preference)
    if mapped.get("status") != "SUCCESS":
        return _result("REJECTED", mapped.get("failure_code", "INVALID_MAPPING"))

    execution_blocks = mapped.get("blocks")
    execution_failure = _validate_execution_blocks(execution_blocks)
    if execution_failure != "NONE":
        return _result("REJECTED", execution_failure)

    return _result("SUCCESS", "NONE", execution_blocks)
