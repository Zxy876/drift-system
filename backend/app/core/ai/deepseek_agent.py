# backend/app/core/ai/deepseek_agent.py
from __future__ import annotations

import os
import json
import time
import hashlib
import threading
import random
from typing import Any, Dict, List, Optional

import requests
from dotenv import load_dotenv

load_dotenv()

API_KEY = os.getenv("OPENAI_API_KEY") or os.getenv("DEEPSEEK_API_KEY", "")
BASE_URL = os.getenv("OPENAI_BASE_URL", "https://api.deepseek.com/v1")
MODEL = os.getenv("OPENAI_MODEL", "deepseek-chat")

HEADERS = {
    "Authorization": f"Bearer {API_KEY}" if API_KEY else "",
    "Content-Type": "application/json",
}


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


CONNECT_TIMEOUT = _read_float_env(
    "AI_CONNECT_TIMEOUT",
    "DEEPSEEK_CONNECT_TIMEOUT",
    default=10.0,
    minimum=1.0,
)
READ_TIMEOUT = _read_float_env(
    "AI_READ_TIMEOUT",
    "DEEPSEEK_READ_TIMEOUT",
    default=120.0,
    minimum=5.0,
)
MAX_RETRIES = _read_int_env(
    "AI_MAX_RETRIES",
    "DEEPSEEK_MAX_RETRIES",
    default=3,
    minimum=0,
)
RETRY_BACKOFF = _read_float_env(
    "AI_RETRY_BACKOFF",
    "DEEPSEEK_RETRY_BACKOFF",
    default=1.5,
    minimum=0.1,
)
MAX_RETRY_BACKOFF = _read_float_env(
    "AI_MAX_RETRY_BACKOFF",
    "DEEPSEEK_MAX_RETRY_BACKOFF",
    default=10.0,
    minimum=0.1,
)

_lock = threading.Lock()
_LAST_CALL_TS: Dict[str, float] = {}
_CACHE: Dict[str, Dict[str, Any]] = {}

# ⭐ 最重要：缩短冷却时间
MIN_INTERVAL = 0.6

MAX_CACHE_SIZE = 128
RETRYABLE_STATUS_CODES = {408, 409, 425, 429, 500, 502, 503, 504}

SYSTEM_PROMPT = """
你的身份是《昆明湖宇宙》的“造物主（Story + World God）”。
只能输出 JSON，不允许任何解释文字。

生成：
- node {title,text}
- world_patch {mc:{...}, variables:{...}}
- 避免把玩家传送进方块内部，避免窒息/掉虚空
- 若出现 NPC/人物/动物 → 必须 spawn
"""

def _make_cache_key(context, messages_tail):
    key_payload = {"context": context, "messages_tail": messages_tail[-8:]}
    s = json.dumps(key_payload, ensure_ascii=False, sort_keys=True, default=str)
    return hashlib.sha256(s.encode()).hexdigest()

def _cache_get(key): return _CACHE.get(key)
def _cache_put(key, val):
    if len(_CACHE) >= MAX_CACHE_SIZE:
        _CACHE.pop(next(iter(_CACHE)))
    _CACHE[key] = val


def _should_retry_http_error(status_code: int | None) -> bool:
    if status_code is None:
        return True
    return int(status_code) in RETRYABLE_STATUS_CODES


def _retry_sleep_seconds(attempt_index: int) -> float:
    base = RETRY_BACKOFF * (2 ** attempt_index)
    capped = min(base, MAX_RETRY_BACKOFF)
    jitter = random.uniform(0.0, max(0.05, capped * 0.2))
    return capped + jitter


def _call_deepseek_api(payload: Dict[str, Any]) -> Dict[str, Any]:
    last_error: Exception | None = None
    total_attempts = MAX_RETRIES + 1
    for attempt in range(total_attempts):
        attempt_no = attempt + 1
        started_at = time.monotonic()
        try:
            resp = requests.post(
                f"{BASE_URL}/chat/completions",
                headers=HEADERS,
                json=payload,
                timeout=(CONNECT_TIMEOUT, READ_TIMEOUT),
            )
            resp.raise_for_status()
            body = resp.json()
            content = body["choices"][0]["message"]["content"]
            parsed = json.loads(content)
            elapsed_ms = int((time.monotonic() - started_at) * 1000)
            print(
                f"[AI INFO] DeepSeek success attempt {attempt_no}/{total_attempts}"
                f" in {elapsed_ms}ms"
            )
            return parsed
        except requests.Timeout as exc:
            last_error = exc
            elapsed_ms = int((time.monotonic() - started_at) * 1000)
            print(
                f"[AI WARN] DeepSeek timeout attempt {attempt_no}/{total_attempts}"
                f" after {elapsed_ms}ms: {exc}"
            )
        except requests.RequestException as exc:
            last_error = exc
            status = getattr(exc.response, "status_code", None)
            elapsed_ms = int((time.monotonic() - started_at) * 1000)
            print(
                f"[AI WARN] DeepSeek HTTP error attempt {attempt_no}/{total_attempts}"
                f" after {elapsed_ms}ms (status={status}): {exc}"
            )
            if not _should_retry_http_error(status):
                print(f"[AI ERROR] DeepSeek non-retryable status={status}, abort retries")
                raise
        except (KeyError, ValueError, json.JSONDecodeError) as exc:
            last_error = exc
            elapsed_ms = int((time.monotonic() - started_at) * 1000)
            print(
                f"[AI WARN] DeepSeek parse error attempt {attempt_no}/{total_attempts}"
                f" after {elapsed_ms}ms: {exc}"
            )

        if attempt < MAX_RETRIES:
            sleep_seconds = _retry_sleep_seconds(attempt)
            print(
                f"[AI INFO] DeepSeek retry sleeping {sleep_seconds:.2f}s"
                f" before attempt {attempt_no + 1}/{total_attempts}"
            )
            time.sleep(sleep_seconds)

    if last_error:
        print("[AI ERROR] DeepSeek failed after retries:", last_error)
        raise last_error
    raise RuntimeError("DeepSeek request failed without specific error")


def deepseek_decide(context, messages_history):

    player_id = str(context.get("player_id") or "global")

    # ⭐ 节流：改成 0.6 秒
    now = time.time()
    last = _LAST_CALL_TS.get(player_id, 0.0)
    if (now - last) < MIN_INTERVAL:
        return {
            "option": None,
            "node": {
                "title": "昆明湖 · 静默帧",
                "text": "微风轻拂，但故事仍在缓缓流动。"
            },
            "world_patch": {"variables": {}, "mc": {}}
        }

    # ⭐ 缓存命中
    key = _make_cache_key(context, messages_history)
    cached = _cache_get(key)
    if cached:
        _LAST_CALL_TS[player_id] = now
        return cached

    # ⭐ 无 API KEY → 本地占位剧情
    if not API_KEY:
        return {
            "option": None,
            "node": {
                "title": "昆明湖 · 本地风声",
                "text": "（未配置 AI 密钥，使用占位剧情）"
            },
            "world_patch": {"variables": {}, "mc": {}}
        }

    # ⭐ 真正请求 DeepSeek
    user_prompt = f"""
    根据玩家输入与历史剧情生成下一步剧情。
    只输出 JSON：
    {{
      "option": ...,
      "node": {{ "title": "...", "text": "..." }},
      "world_patch": {{
         "variables": {{}},
         "mc": {{}}
      }}
    }}
    context = {json.dumps(context, ensure_ascii=False)}
    """

    msgs = [{"role": "system", "content": SYSTEM_PROMPT}]
    msgs += messages_history[-12:]
    msgs.append({"role": "user", "content": user_prompt})

    payload = {
        "model": MODEL,
        "messages": msgs,
        "temperature": 0.8,
        "response_format": {"type": "json_object"},
    }

    try:
        parsed = _call_deepseek_api(payload)
        _cache_put(key, parsed)
        _LAST_CALL_TS[player_id] = time.time()
        return parsed

    except Exception as e:
        print("[AI ERROR]", e)
        _LAST_CALL_TS[player_id] = time.time()
        return {
            "option": None,
            "node": {"title": "昆明湖 · 静默", "text": "AI 一时沉默，但湖水依旧流动。"},
            "world_patch": {"variables": {}, "mc": {"tell": "AI 出错，使用安全剧情"}},
        }


def call_deepseek(
    context: Optional[Dict[str, Any]],
    messages: List[Dict[str, str]],
    temperature: float = 0.7,
    response_format: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Generic DeepSeek API wrapper used by story/world tools."""

    if not API_KEY:
        return {
            "response": json.dumps(
                {"error": "missing_api_key", "context": context or {}},
                ensure_ascii=False,
            )
        }

    payload_messages: List[Dict[str, str]] = []
    if context:
        ctx_json = json.dumps(context, ensure_ascii=False)
        payload_messages.append({"role": "system", "content": f"上下文:\n{ctx_json}"})
    payload_messages.extend(messages)

    payload = {
        "model": MODEL,
        "messages": payload_messages,
        "temperature": temperature,
    }
    if response_format is not None:
        payload["response_format"] = response_format
    else:
        payload["response_format"] = {"type": "json_object"}

    try:
        parsed = _call_deepseek_api(payload)
        if isinstance(parsed, (dict, list)):
            response_text = json.dumps(parsed, ensure_ascii=False)
        else:
            response_text = str(parsed)
        return {"response": response_text, "parsed": parsed}
    except Exception as exc:
        print("[AI ERROR] call_deepseek failed:", exc)
        return {
            "response": json.dumps(
                {"error": str(exc), "context": context or {}}, ensure_ascii=False
            )
        }