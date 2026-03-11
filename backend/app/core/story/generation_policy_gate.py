from __future__ import annotations

import hashlib
import json
import math
import random
import time
from typing import Any, Dict, List, Optional


def _now_ms() -> int:
    return int(time.time() * 1000)


def _safe_int(value: Any, default: int) -> int:
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return int(default)


def _safe_float(value: Any, default: float) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return float(default)


def _stable_json(payload: Any) -> str:
    try:
        return json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    except Exception:
        return "{}"


def _deterministic_roll(seed_text: str) -> float:
    digest = hashlib.sha256(seed_text.encode("utf-8")).hexdigest()
    raw = int(digest[:16], 16)
    denominator = float(0xFFFFFFFFFFFFFFFF)
    return round(raw / denominator, 6)


def sanitize_generation_policy(payload: Dict[str, Any] | None) -> Dict[str, Any]:
    source = payload if isinstance(payload, dict) else {}

    scene_cooldown = max(0.0, _safe_float(source.get("scene_cooldown"), 60.0))
    spawn_probability = min(1.0, max(0.0, _safe_float(source.get("spawn_probability"), 0.4)))
    max_scenes_per_hour = max(1, _safe_int(source.get("max_scenes_per_hour"), 5))
    spawn_distance = max(0.0, _safe_float(source.get("spawn_distance"), 40.0))

    require_player_movement = bool(source.get("require_player_movement", True))
    require_new_location = bool(source.get("require_new_location", True))

    return {
        "scene_cooldown": scene_cooldown,
        "spawn_probability": spawn_probability,
        "max_scenes_per_hour": max_scenes_per_hour,
        "spawn_distance": spawn_distance,
        "require_player_movement": require_player_movement,
        "require_new_location": require_new_location,
    }


def get_generation_policy_snapshot() -> Dict[str, Any]:
    try:
        from app.api.settings_api import get_generation_policy_snapshot as _settings_policy_snapshot

        raw = _settings_policy_snapshot()
    except Exception:
        raw = {}

    return sanitize_generation_policy(raw if isinstance(raw, dict) else {})


def coerce_location_payload(value: Any) -> Dict[str, Any] | None:
    if not isinstance(value, dict):
        return None

    x_raw = value.get("x") if value.get("x") is not None else value.get("base_x")
    y_raw = value.get("y") if value.get("y") is not None else value.get("base_y")
    z_raw = value.get("z") if value.get("z") is not None else value.get("base_z")

    if x_raw is None and y_raw is None and z_raw is None:
        return None

    location = {
        "x": _safe_float(x_raw, 0.0),
        "y": _safe_float(y_raw, 64.0),
        "z": _safe_float(z_raw, 0.0),
    }

    world_token = str(value.get("world") or "").strip()
    if world_token:
        location["world"] = world_token

    return location


def location_from_event_payload(payload: Dict[str, Any] | None) -> Dict[str, Any] | None:
    if not isinstance(payload, dict):
        return None

    for key in ("location", "anchor", "position", "player_position"):
        location = coerce_location_payload(payload.get(key))
        if location is not None:
            return location

    return None


def location_distance(a: Dict[str, Any] | None, b: Dict[str, Any] | None) -> float | None:
    if not isinstance(a, dict) or not isinstance(b, dict):
        return None

    ax = _safe_float(a.get("x"), 0.0)
    ay = _safe_float(a.get("y"), 0.0)
    az = _safe_float(a.get("z"), 0.0)
    bx = _safe_float(b.get("x"), 0.0)
    by = _safe_float(b.get("y"), 0.0)
    bz = _safe_float(b.get("z"), 0.0)

    return math.sqrt((ax - bx) ** 2 + (ay - by) ** 2 + (az - bz) ** 2)


def generation_runtime_payload(scene_generation: Dict[str, Any] | None) -> Dict[str, Any]:
    source = scene_generation if isinstance(scene_generation, dict) else {}
    runtime = source.get("generation_policy_runtime") if isinstance(source.get("generation_policy_runtime"), dict) else {}
    return dict(runtime)


def _avg_scene_interval_seconds(timestamps_ms: List[int]) -> float | None:
    if len(timestamps_ms) < 2:
        return None

    ordered: List[int] = []
    for item in timestamps_ms:
        value = _safe_int(item, 0)
        if value > 0:
            ordered.append(value)
    ordered.sort()
    if len(ordered) < 2:
        return None

    intervals_ms: List[int] = []
    for index in range(1, len(ordered)):
        delta = max(0, ordered[index] - ordered[index - 1])
        intervals_ms.append(delta)

    if not intervals_ms:
        return None

    avg_ms = float(sum(intervals_ms)) / float(len(intervals_ms))
    return round(avg_ms / 1000.0, 2)


def _scene_rate_health(avg_scene_interval: float | None) -> Dict[str, Any]:
    if avg_scene_interval is None:
        return {"status": "UNKNOWN", "label": "no_data", "note": "Need more generated scenes to determine scene rate."}
    if avg_scene_interval < 60.0:
        return {
            "status": "HIGH",
            "label": "too_fast",
            "note": "Scene generation is too fast (<60s average interval).",
        }
    if avg_scene_interval <= 300.0:
        return {
            "status": "NORMAL",
            "label": "balanced",
            "note": "Scene generation interval is in the target band (60s-300s).",
        }
    if avg_scene_interval <= 600.0:
        return {
            "status": "MEDIUM",
            "label": "slightly_slow",
            "note": "Scene generation is slightly slow (300s-600s average interval).",
        }
    return {
        "status": "LOW",
        "label": "too_slow",
        "note": "Scene generation is too slow (>600s average interval).",
    }


def _policy_pressure_health(policy_block_rate: float) -> Dict[str, Any]:
    if policy_block_rate >= 0.6:
        return {
            "status": "HIGH",
            "label": "heavy_blocking",
            "note": "A large share of generation attempts are blocked by policy.",
        }
    if policy_block_rate >= 0.3:
        return {
            "status": "MEDIUM",
            "label": "moderate_blocking",
            "note": "Policy blocking is moderate; pacing may tighten during bursts.",
        }
    return {
        "status": "LOW",
        "label": "light_blocking",
        "note": "Policy blocking is low.",
    }


def _cooldown_stress_health(policy_cooldown_hits: int, policy_gate_blocked_count: int) -> Dict[str, Any]:
    blocked = max(0, int(policy_gate_blocked_count))
    cooldown_hits = max(0, int(policy_cooldown_hits))
    cooldown_hit_rate = (float(cooldown_hits) / float(blocked)) if blocked > 0 else 0.0

    if cooldown_hits >= 50 or (blocked >= 10 and cooldown_hit_rate >= 0.7):
        status = "HIGH"
        label = "cooldown_strict"
        note = "Cooldown is frequently the dominant block reason."
    elif cooldown_hits >= 15 or (blocked >= 5 and cooldown_hit_rate >= 0.4):
        status = "MEDIUM"
        label = "cooldown_pressure"
        note = "Cooldown contributes notable pressure to policy blocking."
    else:
        status = "LOW"
        label = "cooldown_relaxed"
        note = "Cooldown currently contributes limited blocking pressure."

    return {
        "status": status,
        "label": label,
        "cooldown_hit_rate": round(cooldown_hit_rate, 4),
        "note": note,
    }


def _runtime_health_payload(
    *,
    avg_scene_interval: float | None,
    policy_block_rate: float,
    policy_cooldown_hits: int,
    policy_gate_blocked_count: int,
) -> Dict[str, Any]:
    return {
        "scene_rate": _scene_rate_health(avg_scene_interval),
        "policy_pressure": _policy_pressure_health(policy_block_rate),
        "cooldown_stress": _cooldown_stress_health(policy_cooldown_hits, policy_gate_blocked_count),
    }


def _pacing_recommendation_payload(
    *,
    avg_scene_interval: float | None,
    policy_block_rate: float,
    policy_cooldown_hits: int,
    policy: Dict[str, Any],
    policy_gate_total_count: int,
) -> Dict[str, Any]:
    if policy_gate_total_count <= 0 and avg_scene_interval is None:
        return {
            "status": "insufficient_data",
            "severity": "none",
            "code": "insufficient_data",
            "message": "Need more runtime events before making pacing recommendations.",
            "suggested_policy_patch": None,
        }

    scene_cooldown = max(0.0, _safe_float(policy.get("scene_cooldown"), 60.0))

    if policy_block_rate > 0.6 and policy_cooldown_hits > 50:
        target_cooldown = max(30.0, round(scene_cooldown * 0.67, 1))
        if target_cooldown < scene_cooldown:
            return {
                "status": "actionable",
                "severity": "high",
                "code": "decrease_scene_cooldown",
                "message": "Policy blocking is high and cooldown hits are elevated; cooldown may be too strict.",
                "suggested_policy_patch": {
                    "scene_cooldown": target_cooldown,
                },
            }

    if avg_scene_interval is not None and avg_scene_interval < 60.0 and policy_block_rate < 0.3:
        target_cooldown = min(900.0, max(scene_cooldown + 10.0, round(scene_cooldown * 1.25, 1)))
        if target_cooldown > scene_cooldown:
            return {
                "status": "actionable",
                "severity": "medium",
                "code": "increase_scene_cooldown",
                "message": "Scene generation is too frequent; consider raising cooldown to reduce pacing pressure.",
                "suggested_policy_patch": {
                    "scene_cooldown": target_cooldown,
                },
            }

    if avg_scene_interval is not None and avg_scene_interval > 600.0 and scene_cooldown > 30.0:
        target_cooldown = max(30.0, round(scene_cooldown * 0.75, 1))
        if target_cooldown < scene_cooldown:
            return {
                "status": "actionable",
                "severity": "medium",
                "code": "ease_scene_cooldown",
                "message": "Scene generation appears slow; easing cooldown can improve responsiveness.",
                "suggested_policy_patch": {
                    "scene_cooldown": target_cooldown,
                },
            }

    return {
        "status": "stable",
        "severity": "low",
        "code": "no_change",
        "message": "Current pacing signals look stable; no immediate policy changes suggested.",
        "suggested_policy_patch": None,
    }


def _normalize_recent_gate_events(raw_events: Any) -> List[Dict[str, Any]]:
    if not isinstance(raw_events, list):
        return []

    normalized: List[Dict[str, Any]] = []
    for row in raw_events:
        if not isinstance(row, dict):
            continue
        at_ms = _safe_int(row.get("at_ms"), 0)
        if at_ms <= 0:
            continue
        normalized.append(
            {
                "at_ms": at_ms,
                "generated": bool(row.get("generated")),
                "reason": str(row.get("reason") or "").strip() or "unknown",
                "event_type": str(row.get("event_type") or "").strip(),
                "next_available_in": max(0, _safe_int(row.get("next_available_in"), 0)),
            }
        )

    normalized.sort(key=lambda item: _safe_int(item.get("at_ms"), 0))
    return normalized[-200:]


def _scene_timeline_payload(
    generated_timestamps: List[int],
    recent_gate_events: List[Dict[str, Any]],
    *,
    limit: int = 12,
) -> List[Dict[str, Any]]:
    events = list(recent_gate_events)
    if not events:
        for timestamp in generated_timestamps:
            value = _safe_int(timestamp, 0)
            if value <= 0:
                continue
            events.append(
                {
                    "at_ms": value,
                    "generated": True,
                    "reason": "allowed",
                    "event_type": "",
                    "next_available_in": 0,
                }
            )

    if not events:
        return []

    events.sort(key=lambda item: _safe_int(item.get("at_ms"), 0))

    rows: List[Dict[str, Any]] = []
    last_generated_at_ms = 0
    for event in events:
        at_ms = _safe_int(event.get("at_ms"), 0)
        if at_ms <= 0:
            continue

        generated = bool(event.get("generated"))
        interval_since_prev_generated_s: float | None = None
        if generated:
            if last_generated_at_ms > 0 and at_ms >= last_generated_at_ms:
                interval_since_prev_generated_s = round((at_ms - last_generated_at_ms) / 1000.0, 2)
            last_generated_at_ms = at_ms

        rows.append(
            {
                "at_ms": at_ms,
                "type": "scene_generated" if generated else "scene_blocked",
                "generated": generated,
                "reason": str(event.get("reason") or "").strip() or "unknown",
                "event_type": str(event.get("event_type") or "").strip() or None,
                "next_available_in": max(0, _safe_int(event.get("next_available_in"), 0)),
                "interval_since_prev_generated_s": interval_since_prev_generated_s,
            }
        )

    if not rows:
        return []

    limited = rows[-max(1, int(limit)) :]
    return list(reversed(limited))


def build_generation_seed(
    *,
    player_id: str,
    event_type: str | None,
    payload: Dict[str, Any] | None,
    tx_id: str | None = None,
    extra: Dict[str, Any] | None = None,
) -> str:
    seed_payload = {
        "player_id": str(player_id or "").strip(),
        "event_type": str(event_type or "").strip().lower(),
        "tx_id": str(tx_id or "").strip() or None,
        "payload": payload if isinstance(payload, dict) else {},
        "extra": extra if isinstance(extra, dict) else {},
    }
    return hashlib.sha256(_stable_json(seed_payload).encode("utf-8")).hexdigest()


def evaluate_generation_policy_gate(
    scene_generation: Dict[str, Any] | None,
    *,
    event_type: str | None,
    payload: Dict[str, Any] | None,
    deterministic_seed: str | None = None,
    policy: Dict[str, Any] | None = None,
) -> Dict[str, Any]:
    effective_policy = sanitize_generation_policy(policy if isinstance(policy, dict) else get_generation_policy_snapshot())
    now_ms = _now_ms()
    runtime = generation_runtime_payload(scene_generation)

    raw_timestamps = runtime.get("generated_timestamps_ms") if isinstance(runtime.get("generated_timestamps_ms"), list) else []
    recent_timestamps: List[int] = []
    one_hour_ms = 60 * 60 * 1000
    for row in raw_timestamps:
        timestamp = _safe_int(row, 0)
        if timestamp <= 0:
            continue
        if now_ms - timestamp <= one_hour_ms:
            recent_timestamps.append(timestamp)

    recent_timestamps.sort()

    last_generated_at_ms = _safe_int(runtime.get("last_generated_at_ms"), 0)
    if recent_timestamps:
        last_generated_at_ms = max(last_generated_at_ms, recent_timestamps[-1])

    last_player_location = coerce_location_payload(runtime.get("last_player_location"))
    last_generated_location = coerce_location_payload(runtime.get("last_generated_location"))
    current_location = location_from_event_payload(payload)

    allowed = True
    reason = "allowed"
    next_available_in = 0

    cooldown_seconds = _safe_float(effective_policy.get("scene_cooldown"), 0.0)
    if allowed and cooldown_seconds > 0 and last_generated_at_ms > 0:
        remaining_ms = int(cooldown_seconds * 1000) - (now_ms - last_generated_at_ms)
        if remaining_ms > 0:
            allowed = False
            reason = "scene_cooldown"
            next_available_in = max(0, int(math.ceil(remaining_ms / 1000)))

    max_per_hour = max(1, _safe_int(effective_policy.get("max_scenes_per_hour"), 1))
    if allowed and len(recent_timestamps) >= max_per_hour:
        earliest = recent_timestamps[0]
        remaining_ms = one_hour_ms - (now_ms - earliest)
        if remaining_ms > 0:
            allowed = False
            reason = "max_scenes_per_hour"
            next_available_in = max(0, int(math.ceil(remaining_ms / 1000)))

    required_spawn_distance = max(0.0, _safe_float(effective_policy.get("spawn_distance"), 0.0))
    if allowed and required_spawn_distance > 0:
        distance = location_distance(current_location, last_generated_location)
        if distance is not None and distance < required_spawn_distance:
            allowed = False
            reason = "spawn_distance"

    require_player_movement = bool(effective_policy.get("require_player_movement"))
    if allowed and require_player_movement:
        movement_distance = location_distance(current_location, last_player_location)
        if isinstance(last_player_location, dict) and isinstance(current_location, dict) and (movement_distance is None or movement_distance <= 0.01):
            allowed = False
            reason = "require_player_movement"

    require_new_location = bool(effective_policy.get("require_new_location"))
    if allowed and require_new_location:
        relocation_distance = location_distance(current_location, last_generated_location)
        if isinstance(last_generated_location, dict) and isinstance(current_location, dict) and (relocation_distance is None or relocation_distance <= 0.01):
            allowed = False
            reason = "require_new_location"

    probability = min(1.0, max(0.0, _safe_float(effective_policy.get("spawn_probability"), 1.0)))
    seed_text = str(deterministic_seed or "").strip()
    if seed_text:
        probability_roll = _deterministic_roll(seed_text)
        probability_mode = "deterministic"
    else:
        probability_roll = round(random.random(), 6)
        probability_mode = "random"

    if allowed and probability_roll > probability:
        allowed = False
        reason = "spawn_probability"

    return {
        "allowed": bool(allowed),
        "reason": reason,
        "next_available_in": int(next_available_in),
        "evaluated_at_ms": now_ms,
        "event_type": str(event_type or ""),
        "policy": dict(effective_policy),
        "generated_count_last_hour": len(recent_timestamps),
        "max_scenes_per_hour": max_per_hour,
        "probability_roll": probability_roll,
        "probability_mode": probability_mode,
        "deterministic_seed": seed_text or None,
        "current_location": dict(current_location) if isinstance(current_location, dict) else None,
        "_recent_timestamps": list(recent_timestamps),
    }


def record_generation_policy_gate(
    scene_generation: Dict[str, Any] | None,
    gate_result: Dict[str, Any],
    *,
    generated: bool,
) -> Dict[str, Any]:
    updated_generation = dict(scene_generation or {})
    runtime = generation_runtime_payload(updated_generation)
    gate_allowed = bool(gate_result.get("allowed"))
    gate_reason = str(gate_result.get("reason") or "unknown")

    now_ms = _safe_int(gate_result.get("evaluated_at_ms"), _now_ms())
    recent_timestamps = gate_result.get("_recent_timestamps") if isinstance(gate_result.get("_recent_timestamps"), list) else []
    normalized_timestamps: List[int] = []
    for row in recent_timestamps:
        timestamp = _safe_int(row, 0)
        if timestamp > 0:
            normalized_timestamps.append(timestamp)

    if generated:
        normalized_timestamps.append(now_ms)

    one_hour_ms = 60 * 60 * 1000
    normalized_timestamps = [ts for ts in normalized_timestamps if now_ms - ts <= one_hour_ms]
    normalized_timestamps.sort()

    current_location = coerce_location_payload(gate_result.get("current_location"))
    if current_location is not None:
        runtime["last_player_location"] = dict(current_location)

    if generated:
        runtime["last_generated_at_ms"] = now_ms
        if current_location is not None:
            runtime["last_generated_location"] = dict(current_location)

    recent_gate_events = _normalize_recent_gate_events(runtime.get("recent_gate_events"))
    recent_gate_events.append(
        {
            "at_ms": now_ms,
            "generated": bool(generated),
            "reason": gate_reason,
            "event_type": str(gate_result.get("event_type") or "").strip(),
            "next_available_in": max(0, _safe_int(gate_result.get("next_available_in"), 0)),
        }
    )
    recent_gate_events = recent_gate_events[-200:]

    policy_gate_total_count = max(0, _safe_int(runtime.get("policy_gate_total_count"), 0)) + 1
    policy_gate_blocked_count = max(0, _safe_int(runtime.get("policy_gate_blocked_count"), 0))
    if not gate_allowed:
        policy_gate_blocked_count += 1
    policy_gate_allowed_count = max(0, policy_gate_total_count - policy_gate_blocked_count)
    policy_block_rate = (float(policy_gate_blocked_count) / float(policy_gate_total_count)) if policy_gate_total_count > 0 else 0.0
    scenes_generated_last_hour = len(normalized_timestamps)
    avg_scene_interval = _avg_scene_interval_seconds(normalized_timestamps)
    policy_cooldown_hits = max(0, _safe_int(runtime.get("policy_cooldown_hits"), 0))
    if not gate_allowed and gate_reason == "scene_cooldown":
        policy_cooldown_hits += 1

    runtime["generated_timestamps_ms"] = normalized_timestamps[-200:]
    runtime["policy_gate_total_count"] = policy_gate_total_count
    runtime["policy_gate_allowed_count"] = policy_gate_allowed_count
    runtime["policy_gate_blocked_count"] = policy_gate_blocked_count
    runtime["scenes_generated_last_hour"] = scenes_generated_last_hour
    runtime["scenes_blocked_by_policy"] = policy_gate_blocked_count
    runtime["policy_block_rate"] = round(policy_block_rate, 4)
    runtime["avg_scene_interval"] = avg_scene_interval
    runtime["policy_cooldown_hits"] = policy_cooldown_hits
    runtime["recent_gate_events"] = recent_gate_events
    runtime["last_result"] = {
        "allowed": gate_allowed,
        "reason": gate_reason,
        "next_available_in": _safe_int(gate_result.get("next_available_in"), 0),
        "evaluated_at_ms": now_ms,
        "generated": bool(generated),
    }

    updated_generation["generation_policy_runtime"] = runtime
    updated_generation["generation_policy"] = dict(gate_result.get("policy") or get_generation_policy_snapshot())
    updated_generation["generation_policy_result"] = {
        "allowed": gate_allowed,
        "reason": gate_reason,
        "next_available_in": _safe_int(gate_result.get("next_available_in"), 0),
        "evaluated_at_ms": now_ms,
        "generated": bool(generated),
    }
    updated_generation["generation_skipped"] = not gate_allowed
    updated_generation["generation_skip_reason"] = "" if gate_allowed else gate_reason
    updated_generation["scenes_generated_last_hour"] = scenes_generated_last_hour
    updated_generation["scenes_blocked_by_policy"] = policy_gate_blocked_count
    updated_generation["policy_block_rate"] = round(policy_block_rate, 4)
    updated_generation["avg_scene_interval"] = avg_scene_interval
    updated_generation["policy_cooldown_hits"] = policy_cooldown_hits

    return updated_generation


def generation_policy_observability_payload(scene_generation: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    scene_payload = scene_generation if isinstance(scene_generation, dict) else {}
    runtime = generation_runtime_payload(scene_payload)

    policy = scene_payload.get("generation_policy") if isinstance(scene_payload.get("generation_policy"), dict) else get_generation_policy_snapshot()
    gate = scene_payload.get("generation_policy_result") if isinstance(scene_payload.get("generation_policy_result"), dict) else {}

    raw_generated_timestamps = runtime.get("generated_timestamps_ms") if isinstance(runtime.get("generated_timestamps_ms"), list) else []
    recent_gate_events = _normalize_recent_gate_events(runtime.get("recent_gate_events"))
    now_ms = _now_ms()
    one_hour_ms = 60 * 60 * 1000
    normalized_generated_timestamps: List[int] = []
    for row in raw_generated_timestamps:
        timestamp = _safe_int(row, 0)
        if timestamp <= 0:
            continue
        if now_ms - timestamp <= one_hour_ms:
            normalized_generated_timestamps.append(timestamp)

    scenes_generated_last_hour = len(normalized_generated_timestamps)
    policy_gate_blocked_count = max(
        0,
        _safe_int(runtime.get("policy_gate_blocked_count"), _safe_int(scene_payload.get("scenes_blocked_by_policy"), 0)),
    )
    policy_gate_total_count = max(0, _safe_int(runtime.get("policy_gate_total_count"), 0))
    if policy_gate_total_count <= 0:
        policy_gate_total_count = max(0, _safe_int(runtime.get("policy_gate_allowed_count"), 0) + policy_gate_blocked_count)

    avg_scene_interval = _avg_scene_interval_seconds(normalized_generated_timestamps)
    policy_cooldown_hits = max(
        0,
        _safe_int(runtime.get("policy_cooldown_hits"), _safe_int(scene_payload.get("policy_cooldown_hits"), 0)),
    )

    raw_policy_block_rate = _safe_float(runtime.get("policy_block_rate"), -1.0)
    if raw_policy_block_rate < 0.0:
        raw_policy_block_rate = (float(policy_gate_blocked_count) / float(policy_gate_total_count)) if policy_gate_total_count > 0 else 0.0
    policy_block_rate = min(1.0, max(0.0, raw_policy_block_rate))

    skipped = False
    skip_reason = None
    if gate:
        skipped = not bool(gate.get("allowed"))
        reason = str(gate.get("reason") or "").strip()
        skip_reason = reason or None

    runtime_health = _runtime_health_payload(
        avg_scene_interval=avg_scene_interval,
        policy_block_rate=policy_block_rate,
        policy_cooldown_hits=policy_cooldown_hits,
        policy_gate_blocked_count=policy_gate_blocked_count,
    )
    pacing_recommendation = _pacing_recommendation_payload(
        avg_scene_interval=avg_scene_interval,
        policy_block_rate=policy_block_rate,
        policy_cooldown_hits=policy_cooldown_hits,
        policy=policy,
        policy_gate_total_count=policy_gate_total_count,
    )
    scene_timeline = _scene_timeline_payload(normalized_generated_timestamps, recent_gate_events)

    return {
        "generation_policy": dict(policy),
        "generation_policy_gate": dict(gate),
        "generation_skipped": skipped,
        "generation_skip_reason": skip_reason,
        "scenes_generated_last_hour": scenes_generated_last_hour,
        "scenes_blocked_by_policy": policy_gate_blocked_count,
        "policy_block_rate": round(policy_block_rate, 4),
        "avg_scene_interval": avg_scene_interval,
        "policy_cooldown_hits": policy_cooldown_hits,
        "runtime_health": runtime_health,
        "pacing_recommendation": pacing_recommendation,
        "scene_timeline": scene_timeline,
    }
