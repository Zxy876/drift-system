from __future__ import annotations

from copy import deepcopy
from typing import Any, Dict


DEFAULT_RULE_VERSION = "rule_v2_2"

PROJECTION_RULE_REGISTRY: Dict[str, Dict[str, Dict[str, Any]]] = {
    "rule_v2_2": {
        "atmosphere.fog": {
            "rule_id": "PROJECTION_ATMOSPHERE_FOG_V1",
            "priority": 300,
            "stage": "mapper",
            "block": "glass_pane",
            "y_offset": 1,
            "fill_mode": "full",
            "conflict_policy": "skip_on_structure",
            "supported_engines": ["engine_v2_1"],
        },
        "npc_behavior.lake_guard": {
            "rule_id": "PROJECTION_NPC_LAKE_GUARD_V1",
            "priority": 350,
            "stage": "mapper",
            "block": "npc_placeholder",
            "x_offset": 2,
            "y_offset": 0,
            "z_offset": 0,
            "entity_type": "villager",
            "name": "Lake Guard",
            "profession": "none",
            "ai_disabled": True,
            "silent": True,
            "rotation": 90,
            "conflict_policy": "skip_on_structure",
            "supported_engines": ["engine_v2_1"],
        },
    }
}


def get_projection_rule(rule_version: str, effect_key: str) -> dict | None:
    rules = PROJECTION_RULE_REGISTRY.get(str(rule_version), {})
    rule = rules.get(str(effect_key))
    if not isinstance(rule, dict):
        return None
    return deepcopy(rule)


def projection_supported(rule_version: str, engine_version: str, effect_key: str) -> bool:
    rule = get_projection_rule(rule_version, effect_key)
    if not isinstance(rule, dict):
        return False
    engines = rule.get("supported_engines")
    if not isinstance(engines, list) or not engines:
        return False
    return str(engine_version) in set(str(item) for item in engines)


def list_supported_projection_effects(rule_version: str, engine_version: str) -> list[str]:
    rules = PROJECTION_RULE_REGISTRY.get(str(rule_version), {})
    effects = []
    for effect_key in sorted(rules.keys()):
        if projection_supported(rule_version, engine_version, effect_key):
            effects.append(effect_key)
    return effects
