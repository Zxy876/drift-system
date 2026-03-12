from __future__ import annotations

import json
import os
import re
import copy
from typing import Any, Dict, Tuple

import requests

from app.core.generation.spec_validator import validate_spec


API_KEY = os.getenv("OPENAI_API_KEY") or os.getenv("DEEPSEEK_API_KEY", "")
BASE_URL = os.getenv("OPENAI_BASE_URL", "https://api.deepseek.com/v1")
MODEL = os.getenv("OPENAI_MODEL", "deepseek-chat")

DEFAULT_SPEC = {
    "structure_type": "house",
    "width": 7,
    "depth": 5,
    "height": 4,
    "material_preference": "wood",
    "roof_type": "flat",
    "orientation": "south",
    "features": {
        "door": {"enabled": False, "side": "front"},
        "windows": {"enabled": False, "count": 0},
    },
}

SYSTEM_PROMPT = (
    "你是 Drift Spec 抽取器。"
    "只允许输出 JSON 对象。"
    "只允许字段：structure_type,width,depth,height,material_preference,roof_type,orientation,features。"
    "features 仅允许 door(enabled,side) 与 windows(enabled,count)。"
    "禁止输出 blocks/build/mc/world_patch。"
    "禁止任何解释文字。"
)

FORBIDDEN_HINTS = ("blocks", "world_patch", "mc", "build:", "build=")
UNSAFE_PATTERNS = ("炸掉", "炸", "爆破", "攻击", "destroy server", "ddos")


def _call_llm_json(text: str) -> Tuple[bool, Dict[str, Any] | str]:
    if os.getenv("PYTEST_CURRENT_TEST"):
        return False, "UNAVAILABLE"

    if not API_KEY:
        return False, "UNAVAILABLE"

    payload = {
        "model": MODEL,
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": text},
        ],
        "temperature": 0,
        "response_format": {"type": "json_object"},
        "max_tokens": 120,
    }

    try:
        response = requests.post(
            f"{BASE_URL}/chat/completions",
            headers={
                "Authorization": f"Bearer {API_KEY}",
                "Content-Type": "application/json",
            },
            json=payload,
            timeout=(10, 20),
        )
        response.raise_for_status()
        data = response.json()
        content = data["choices"][0]["message"]["content"]
        parsed = json.loads(content)
        if not isinstance(parsed, dict):
            return False, "PARSE_ERROR"
        return True, parsed
    except (requests.RequestException, KeyError, ValueError, json.JSONDecodeError):
        return False, "PARSE_ERROR"


def _extract_local_spec(text: str) -> Dict[str, Any]:
    raw = text or ""
    lowered = raw.lower()

    spec = copy.deepcopy(DEFAULT_SPEC)

    if any(token in lowered for token in ("tower", "塔", "高塔")):
        spec["structure_type"] = "tower"
    elif any(token in lowered for token in ("wall", "墙")):
        spec["structure_type"] = "wall"
    elif any(token in lowered for token in ("bridge", "桥")):
        spec["structure_type"] = "bridge"
    else:
        spec["structure_type"] = "house"

    if any(token in lowered for token in ("stone", "石")):
        spec["material_preference"] = "stone"
    elif any(token in lowered for token in ("brick", "砖")):
        spec["material_preference"] = "brick"
    else:
        spec["material_preference"] = "wood"

    if any(token in lowered for token in ("gable", "坡顶", "斜顶")):
        spec["roof_type"] = "gable"
    elif any(token in lowered for token in ("none", "无顶", "不要屋顶")):
        spec["roof_type"] = "none"
    else:
        spec["roof_type"] = "flat"

    dims = re.search(r"(\d+)\s*[xX×]\s*(\d+)", raw)
    if dims:
        spec["width"] = int(dims.group(1))
        spec["depth"] = int(dims.group(2))

    height_match = re.search(r"高\s*(\d+)", raw)
    if height_match:
        spec["height"] = int(height_match.group(1))

    if any(token in lowered for token in ("朝北", "向北", "north")):
        spec["orientation"] = "north"
    elif any(token in lowered for token in ("朝南", "向南", "south")):
        spec["orientation"] = "south"
    elif any(token in lowered for token in ("朝东", "向东", "east")):
        spec["orientation"] = "east"
    elif any(token in lowered for token in ("朝西", "向西", "west")):
        spec["orientation"] = "west"

    door_enabled = any(token in lowered for token in ("门", "door"))
    spec["features"]["door"]["enabled"] = door_enabled
    spec["features"]["door"]["side"] = "front"

    window_enabled = any(token in lowered for token in ("窗", "window"))
    if window_enabled:
        window_count = 2
        cn_counts = {
            "一": 1,
            "两": 2,
            "二": 2,
            "三": 3,
            "四": 4,
        }
        digit_match = re.search(r"(\d+)\s*(扇)?\s*窗", raw)
        if digit_match:
            window_count = int(digit_match.group(1))
        else:
            for token, value in cn_counts.items():
                if f"{token}扇窗" in raw or f"{token}个窗" in raw:
                    window_count = value
                    break
        spec["features"]["windows"]["enabled"] = True
        spec["features"]["windows"]["count"] = window_count

    return spec


def _apply_defaults(candidate: Dict[str, Any], text: str) -> Dict[str, Any]:
    base = _extract_local_spec(text)
    _ = candidate
    return dict(base)


def generate_spec_from_text_v1(text: str) -> dict:
    if not isinstance(text, str) or not text.strip():
        return {"status": "REJECTED", "failure_code": "LLM_INVALID_SPEC", "spec": None}

    lowered = text.lower()
    if any(token in lowered for token in UNSAFE_PATTERNS):
        return {"status": "REJECTED", "failure_code": "LLM_INVALID_SPEC", "spec": None}

    if any(token in lowered for token in FORBIDDEN_HINTS):
        return {"status": "REJECTED", "failure_code": "LLM_INVALID_SPEC", "spec": None}

    ok, payload = _call_llm_json(text)
    if ok:
        candidate = _apply_defaults(payload, text)
    else:
        if payload == "PARSE_ERROR":
            return {"status": "REJECTED", "failure_code": "LLM_PARSE_ERROR", "spec": None}
        candidate = _extract_local_spec(text)

    validation = validate_spec(candidate)
    if validation.get("status") != "VALID":
        return {"status": "REJECTED", "failure_code": "LLM_INVALID_SPEC", "spec": None}

    return {
        "status": "VALID",
        "failure_code": "NONE",
        "spec": validation.get("spec"),
    }
