from __future__ import annotations

from typing import Any, Dict


REQUIRED_FIELDS = ("scene_type", "time_of_day", "weather", "mood")
ALLOWED_FIELDS = set(REQUIRED_FIELDS) | {"semantic_effects", "semantic_version"}
FORBIDDEN_FIELDS = {"blocks"}

SCENE_TYPES = {"lake", "village", "forest", "plain"}
TIMES = {"day", "night"}
WEATHERS = {"clear", "rain"}
MOODS = {"calm", "tense", "mysterious"}
SEMANTIC_VERSION = "scene_semantic_v1"
EFFECT_VALUE_ENUMS = {
    "atmosphere": {"fog"},
    "sound": {"low_music"},
    "lighting": set(),
    "npc_behavior": {"lake_guard"},
}


def _reject(failure_code: str) -> Dict[str, Any]:
    return {
        "status": "REJECTED",
        "failure_code": failure_code,
        "scene_spec": None,
    }


def _norm_str(value: Any) -> str:
    if not isinstance(value, str):
        return ""
    return value.strip().lower()


def validate_scene_spec(scene_spec: dict) -> dict:
    if not isinstance(scene_spec, dict):
        return _reject("MISSING_FIELD")

    if any(field in scene_spec for field in FORBIDDEN_FIELDS):
        return _reject("MISSING_FIELD")

    for field in REQUIRED_FIELDS:
        if field not in scene_spec:
            return _reject("MISSING_FIELD")

    unknown = [k for k in scene_spec.keys() if k not in ALLOWED_FIELDS]
    if unknown:
        return _reject("MISSING_FIELD")

    scene_type = _norm_str(scene_spec.get("scene_type"))
    if scene_type not in SCENE_TYPES:
        return _reject("INVALID_SCENE_TYPE")

    time_of_day = _norm_str(scene_spec.get("time_of_day"))
    if time_of_day not in TIMES:
        return _reject("INVALID_TIME")

    weather = _norm_str(scene_spec.get("weather"))
    if weather not in WEATHERS:
        return _reject("INVALID_WEATHER")

    mood = _norm_str(scene_spec.get("mood"))
    if mood not in MOODS:
        return _reject("INVALID_MOOD")

    semantic_version = scene_spec.get("semantic_version", SEMANTIC_VERSION)
    if not isinstance(semantic_version, str) or semantic_version.strip() != SEMANTIC_VERSION:
        return _reject("MISSING_FIELD")

    semantic_effects = scene_spec.get("semantic_effects", [])
    if not isinstance(semantic_effects, list):
        return _reject("MISSING_FIELD")

    normalized_effects = []
    for entry in semantic_effects:
        if not isinstance(entry, dict):
            return _reject("MISSING_FIELD")

        effect_type = _norm_str(entry.get("type"))
        value = _norm_str(entry.get("value"))
        effect_source = _norm_str(entry.get("effect_source"))
        confidence_raw = entry.get("confidence")

        if effect_type not in EFFECT_VALUE_ENUMS:
            return _reject("MISSING_FIELD")
        allowed_values = EFFECT_VALUE_ENUMS[effect_type]
        if value not in allowed_values:
            return _reject("MISSING_FIELD")
        if effect_source != "nl_extraction":
            return _reject("MISSING_FIELD")

        try:
            confidence = float(confidence_raw)
        except (TypeError, ValueError):
            return _reject("MISSING_FIELD")

        if confidence < 0.7 or confidence > 1.0:
            return _reject("MISSING_FIELD")

        normalized_effects.append(
            {
                "type": effect_type,
                "value": value,
                "confidence": round(confidence, 3),
                "effect_source": "nl_extraction",
            }
        )

    dedup = {}
    for item in normalized_effects:
        key = (item["type"], item["value"])
        prev = dedup.get(key)
        if prev is None or item["confidence"] > prev["confidence"]:
            dedup[key] = item
    normalized_effects = sorted(dedup.values(), key=lambda item: (item["type"], item["value"]))

    normalized = {
        "scene_type": scene_type,
        "time_of_day": time_of_day,
        "weather": weather,
        "mood": mood,
        "semantic_effects": normalized_effects,
        "semantic_version": SEMANTIC_VERSION,
    }

    return {
        "status": "VALID",
        "failure_code": "NONE",
        "scene_spec": normalized,
    }
