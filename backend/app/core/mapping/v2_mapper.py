from __future__ import annotations

import hashlib
import json
from typing import Any, Dict, List


REQUIRED_SCENE_FIELDS = {"scene_type", "time_of_day", "weather", "mood"}
VALIDATOR_FAILURE_CODES = {"INVALID_BLOCK_ID", "INVALID_COORD", "TOO_MANY_BLOCKS", "EMPTY_BLOCKS"}
FALLBACK_STRUCTURE = "v2->structure_spec->v1_commands"
FALLBACK_METADATA = "v2->metadata_only"


def _stable_hash(value: Any) -> str:
    payload = json.dumps(value, ensure_ascii=False, sort_keys=True)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _get_context(context: dict | None) -> dict:
    if isinstance(context, dict):
        return context
    return {}


def _get_enums(ctx: dict, rule_version: str) -> dict:
    enums = ctx.get("enums") if isinstance(ctx.get("enums"), dict) else {}
    by_rule = enums.get(rule_version)
    if isinstance(by_rule, dict):
        return by_rule

    return {
        "scene_type": {"lake", "village", "forest", "plain"},
        "time_of_day": {"day", "night"},
        "weather": {"clear", "rain"},
        "mood": {"calm", "tense", "mysterious"},
    }


def _base_trace(scene_spec: dict, ctx: dict) -> dict:
    rule_version = str(ctx.get("rule_version", "rule_v2_default"))
    catalog_version = str(ctx.get("catalog_version", "catalog_v2_default"))
    engine_version = str(ctx.get("engine_version", "engine_v2_default"))

    final_commands = ctx.get("final_commands")
    if not isinstance(final_commands, list):
        final_commands = []

    decisions = ctx.get("mapper_decisions")
    if not isinstance(decisions, list):
        decisions = []

    return {
        "input_text_hash": str(ctx.get("input_text_hash") or _stable_hash(ctx.get("input_text", ""))),
        "scene_spec_hash": _stable_hash(scene_spec if isinstance(scene_spec, dict) else {}),
        "rule_version": rule_version,
        "catalog_version": catalog_version,
        "engine_version": engine_version,
        "mapper_decisions": decisions,
        "degrade_reason": None,
        "lost_semantics": [],
        "fallback_path": None,
        "final_commands_hash": str(ctx.get("final_commands_hash") or _stable_hash(final_commands)),
    }


def _result_ok(trace: dict, projected_structure_spec: dict) -> dict:
    return {
        "status": "OK",
        "failure_code": "NONE",
        "degrade_reason": None,
        "lost_semantics": [],
        "fallback_path": None,
        "trace": trace,
        "projected_structure_spec": projected_structure_spec,
    }


def _result_ok_with_losses(trace: dict, projected_structure_spec: dict, lost_semantics: list[str]) -> dict:
    normalized_lost = sorted(set(str(item) for item in lost_semantics))
    trace["lost_semantics"] = normalized_lost
    return {
        "status": "OK",
        "failure_code": "NONE",
        "degrade_reason": None,
        "lost_semantics": normalized_lost,
        "fallback_path": None,
        "trace": trace,
        "projected_structure_spec": projected_structure_spec,
    }


def _result_rejected(trace: dict, failure_code: str, lost_semantics: list[str] | None = None) -> dict:
    normalized_lost = sorted(set(str(item) for item in (lost_semantics or [])))
    trace["lost_semantics"] = normalized_lost
    return {
        "status": "REJECTED",
        "failure_code": failure_code,
        "degrade_reason": None,
        "lost_semantics": normalized_lost,
        "fallback_path": None,
        "trace": trace,
        "projected_structure_spec": {},
    }


def _result_degraded(
    trace: dict,
    degrade_reason: str,
    lost_semantics: list[str],
    fallback_path: str,
    projected_structure_spec: dict,
) -> dict:
    normalized_lost = sorted(set(str(item) for item in lost_semantics))
    trace["degrade_reason"] = degrade_reason
    trace["lost_semantics"] = normalized_lost
    trace["fallback_path"] = fallback_path

    return {
        "status": "DEGRADED",
        "failure_code": "NONE",
        "degrade_reason": degrade_reason,
        "lost_semantics": normalized_lost,
        "fallback_path": fallback_path,
        "trace": trace,
        "projected_structure_spec": projected_structure_spec,
    }


def _strict(ctx: dict) -> bool:
    return bool(ctx.get("strict_mode", False))


def _to_list(value: Any) -> list:
    return value if isinstance(value, list) else []


def _normalize_semantic_key(effect_type: str, effect_value: str) -> str:
    return f"{effect_type.strip().lower()}.{effect_value.strip().lower()}"


def _collect_scene_semantics(scene_spec: dict) -> list[str]:
    semantic_effects = scene_spec.get("semantic_effects") if isinstance(scene_spec, dict) else []
    if not isinstance(semantic_effects, list):
        return []

    keys: list[str] = []
    for effect in semantic_effects:
        if not isinstance(effect, dict):
            continue
        effect_type = str(effect.get("type", "")).strip().lower()
        effect_value = str(effect.get("value", "")).strip().lower()
        if not effect_type or not effect_value:
            continue
        keys.append(_normalize_semantic_key(effect_type, effect_value))
    return sorted(set(keys))


def map_scene_v2(scene_spec: dict, context: dict | None = None) -> dict:
    ctx = _get_context(context)
    projected_structure_spec = ctx.get("projected_structure_spec") if isinstance(ctx.get("projected_structure_spec"), dict) else {}
    trace = _base_trace(scene_spec, ctx)

    if not isinstance(scene_spec, dict):
        missing = sorted(REQUIRED_SCENE_FIELDS)
        if _strict(ctx):
            return _result_rejected(trace, "MISSING_SCENE_FIELD")
        return _result_degraded(trace, "SCENE_SPEC_INCOMPLETE", [f"SCENE.{field}" for field in missing], FALLBACK_STRUCTURE, projected_structure_spec)

    missing_fields = sorted(REQUIRED_SCENE_FIELDS - set(scene_spec.keys()))
    if missing_fields:
        if _strict(ctx):
            return _result_rejected(trace, "MISSING_SCENE_FIELD")
        return _result_degraded(trace, "SCENE_SPEC_INCOMPLETE", [f"SCENE.{field}" for field in missing_fields], FALLBACK_STRUCTURE, projected_structure_spec)

    rule_version = str(trace["rule_version"])
    enums = _get_enums(ctx, rule_version)
    invalid_fields: List[str] = []
    for key in ("scene_type", "time_of_day", "weather", "mood"):
        allowed = enums.get(key)
        if isinstance(allowed, set):
            allowed_values = allowed
        elif isinstance(allowed, list):
            allowed_values = set(allowed)
        else:
            allowed_values = set()

        if str(scene_spec.get(key)) not in allowed_values:
            invalid_fields.append(key)

    if invalid_fields:
        if _strict(ctx):
            return _result_rejected(trace, "INVALID_SCENE_ENUM")
        return _result_degraded(
            trace,
            "SCENE_ENUM_UNSUPPORTED",
            [f"SCENE.{field}" for field in invalid_fields],
            FALLBACK_STRUCTURE,
            projected_structure_spec,
        )

    rule_registry_has_version = bool(ctx.get("rule_registry_has_version", True))
    if not rule_registry_has_version:
        if _strict(ctx):
            return _result_rejected(trace, "RULESET_NOT_FOUND")
        return _result_degraded(trace, "RULESET_MISSING", ["MAPPING.*"], FALLBACK_STRUCTURE, projected_structure_spec)

    ruleset_integrity_ok = bool(ctx.get("ruleset_integrity_ok", True))
    if not ruleset_integrity_ok:
        if _strict(ctx):
            return _result_rejected(trace, "RULE_MISSING")
        return _result_degraded(trace, "RULE_ENTRY_MISSING", ["MAPPING.*"], FALLBACK_STRUCTURE, projected_structure_spec)

    top_candidates = _to_list(ctx.get("top_candidates"))
    if len(top_candidates) >= 2:
        first = top_candidates[0]
        second = top_candidates[1]
        first_score = first.get("score") if isinstance(first, dict) else None
        second_score = second.get("score") if isinstance(second, dict) else None
        if first_score is not None and first_score == second_score:
            if _strict(ctx):
                return _result_rejected(trace, "AMBIGUOUS_SCENE_INTENT")
            return _result_degraded(trace, "SCENE_AMBIGUOUS_TOP_TIE", ["SCENE.*"], FALLBACK_METADATA, projected_structure_spec)

    scene_semantics = _collect_scene_semantics(scene_spec)
    supported_effects = set(str(item) for item in _to_list(ctx.get("supported_effects")))

    unsupported_from_scene = sorted(item for item in scene_semantics if item not in supported_effects)
    supported_from_scene = sorted(item for item in scene_semantics if item in supported_effects)

    unsupported_semantics = sorted(set(str(item) for item in _to_list(ctx.get("unsupported_semantics"))) | set(unsupported_from_scene))

    if unsupported_semantics:
        decisions = trace.get("mapper_decisions")
        if isinstance(decisions, list):
            existing_semantics = {
                str(item.get("semantic"))
                for item in decisions
                if isinstance(item, dict) and item.get("decision") == "UNSUPPORTED_EFFECT"
            }
            for semantic_key in unsupported_semantics:
                if semantic_key in existing_semantics:
                    continue
                decisions.append(
                    {
                        "decision": "UNSUPPORTED_EFFECT",
                        "semantic": semantic_key,
                        "priority": 1,
                        "reason": "projection_not_supported",
                    }
                )
            decisions.sort(key=lambda item: (str(item.get("semantic", "")), str(item.get("decision", ""))))

    if unsupported_semantics:
        if _strict(ctx):
            return _result_rejected(trace, "EXEC_CAPABILITY_GAP", unsupported_semantics)

        if supported_from_scene:
            return _result_ok_with_losses(trace, projected_structure_spec, unsupported_semantics)

        return _result_degraded(trace, "NON_PROJECTABLE_SCENE_EFFECT", unsupported_semantics, FALLBACK_STRUCTURE, projected_structure_spec)

    requested_npc_primitive = ctx.get("requested_npc_primitive")
    supported_by_engine = ctx.get("supported_npc_primitives")
    if requested_npc_primitive is not None and isinstance(supported_by_engine, dict):
        engine_version = str(trace["engine_version"])
        engine_set = supported_by_engine.get(engine_version, [])
        if requested_npc_primitive not in set(engine_set):
            if _strict(ctx):
                return _result_rejected(trace, "NPC_BEHAVIOR_UNSUPPORTED")
            return _result_degraded(
                trace,
                "NPC_PRIMITIVE_UNSUPPORTED",
                ["NPC_BEHAVIOR.*"],
                FALLBACK_STRUCTURE,
                projected_structure_spec,
            )

    exists_conflict = bool(ctx.get("exists_conflict", False))
    conflict_priority_equal = bool(ctx.get("conflict_priority_equal", False))
    tiebreak_rule_found = bool(ctx.get("tiebreak_rule_found", True))
    if exists_conflict and conflict_priority_equal and not tiebreak_rule_found:
        if _strict(ctx):
            return _result_rejected(trace, "MERGE_CONFLICT_UNRESOLVED")
        return _result_degraded(trace, "CONFLICT_NO_TIEBREAKER", ["MAPPING.*"], FALLBACK_METADATA, projected_structure_spec)

    catalog_loaded = bool(ctx.get("catalog_loaded", True))
    expected_catalog_version = str(ctx.get("expected_catalog_version", trace["catalog_version"]))
    catalog_version = str(trace["catalog_version"])
    if (not catalog_loaded) or (catalog_version != expected_catalog_version):
        if _strict(ctx):
            return _result_rejected(trace, "CATALOG_UNAVAILABLE")
        return _result_degraded(
            trace,
            "CATALOG_VERSION_OR_LOAD_FAILED",
            ["RESOURCE_BINDING.*"],
            FALLBACK_METADATA,
            projected_structure_spec,
        )

    resource_id = ctx.get("resource_id")
    catalog_resource_ids = set(_to_list(ctx.get("catalog_resource_ids")))
    if resource_id is not None and resource_id not in catalog_resource_ids:
        dependent = bool(ctx.get("dependent_on_resource_binding", False))
        lost = ["RESOURCE_BINDING.*"]
        if dependent:
            lost.append("SCENE.*")
        if _strict(ctx):
            return _result_rejected(trace, "RESOURCE_ID_NOT_FOUND")
        return _result_degraded(trace, "RESOURCE_UNRESOLVED", lost, FALLBACK_STRUCTURE, projected_structure_spec)

    max_structure_blocks = int(ctx.get("max_structure_blocks", 2000))
    predicted_blocks = int(ctx.get("predicted_blocks", 0))
    blocked_block_id_detected = bool(ctx.get("blocked_block_id_detected", False))
    if predicted_blocks > max_structure_blocks or blocked_block_id_detected:
        if _strict(ctx):
            return _result_rejected(trace, "GUARDRAIL_VIOLATION")
        return _result_degraded(
            trace,
            "RESOURCE_GUARDRAIL_BLOCKED",
            ["RESOURCE_BINDING.*"],
            FALLBACK_STRUCTURE,
            projected_structure_spec,
        )

    structure_block_count = int(ctx.get("structure_block_count", 0))
    if structure_block_count > max_structure_blocks:
        return _result_rejected(trace, "STRUCTURE_TOO_LARGE")

    if predicted_blocks < structure_block_count:
        return _result_rejected(trace, "PREDICTION_UNDERFLOW")

    validator_result = ctx.get("validator_result") if isinstance(ctx.get("validator_result"), dict) else {}
    validator_code = validator_result.get("failure_code")
    if validator_code in VALIDATOR_FAILURE_CODES:
        return _result_rejected(trace, str(validator_code))

    if bool(ctx.get("executor_queue_full", False)):
        return _result_rejected(trace, "EXECUTOR_QUEUE_FULL")

    if bool(ctx.get("duplicate_build_id", False)):
        return _result_rejected(trace, "DUPLICATE_BUILD_ID")

    return _result_ok(trace, projected_structure_spec)
