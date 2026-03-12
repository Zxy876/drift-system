# backend/app/core/ai/intent_engine.py
from __future__ import annotations
import json
import os
import re
import time
from typing import Any, Dict, Optional, List
import requests

API_KEY = os.getenv("OPENAI_API_KEY") or os.getenv("DEEPSEEK_API_KEY", "")
BASE_URL = os.getenv("OPENAI_BASE_URL", "https://api.deepseek.com/v1")
MODEL = os.getenv("OPENAI_MODEL", "deepseek-chat")


def _read_float_env(*names: str, default: float, minimum: float) -> float:
    for name in names:
        raw_value = os.getenv(name)
        if raw_value is None:
            continue
        try:
            parsed = float(raw_value)
        except (TypeError, ValueError):
            continue
        if parsed >= minimum:
            return parsed
    return float(default)


def _read_int_env(*names: str, default: int, minimum: int) -> int:
    for name in names:
        raw_value = os.getenv(name)
        if raw_value is None:
            continue
        try:
            parsed = int(raw_value)
        except (TypeError, ValueError):
            continue
        if parsed >= minimum:
            return parsed
    return int(default)


INTENT_CONNECT_TIMEOUT = _read_float_env(
    "INTENT_AI_CONNECT_TIMEOUT",
    "AI_CONNECT_TIMEOUT",
    "DEEPSEEK_CONNECT_TIMEOUT",
    default=10.0,
    minimum=1.0,
)
INTENT_READ_TIMEOUT = _read_float_env(
    "INTENT_AI_READ_TIMEOUT",
    "AI_READ_TIMEOUT",
    "DEEPSEEK_READ_TIMEOUT",
    default=120.0,
    minimum=5.0,
)
INTENT_MAX_RETRIES = _read_int_env(
    "INTENT_AI_MAX_RETRIES",
    "AI_MAX_RETRIES",
    "DEEPSEEK_MAX_RETRIES",
    default=3,
    minimum=0,
)
INTENT_RETRY_BACKOFF = _read_float_env(
    "INTENT_AI_RETRY_BACKOFF",
    "AI_RETRY_BACKOFF",
    "DEEPSEEK_RETRY_BACKOFF",
    default=1.0,
    minimum=0.1,
)
INTENT_RETRYABLE_STATUS_CODES = {408, 409, 425, 429, 500, 502, 503, 504}

# ============================================================
# Prompt：新版（要求返回 intents[]）
# ============================================================
INTENT_PROMPT = """
你是“心悦宇宙多意图解析器”。
必须输出 JSON，结构固定为：

{
  "intents": [
      { "type": "...", ... },
      { "type": "...", ... }
  ]
}

支持的意图（type）：

- CREATE_STORY
- SHOW_MINIMAP
- SET_DAY / SET_NIGHT
- SET_WEATHER
- TELEPORT
- SPAWN_ENTITY
- BUILD_STRUCTURE
- GOTO_LEVEL
- GOTO_NEXT_LEVEL
- STORY_CONTINUE
- SAY_ONLY

规则：

1. 若一句话包含多个动作（如：跳到第三关并把天气改成白天），则必须输出多个 intents。
2. 出现以下词 → 必须加入 CREATE_STORY：
    “写剧情”“写故事”“编故事”“创造剧情”“生成剧情”“做一个关卡”“创建剧情”“创建关卡”“导入剧情”
3. 若是 CREATE_STORY 且用户文本中出现主题词（例如“创建剧情 大风吹”），请在该 intent 中返回 "scene_theme" 字段。
4. 若文本包含位置提示（例如“在森林里/在海边”），请同时返回 "scene_hint" 字段。
5. 涉及关卡数字必须解析成 level_01 / level_05 形式。
6. 若 AI 不确定，只输出一个 { "type": "SAY_ONLY" }。

严格只允许 JSON。
"""

CREATE_STORY_KEYWORDS = (
    "写剧情",
    "写故事",
    "编故事",
    "创造剧情",
    "生成剧情",
    "做一个关卡",
    "创建剧情",
    "创建关卡",
    "导入剧情",
)


def _clean_scene_theme(raw_theme: Any) -> Optional[str]:
    theme = str(raw_theme or "").strip()
    if not theme:
        return None

    theme = re.sub(r"^[\s:：,，\-—\"'“”‘’]+", "", theme)
    theme = re.sub(r'[\s。！!？?]+$', "", theme).strip()
    if not theme:
        return None

    return theme


def _clean_scene_hint(raw_hint: Any) -> Optional[str]:
    hint = str(raw_hint or "").strip()
    if not hint:
        return None

    hint = re.sub(r"^[\s:：,，\-—\"'“”‘’]+", "", hint)
    hint = re.sub(r"[\s。！!？?]+$", "", hint).strip()

    for suffix in ("里面", "里边", "附近", "周围", "一带", "这里", "那里", "场景", "里", "中"):
        if hint.endswith(suffix) and len(hint) > len(suffix):
            hint = hint[: -len(suffix)].strip()
            break

    if hint.startswith("在") and len(hint) > 1:
        hint = hint[1:].strip()

    if not hint:
        return None
    return hint


def _extract_scene_theme_and_hint(text: str) -> tuple[Optional[str], Optional[str]]:
    raw = str(text or "").strip()
    if not raw:
        return None, None

    scene_hint: Optional[str] = None
    trailing_hint_match = re.search(r"\s+在\s*(.+?)(?:里|中|附近|旁边|一带)?$", raw)
    if trailing_hint_match:
        scene_hint = _clean_scene_hint(trailing_hint_match.group(1))
        raw = raw[: trailing_hint_match.start()].strip()

    create_prefix_patterns = [
        r"^(?:请)?(?:帮我)?(?:创建|生成|导入|写|编|创造|做)(?:一个)?(?:剧情|故事|关卡)\s*[:：,，\-— ]*(.+)$",
        r"^(?:创建剧情|创建关卡|导入剧情)\s*[:：,，\-— ]*(.+)$",
    ]
    for pattern in create_prefix_patterns:
        match = re.match(pattern, raw)
        if not match:
            continue
        content = str(match.group(1) or "").strip()
        inline_hint = re.search(r"\s+在\s*(.+)$", content)
        if inline_hint:
            scene_hint = scene_hint or _clean_scene_hint(inline_hint.group(1))
            content = content[: inline_hint.start()].strip()
        return _clean_scene_theme(content), scene_hint

    scene_match = re.match(r"^我要(?:一个)?(.+?)的场景(?:\s*在\s*(.+))?$", raw)
    if scene_match:
        theme = _clean_scene_theme(scene_match.group(1))
        if scene_match.group(2):
            scene_hint = scene_hint or _clean_scene_hint(scene_match.group(2))
        return theme, scene_hint

    for keyword in ("创建剧情", "创建关卡", "导入剧情"):
        if keyword in raw:
            content = raw.split(keyword, 1)[1].strip()
            inline_hint = re.search(r"\s+在\s*(.+)$", content)
            if inline_hint:
                scene_hint = scene_hint or _clean_scene_hint(inline_hint.group(1))
                content = content[: inline_hint.start()].strip()
            return _clean_scene_theme(content), scene_hint

    return None, scene_hint


def extract_scene_theme(text: str) -> Optional[str]:
    scene_theme, _ = _extract_scene_theme_and_hint(text)
    return scene_theme


def extract_scene_hint(text: str) -> Optional[str]:
    _, scene_hint = _extract_scene_theme_and_hint(text)
    return scene_hint


def is_create_story_request(text: str) -> bool:
    raw = str(text or "").strip()
    if not raw:
        return False
    if any(keyword in raw for keyword in CREATE_STORY_KEYWORDS):
        return True
    return bool(re.search(r"我要(?:一个)?.+场景", raw))

# ============================================================
# level 解析
# ============================================================
def normalize_level(text: str) -> Optional[str]:
    raw = text.lower()
    m = re.search(r"\d+", raw)
    if m:
        return f"level_{int(m.group()):02d}"

    cn = {"一":1,"二":2,"三":3,"四":4,"五":5,"六":6,"七":7,"八":8,"九":9,"十":10}
    for k,v in cn.items():
        if k+"关" in text:
            return f"level_{v:02d}"
    return None

# ============================================================
# AI 多意图解析
# ============================================================
def ai_parse_multi(text: str) -> Optional[List[Dict[str, Any]]]:
    if not API_KEY:
        return None

    payload = {
        "model": MODEL,
        "messages": [
            {"role": "system", "content": INTENT_PROMPT},
            {"role": "user", "content": text},
        ],
        "temperature": 0.2,
        "response_format": {"type": "json_object"},
    }

    total_attempts = INTENT_MAX_RETRIES + 1
    last_error: Exception | None = None

    for attempt in range(total_attempts):
        attempt_no = attempt + 1
        try:
            response = requests.post(
                f"{BASE_URL}/chat/completions",
                headers={"Authorization": f"Bearer {API_KEY}",
                         "Content-Type": "application/json"},
                json=payload,
                timeout=(INTENT_CONNECT_TIMEOUT, INTENT_READ_TIMEOUT),
            )
            response.raise_for_status()
            resp = response.json()
            data = json.loads(resp["choices"][0]["message"]["content"])
            intents = data.get("intents", [])
            if isinstance(intents, list):
                return intents
            return []
        except requests.Timeout as exc:
            last_error = exc
            print(f"[intent_engine] AI multi-intent timeout attempt {attempt_no}/{total_attempts}: {exc}")
        except requests.RequestException as exc:
            last_error = exc
            status = getattr(exc.response, "status_code", None)
            print(
                f"[intent_engine] AI multi-intent HTTP error attempt {attempt_no}/{total_attempts}"
                f" (status={status}): {exc}"
            )
            if status is not None and int(status) not in INTENT_RETRYABLE_STATUS_CODES:
                break
        except (KeyError, ValueError, json.JSONDecodeError) as exc:
            last_error = exc
            print(f"[intent_engine] AI multi-intent parse error attempt {attempt_no}/{total_attempts}: {exc}")

        if attempt < INTENT_MAX_RETRIES:
            sleep_seconds = INTENT_RETRY_BACKOFF * (attempt + 1)
            time.sleep(sleep_seconds)

    if last_error is not None:
        print("[intent_engine] AI multi-intent failed:", last_error)
    return None

# ============================================================
# fallback：返回 list
# ============================================================
def fallback_intents(text: str) -> List[Dict[str, Any]]:
    raw = text.strip()
    intents = []

    # CREATE_STORY
    if is_create_story_request(raw):
        create_story_intent = {
            "type": "CREATE_STORY",
            "title": raw[:12],
            "text": raw,
            "raw_text": raw,
        }
        scene_theme, scene_hint = _extract_scene_theme_and_hint(raw)
        if scene_theme:
            create_story_intent["scene_theme"] = scene_theme
        if scene_hint:
            create_story_intent["scene_hint"] = scene_hint
        intents.append(create_story_intent)
        return intents

    # minimap - 扩展自然语言触发词
    if any(w in raw for w in ["地图", "minimap", "看地图", "小地图", "导航", "周围", "位置", "在哪", "地图在哪", "显示地图", "查看地图", "看看周围"]):
        intents.append({"type": "SHOW_MINIMAP", "raw_text": raw})

    # time/weather
    if "白天" in raw:
        intents.append({"type": "SET_DAY"})
    if "晚上" in raw or "夜" in raw:
        intents.append({"type": "SET_NIGHT"})
    if "雨" in raw:
        intents.append({"type": "SET_WEATHER", "weather": "rain"})

    # level
    lvl = normalize_level(raw)
    if lvl:
        intents.append({"type": "GOTO_LEVEL", "level_id": lvl})

    if not intents:
        intents.append({"type": "SAY_ONLY", "raw_text": raw})

    return intents


# ============================================================
# parse_intent → 输出 { status, intents: [] }
# ============================================================
def parse_intent(player_id, text, world_state, story_engine):

    ai_list = ai_parse_multi(text)
    intents = ai_list if ai_list else fallback_intents(text)

    # 修正 level 格式
    for it in intents:
        if it.get("type") == "GOTO_LEVEL":
            lvl1 = it.get("level_id")
            lvl2 = it.get("level")
            if lvl1:
                it["level_id"] = lvl1
            elif lvl2:
                it["level_id"] = normalize_level(lvl2)
            it.pop("level", None)

    for it in intents:
        raw_text = str(it.get("raw_text") or "").strip()
        if not raw_text and text:
            it["raw_text"] = text

    # 附加 minimap （给所有 intents）
    for it in intents:
        it["minimap"] = story_engine.minimap.to_dict(player_id)

    # 自动补世界 patch
    for it in intents:
        t = it["type"]
        if t == "SET_DAY":
            it["world_patch"] = {"mc": {"time": "day"}}
        elif t == "SET_NIGHT":
            it["world_patch"] = {"mc": {"time": "night"}}
        elif t == "SET_WEATHER":
            w = it.get("weather", "clear")
            it["world_patch"] = {"mc": {"weather": w}}

        elif t == "TELEPORT":
            it["world_patch"] = {"mc": {
                "teleport": {"mode": "relative", "x": 0, "y": 0, "z": 3}
            }}

    # CREATE_STORY 自动补全
    for it in intents:
        if it["type"] == "CREATE_STORY":
            raw_text = str(it.get("raw_text") or text or "").strip()
            if raw_text:
                it["raw_text"] = raw_text

            scene_theme = it.get("scene_theme") or it.get("theme")
            scene_hint = it.get("scene_hint") or it.get("hint")

            parsed_theme, parsed_hint = _extract_scene_theme_and_hint(raw_text or str(it.get("text") or text or ""))

            if not scene_theme:
                scene_theme = parsed_theme
            if not scene_hint:
                scene_hint = parsed_hint

            normalized_scene_theme = _clean_scene_theme(scene_theme)
            if normalized_scene_theme:
                it["scene_theme"] = normalized_scene_theme
            normalized_scene_hint = _clean_scene_hint(scene_hint)
            if normalized_scene_hint:
                it["scene_hint"] = normalized_scene_hint
            it.pop("theme", None)
            it.pop("hint", None)

            it.setdefault("title", (raw_text or text)[:12] or "新剧情")
            it.setdefault("text", raw_text or text)
            it.setdefault("world_patch", {
                "mc": {
                    "spawn": {
                        "type": "villager",
                        "name": "桃子",
                        "offset": {"dx": 2, "dy": 0, "dz": 2}
                    },
                    "tell": "✨ 新剧情已准备好，正在加载……"
                }
            })

    return {
        "status": "ok",
        "intents": intents
    }