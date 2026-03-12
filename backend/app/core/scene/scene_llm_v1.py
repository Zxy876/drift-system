from __future__ import annotations

import hashlib
import json
import os
from typing import Any, Dict, Tuple

import requests

from app.core.scene.scene_spec_validator import validate_scene_spec


API_KEY = os.getenv("OPENAI_API_KEY") or os.getenv("DEEPSEEK_API_KEY", "")
BASE_URL = os.getenv("OPENAI_BASE_URL", "https://api.deepseek.com/v1")
MODEL = os.getenv("OPENAI_MODEL", "deepseek-chat")

DEFAULT_SCENE_SPEC = {
    "scene_type": "plain",
    "time_of_day": "day",
    "weather": "clear",
    "mood": "calm",
    "semantic_effects": [],
    "semantic_version": "scene_semantic_v1",
}

SYSTEM_PROMPT = (
    "你是 Scene Spec 抽取器。"
    "只允许输出 JSON 对象。"
    "只允许字段：scene_type,time_of_day,weather,mood,semantic_effects,semantic_version。"
    "semantic_version 必须等于 scene_semantic_v1。"
    "semantic_effects 每项必须包含 type,value,confidence,effect_source。"
    "effect_source 必须等于 nl_extraction。"
    "semantic_effects.value 只允许固定枚举：atmosphere=['fog'], sound=['low_music'], npc_behavior=['lake_guard']。"
    "凡出现雾/烟/朦胧等环境效果，必须输出 atmosphere.fog。"
    "凡出现低沉音乐/环境音/回声等听觉效果，必须输出 sound.low_music。"
    "凡出现湖边守卫/守卫/guard 等 NPC 语义，必须输出 npc_behavior.lake_guard。"
    "confidence<0.7 的效果不得输出。"
    "semantic_effects 按 type+value 排序。"
    "已进入 semantic_effects 的效果不得在 mood 中重复描述具体物理/听觉词汇。"
    "若无可提取效果，semantic_effects 必须输出空数组。"
    "禁止输出 blocks。"
    "禁止解释文字。"
)

SEMANTIC_VERSION = "scene_semantic_v1"

EFFECT_VALUE_ENUMS = {
    "atmosphere": {"fog"},
    "sound": {"low_music"},
    "npc_behavior": {"lake_guard"},
}

ATMOSPHERE_KEYWORDS = (
    "雾",
    "雾气",
    "薄雾",
    "迷雾",
    "烟",
    "朦胧",
    "fog",
    "mist",
)

SOUND_KEYWORDS = (
    "低沉音乐",
    "音乐",
    "环境音",
    "回声",
    "sound",
    "music",
    "ambient",
)

NPC_GUARD_KEYWORDS = (
    "守卫",
    "卫兵",
    "岗哨",
    "guard",
    "lake guard",
)

SCENE_TYPE_ALIASES = {
    "lake": "lake",
    "湖": "lake",
    "湖边": "lake",
    "湖泊": "lake",
    "water": "lake",
    "village": "village",
    "村": "village",
    "村庄": "village",
    "forest": "forest",
    "森林": "forest",
    "林地": "forest",
    "plain": "plain",
    "平原": "plain",
    "草地": "plain",
}

TIME_ALIASES = {
    "day": "day",
    "白天": "day",
    "日间": "day",
    "night": "night",
    "夜": "night",
    "夜晚": "night",
}

WEATHER_ALIASES = {
    "clear": "clear",
    "晴": "clear",
    "晴天": "clear",
    "晴朗": "clear",
    "rain": "rain",
    "rainy": "rain",
    "雨": "rain",
    "下雨": "rain",
    "雨天": "rain",
}

MOOD_ALIASES = {
    "calm": "calm",
    "平静": "calm",
    "宁静": "calm",
    "tense": "tense",
    "紧张": "tense",
    "压迫": "tense",
    "mysterious": "mysterious",
    "mystic": "mysterious",
    "神秘": "mysterious",
}


def _normalize_choice(value: Any, aliases: Dict[str, str]) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str):
        return None
    normalized = value.strip().lower()
    if not normalized:
        return None
    if normalized in aliases:
        return aliases[normalized]
    for key, canonical in aliases.items():
        if key and key in normalized:
            return canonical
    return None


def _llm_extract(text: str) -> Tuple[bool, Dict[str, Any] | None]:
    if os.getenv("PYTEST_CURRENT_TEST"):
        return False, None
    if not API_KEY:
        return False, None

    payload = {
        "model": MODEL,
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": text},
        ],
        "temperature": 0,
        "response_format": {"type": "json_object"},
        "max_tokens": 80,
    }

    try:
        response = requests.post(
            f"{BASE_URL}/chat/completions",
            headers={
                "Authorization": f"Bearer {API_KEY}",
                "Content-Type": "application/json",
            },
            json=payload,
            timeout=(8, 15),
        )
        response.raise_for_status()
        data = response.json()
        content = data["choices"][0]["message"]["content"]
        parsed = json.loads(content)
        if isinstance(parsed, dict):
            return True, parsed
        return False, None
    except (requests.RequestException, KeyError, ValueError, json.JSONDecodeError):
        return False, None


def _rule_extract(text: str) -> Dict[str, Any]:
    raw = text or ""
    lowered = raw.lower()

    spec = dict(DEFAULT_SCENE_SPEC)

    if any(k in lowered for k in ("湖", "湖边", "lake")):
        spec["scene_type"] = "lake"
    elif any(k in lowered for k in ("村", "村庄", "village")):
        spec["scene_type"] = "village"
    elif any(k in lowered for k in ("森林", "林", "forest")):
        spec["scene_type"] = "forest"
    else:
        spec["scene_type"] = "plain"

    if any(k in lowered for k in ("夜", "night")):
        spec["time_of_day"] = "night"
    else:
        spec["time_of_day"] = "day"

    if any(k in lowered for k in ("雨", "rain")):
        spec["weather"] = "rain"
    else:
        spec["weather"] = "clear"

    if any(k in lowered for k in ("紧张", "tense")):
        spec["mood"] = "tense"
    elif any(k in lowered for k in ("神秘", "mysterious")):
        spec["mood"] = "mysterious"
    else:
        spec["mood"] = "calm"

    semantic_effects = []
    if any(k in lowered for k in ATMOSPHERE_KEYWORDS):
        semantic_effects.append(
            {
                "type": "atmosphere",
                "value": "fog",
                "confidence": 0.9,
                "effect_source": "nl_extraction",
            }
        )
    if any(k in lowered for k in SOUND_KEYWORDS):
        semantic_effects.append(
            {
                "type": "sound",
                "value": "low_music",
                "confidence": 0.8,
                "effect_source": "nl_extraction",
            }
        )
    if any(k in lowered for k in NPC_GUARD_KEYWORDS):
        semantic_effects.append(
            {
                "type": "npc_behavior",
                "value": "lake_guard",
                "confidence": 0.9,
                "effect_source": "nl_extraction",
            }
        )

    semantic_effects.sort(key=lambda item: (item["type"], item["value"]))
    spec["semantic_effects"] = semantic_effects
    spec["semantic_version"] = SEMANTIC_VERSION

    return spec


def _normalize_semantic_effects(payload: Any) -> list[dict]:
    if not isinstance(payload, list):
        return []

    normalized = {}
    for entry in payload:
        if not isinstance(entry, dict):
            continue
        effect_type = entry.get("type")
        value = entry.get("value")
        confidence = entry.get("confidence", 0.0)

        if not isinstance(effect_type, str) or not isinstance(value, str):
            continue

        effect_type_norm = effect_type.strip().lower()
        value_norm = value.strip().lower()
        allowed_values = EFFECT_VALUE_ENUMS.get(effect_type_norm)
        if not allowed_values or value_norm not in allowed_values:
            continue

        try:
            confidence_value = float(confidence)
        except (TypeError, ValueError):
            continue

        if confidence_value < 0.7 or confidence_value > 1.0:
            continue

        key = (effect_type_norm, value_norm)
        previous = normalized.get(key)
        if previous is None or confidence_value > previous["confidence"]:
            normalized[key] = {
                "type": effect_type_norm,
                "value": value_norm,
                "confidence": round(confidence_value, 3),
                "effect_source": "nl_extraction",
            }

    merged = list(normalized.values())
    merged.sort(key=lambda item: (item["type"], item["value"]))
    return merged


def generate_scene_spec_from_text_v1(text: str) -> dict:
    if not isinstance(text, str) or not text.strip():
        validation = validate_scene_spec(DEFAULT_SCENE_SPEC)
        return validation

    ok, payload = _llm_extract(text)
    extracted = _rule_extract(text)

    if ok and isinstance(payload, dict):
        merged = dict(extracted)
        for key in ("scene_type", "time_of_day", "weather", "mood"):
            if key not in payload or payload[key] is None:
                continue

            if key == "scene_type":
                candidate = _normalize_choice(payload[key], SCENE_TYPE_ALIASES)
            elif key == "time_of_day":
                candidate = _normalize_choice(payload[key], TIME_ALIASES)
            elif key == "weather":
                candidate = _normalize_choice(payload[key], WEATHER_ALIASES)
            elif key == "mood":
                candidate = _normalize_choice(payload[key], MOOD_ALIASES)
            else:
                candidate = None

            if candidate is not None:
                merged[key] = candidate

        llm_effects = _normalize_semantic_effects(payload.get("semantic_effects"))
        if llm_effects:
            indexed = {(item["type"], item["value"]): item for item in merged.get("semantic_effects") or []}
            for item in llm_effects:
                key = (item["type"], item["value"])
                existing = indexed.get(key)
                if existing is None or item["confidence"] > existing.get("confidence", 0.0):
                    indexed[key] = item

            merged["semantic_effects"] = sorted(indexed.values(), key=lambda item: (item["type"], item["value"]))
        else:
            merged["semantic_effects"] = sorted(
                merged.get("semantic_effects") or [],
                key=lambda item: (item["type"], item["value"]),
            )

        merged["semantic_version"] = SEMANTIC_VERSION
        extracted = merged

    if "semantic_effects" not in extracted:
        extracted["semantic_effects"] = []
    if "semantic_version" not in extracted:
        extracted["semantic_version"] = SEMANTIC_VERSION

    return validate_scene_spec(extracted)


def scene_spec_hash(scene_spec: dict) -> str:
    payload = json.dumps(scene_spec, ensure_ascii=False, sort_keys=True)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()
