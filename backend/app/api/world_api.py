import os
import time
import math
from collections import defaultdict
from datetime import datetime, timezone
import json

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field
from typing import Optional, Dict, Any, Literal, List
import logging

from app.core.world.engine import WorldEngine
from app.core.story.story_engine import story_engine
from app.core.world.trigger import trigger_engine
from app.core.ai.intent_engine import parse_intent
from app.core.narrative.semantic_engine import infer_semantic_from_text
from app.core.narrative.scene_library import select_fragments_with_debug
from app.core.quest.runtime import quest_runtime
from app.core.semantic.player_tag_store import player_tag_store
from app.core.runtime.interaction_event import create_interaction_event, interaction_event_to_dict
from app.core.story.generation_policy_gate import (
    build_generation_seed as _core_build_generation_seed,
    evaluate_generation_policy_gate as _core_evaluate_generation_policy_gate,
    generation_policy_observability_payload as _core_generation_policy_observability_payload,
    get_generation_policy_snapshot as _core_get_generation_policy_snapshot,
    record_generation_policy_gate as _core_record_generation_policy_gate,
    sanitize_generation_policy as _core_sanitize_generation_policy,
)
from app.core.trng.transaction import build_tx_id

router = APIRouter(prefix="/world", tags=["World"])
world_engine = WorldEngine()
logger = logging.getLogger("uvicorn.error")
APPLY_REPORTS_LIMIT = 20
REPORT_STATUS_RANK: Dict[str, int] = {
    "REJECTED": 1,
    "PARTIAL": 2,
    "EXECUTED": 3,
}
apply_reports_by_player: Dict[str, Dict[str, Dict[str, Any]]] = defaultdict(dict)
fallback_state_by_player: Dict[str, Dict[str, Any]] = defaultdict(dict)
semantic_bootstrap_state_by_player: Dict[str, Dict[str, Any]] = defaultdict(dict)


def _now_ms() -> int:
    return int(time.time() * 1000)


def _as_bool_env(name: str, default: bool = False) -> bool:
    raw = os.environ.get(name)
    if raw is None:
        return default
    return str(raw).strip().lower() in {"1", "true", "yes", "on"}


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


def _normalize_token(value: Any) -> str:
    token = str(value or "").strip().lower()
    if not token:
        return ""
    return token.replace("-", "_").replace(" ", "_").strip("_")


def _normalize_token_list(values: Any) -> List[str]:
    if not isinstance(values, list):
        return []

    normalized: List[str] = []
    seen: set[str] = set()
    for value in values:
        token = _normalize_token(value)
        if not token or token in seen:
            continue
        seen.add(token)
        normalized.append(token)
    return normalized


def _sanitize_generation_policy(payload: Dict[str, Any] | None) -> Dict[str, Any]:
    return _core_sanitize_generation_policy(payload)


def _generation_policy_snapshot() -> Dict[str, Any]:
    return _core_get_generation_policy_snapshot()


def _coerce_location_payload(value: Any) -> Dict[str, Any] | None:
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


def _location_from_event_payload(payload: Dict[str, Any] | None) -> Dict[str, Any] | None:
    if not isinstance(payload, dict):
        return None

    for key in ("location", "anchor", "position", "player_position"):
        location = _coerce_location_payload(payload.get(key))
        if location is not None:
            return location

    return None


def _location_distance(a: Dict[str, Any] | None, b: Dict[str, Any] | None) -> float | None:
    if not isinstance(a, dict) or not isinstance(b, dict):
        return None

    ax = _safe_float(a.get("x"), 0.0)
    ay = _safe_float(a.get("y"), 0.0)
    az = _safe_float(a.get("z"), 0.0)
    bx = _safe_float(b.get("x"), 0.0)
    by = _safe_float(b.get("y"), 0.0)
    bz = _safe_float(b.get("z"), 0.0)

    return math.sqrt((ax - bx) ** 2 + (ay - by) ** 2 + (az - bz) ** 2)


def _generation_runtime_payload(scene_generation: Dict[str, Any] | None) -> Dict[str, Any]:
    source = scene_generation if isinstance(scene_generation, dict) else {}
    runtime = source.get("generation_policy_runtime") if isinstance(source.get("generation_policy_runtime"), dict) else {}
    return dict(runtime)


def _evaluate_generation_policy_gate(
    scene_generation: Dict[str, Any] | None,
    *,
    event_type: str | None,
    payload: Dict[str, Any] | None,
    deterministic_seed: str | None = None,
) -> Dict[str, Any]:
    return _core_evaluate_generation_policy_gate(
        scene_generation,
        event_type=event_type,
        payload=payload,
        deterministic_seed=deterministic_seed,
    )


def _record_generation_policy_gate(
    player_id: str,
    scene_generation: Dict[str, Any] | None,
    gate_result: Dict[str, Any],
    *,
    generated: bool,
) -> Dict[str, Any]:
    updated_generation = _core_record_generation_policy_gate(
        scene_generation,
        gate_result,
        generated=generated,
    )
    _update_scene_generation_for_player(player_id, updated_generation)
    return updated_generation


def _generation_policy_observability_payload(scene_generation: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    return _core_generation_policy_observability_payload(scene_generation)


def _interaction_type_from_rule_event(event_type: str) -> str:
    normalized = str(event_type or "").strip().lower()
    if normalized in {"chat", "talk", "npc_talk"}:
        return "talk"
    if normalized in {"collect", "pickup", "pickup_item", "item_pickup"}:
        return "collect"
    return "trigger"


def _trigger_key_from_rule_payload(incoming_type: str, payload: Dict[str, Any]) -> str:
    candidates = [
        payload.get("trigger"),
        payload.get("quest_event"),
        payload.get("event_type"),
        payload.get("type"),
        incoming_type,
    ]
    for candidate in candidates:
        token = str(candidate or "").strip().lower()
        if token:
            return token
    return "trigger"


def _npc_id_from_rule_payload(payload: Dict[str, Any]) -> str | None:
    for key in ("npc_id", "npc", "target", "entity_name"):
        value = payload.get(key)
        token = str(value or "").strip()
        if token:
            return token
    return None


def _anchor_from_rule_payload(payload: Dict[str, Any]) -> Dict[str, Any]:
    location = payload.get("location") if isinstance(payload.get("location"), dict) else {}
    explicit_anchor = payload.get("anchor") if isinstance(payload.get("anchor"), dict) else {}

    if explicit_anchor:
        return {
            "base_x": _safe_int(explicit_anchor.get("base_x"), 0),
            "base_y": _safe_int(explicit_anchor.get("base_y"), 64),
            "base_z": _safe_int(explicit_anchor.get("base_z"), 0),
            "anchor_mode": str(explicit_anchor.get("anchor_mode") or "player"),
        }

    return {
        "base_x": _safe_int(location.get("x"), 0),
        "base_y": _safe_int(location.get("y"), 64),
        "base_z": _safe_int(location.get("z"), 0),
        "anchor_mode": "player",
    }


def _text_from_interaction_event(event_payload: Dict[str, Any]) -> str:
    event_type = str(event_payload.get("type") or "trigger")
    data = event_payload.get("data") if isinstance(event_payload.get("data"), dict) else {}

    if event_type == "talk":
        text = str(data.get("text") or data.get("message") or "").strip()
        return text or "talk"

    if event_type == "collect":
        resource = str(data.get("resource") or data.get("item_type") or "unknown_resource")
        amount = _safe_int(data.get("amount") or data.get("count"), 1)
        return f"collect:{resource}:{amount}"

    trigger_key = str(data.get("trigger") or data.get("quest_event") or data.get("event_type") or "trigger")
    return f"trigger:{trigger_key}"


def _default_rule_event_id(player_id: str, incoming_type: str, payload: Dict[str, Any]) -> str:
    seed_payload = {
        "player_id": str(player_id or "").strip(),
        "event_type": str(incoming_type or "").strip().lower(),
        "payload": dict(payload or {}),
    }
    digest = _core_build_generation_seed(
        player_id=str(player_id or "").strip(),
        event_type=str(incoming_type or "").strip().lower(),
        payload=seed_payload,
    )
    return f"plugin_{incoming_type}_{digest[:12]}"


def _build_rule_event_interaction_payload(event: "RuleTriggerEvent") -> Dict[str, Any]:
    payload = dict(event.payload or {})
    incoming_type = str(event.event_type or "trigger").strip().lower() or "trigger"
    interaction_type = _interaction_type_from_rule_event(incoming_type)

    data = dict(payload)
    data.setdefault("event_type", incoming_type)
    npc_id = _npc_id_from_rule_payload(data)

    if interaction_type == "talk":
        if npc_id:
            data.setdefault("npc_id", npc_id)

    if interaction_type == "collect":
        data.setdefault("resource", data.get("item_type") or data.get("block_type") or "resource")
        data.setdefault("amount", _safe_int(data.get("amount") or data.get("count"), 1))
    elif interaction_type == "trigger":
        data.setdefault("trigger", _trigger_key_from_rule_payload(incoming_type, data))

    event_id = str(payload.get("event_id") or "").strip()
    if not event_id:
        event_id = _default_rule_event_id(event.player_id, incoming_type, data)

    interaction_event = create_interaction_event(
        event_type=interaction_type,
        player_id=event.player_id,
        npc_id=npc_id,
        anchor=_anchor_from_rule_payload(payload),
        data=data,
        event_id=event_id,
        timestamp_ms=_safe_int(payload.get("timestamp_ms"), _now_ms()),
    )
    return interaction_event_to_dict(interaction_event)


def _planned_rule_event_gate_seed(event: "RuleTriggerEvent") -> str:
    interaction_payload = _build_rule_event_interaction_payload(event)
    tx_events = [
        {
            "event_id": interaction_payload.get("event_id"),
            "type": interaction_payload.get("type"),
            "text": _text_from_interaction_event(interaction_payload),
        }
    ]
    planned_tx_id = build_tx_id(
        tx_events,
        rule_version="rule_v2_2",
        engine_version="engine_v2_1",
    )
    return _core_build_generation_seed(
        player_id=event.player_id,
        event_type=event.event_type,
        payload=event.payload if isinstance(event.payload, dict) else {},
        tx_id=planned_tx_id,
    )


def _ingest_rule_event_via_trng(event: "RuleTriggerEvent") -> Dict[str, Any]:
    interaction_payload = _build_rule_event_interaction_payload(event)

    from app.api.story_api import run_transaction

    tx_result = run_transaction(
        [
            {
                "event_id": interaction_payload["event_id"],
                "type": interaction_payload["type"],
                "text": _text_from_interaction_event(interaction_payload),
            }
        ],
        rule_version="rule_v2_2",
        engine_version="engine_v2_1",
    )

    return {
        "tx_id": tx_result.get("tx_id"),
        "committed_state_hash": tx_result.get("committed_state_hash"),
        "committed_graph_hash": tx_result.get("committed_graph_hash"),
        "event_count": tx_result.get("event_count"),
        "interaction_event": interaction_payload,
    }


def _rank_for_status(status: str) -> int:
    return REPORT_STATUS_RANK.get(status, 0)


def _upsert_apply_report(report: "ApplyReportInput") -> Dict[str, Any]:
    player_reports = apply_reports_by_player[report.player_id]
    build_id = report.build_id
    now_ms = _now_ms()
    incoming_rank = _rank_for_status(report.status)
    existing = player_reports.get(build_id)

    if not existing:
        record = {
            "build_id": build_id,
            "player_id": report.player_id,
            "report_count": 1,
            "first_seen_ms": now_ms,
            "last_seen_ms": now_ms,
            "status_rank": incoming_rank,
            "last_status": report.status,
            "last_failure_code": report.failure_code,
            "last_executed": report.executed,
            "last_failed": report.failed,
            "last_duration_ms": report.duration_ms,
            "last_payload_hash": report.payload_hash,
            "received_at": datetime.now(timezone.utc).isoformat(),
        }
        player_reports[build_id] = record
        return record

    existing["report_count"] = int(existing.get("report_count", 0)) + 1
    existing["last_seen_ms"] = now_ms
    existing["received_at"] = datetime.now(timezone.utc).isoformat()

    current_rank = int(existing.get("status_rank", 0))
    should_overwrite = incoming_rank > current_rank or incoming_rank == current_rank

    if should_overwrite:
        existing["status_rank"] = incoming_rank
        existing["last_status"] = report.status
        existing["last_failure_code"] = report.failure_code
        existing["last_executed"] = report.executed
        existing["last_failed"] = report.failed
        existing["last_duration_ms"] = report.duration_ms
        existing["last_payload_hash"] = report.payload_hash

    return existing


def _recent_reports_for_player(player_id: str) -> list[Dict[str, Any]]:
    reports = list(apply_reports_by_player.get(player_id, {}).values())
    reports.sort(key=lambda item: int(item.get("last_seen_ms", 0)), reverse=True)
    return reports[:APPLY_REPORTS_LIMIT]


def _scene_level_for_player(player_id: str):
    players_state = getattr(quest_runtime, "_players", None)
    if not isinstance(players_state, dict):
        return None

    state = players_state.get(player_id)
    if not isinstance(state, dict):
        return None

    return state.get("level")


def _scene_generation_for_player(player_id: str) -> Optional[Dict[str, Any]]:
    level = _scene_level_for_player(player_id)
    if level is not None:
        level_meta = getattr(level, "meta", None)
        if isinstance(level_meta, dict):
            scene_generation = level_meta.get("scene_generation")
            if isinstance(scene_generation, dict):
                semantic_bootstrap_state_by_player.pop(player_id, None)
                return dict(scene_generation)

        raw_payload = getattr(level, "_raw_payload", None)
        if isinstance(raw_payload, dict):
            raw_meta = raw_payload.get("meta")
            if isinstance(raw_meta, dict):
                scene_generation = raw_meta.get("scene_generation")
                if isinstance(scene_generation, dict):
                    semantic_bootstrap_state_by_player.pop(player_id, None)
                    return dict(scene_generation)

        semantic_bootstrap_state_by_player.pop(player_id, None)
        return None

    fallback_generation = semantic_bootstrap_state_by_player.get(player_id)
    if isinstance(fallback_generation, dict) and fallback_generation:
        return dict(fallback_generation)

    return None


def _default_scene_theme_token() -> str:
    token = _normalize_token(os.environ.get("DRIFT_DEFAULT_SCENE_THEME", "camp"))
    return token or "camp"


def _scene_theme_override_from_prediction(
    prediction: Dict[str, Any] | None,
    *,
    current_scene_theme: str,
) -> str | None:
    if not isinstance(prediction, dict):
        return None

    default_theme = _default_scene_theme_token()
    current_theme = _normalize_token(current_scene_theme)

    if current_theme and current_theme != default_theme:
        return None

    semantic_theme = _normalize_token(prediction.get("semantic"))
    if semantic_theme and semantic_theme != default_theme:
        return semantic_theme

    return None


def _bootstrap_scene_generation_for_talk_event(
    player_id: str,
    event_type: str | None,
    payload: Dict[str, Any] | None,
) -> Dict[str, Any] | None:
    normalized_player = str(player_id or "").strip()
    if not normalized_player:
        return None

    normalized_type = _normalize_token(event_type)
    if normalized_type not in {"talk", "chat"}:
        return None

    payload_dict = payload if isinstance(payload, dict) else {}
    text = _text_from_rule_event_payload(payload_dict)
    if not text:
        return None

    current_generation = _scene_generation_for_player(normalized_player) or {}
    updated_generation = dict(current_generation)
    updated_generation["scene_hint"] = text

    scene_theme_raw = updated_generation.get("scene_theme")
    scene_theme = str(scene_theme_raw).strip() if isinstance(scene_theme_raw, str) else ""
    if not scene_theme:
        scene_theme = os.environ.get("DRIFT_DEFAULT_SCENE_THEME", "camp")
    updated_generation["scene_theme"] = scene_theme

    prediction = _predict_scene_payload_for_player(normalized_player, scene_generation=updated_generation)
    theme_override = _scene_theme_override_from_prediction(prediction, current_scene_theme=scene_theme)
    if isinstance(theme_override, str) and theme_override.strip():
        scene_theme = theme_override
        updated_generation["scene_theme"] = scene_theme
        prediction = _predict_scene_payload_for_player(normalized_player, scene_generation=updated_generation)

    updated_generation["selected_root"] = prediction.get("predicted_root")
    updated_generation["candidate_scores"] = list(prediction.get("candidate_scores") or [])
    updated_generation["semantic_scores"] = dict(prediction.get("semantic_scores") or {})
    updated_generation["semantic_resolution"] = list(prediction.get("semantic_resolution") or [])

    _update_scene_generation_for_player(normalized_player, updated_generation)

    return {
        "scene_hint": text,
        "scene_theme": scene_theme,
        "scene_theme_override": theme_override,
        "predicted_root": prediction.get("predicted_root"),
        "candidate_count": len(updated_generation.get("candidate_scores") or []),
    }


def _text_from_rule_event_payload(payload: Dict[str, Any] | None) -> str:
    payload_dict = payload if isinstance(payload, dict) else {}
    for key in ("text", "message", "say", "utterance", "input", "content", "chat", "raw_text"):
        value = str(payload_dict.get(key) or "").strip()
        if value:
            return value

    nested_payload = payload_dict.get("payload") if isinstance(payload_dict.get("payload"), dict) else {}
    for key in ("text", "message", "say", "utterance", "input", "content", "chat", "raw_text"):
        value = str(nested_payload.get(key) or "").strip()
        if value:
            return value

    return ""


def _intent_summary_from_result(intent_result: Dict[str, Any] | None) -> Dict[str, Any] | None:
    payload = intent_result if isinstance(intent_result, dict) else {}
    intents = payload.get("intents") if isinstance(payload.get("intents"), list) else []
    if not intents:
        return None

    first = intents[0] if isinstance(intents[0], dict) else {}
    if not first:
        return None

    summary: Dict[str, Any] = {
        "type": str(first.get("type") or "").strip() or "UNKNOWN",
        "raw_text": str(first.get("raw_text") or "").strip() or None,
        "scene_theme": str(first.get("scene_theme") or first.get("theme") or "").strip() or None,
        "scene_hint": str(first.get("scene_hint") or first.get("hint") or "").strip() or None,
    }

    confidence = first.get("confidence")
    if confidence is not None:
        try:
            summary["confidence"] = float(confidence)
        except (TypeError, ValueError):
            pass

    if isinstance(first.get("minimap"), dict):
        summary["has_minimap"] = True

    return summary


def _remember_input_trace(
    player_id: str,
    *,
    event_type: str,
    text: str,
    intent_summary: Dict[str, Any] | None,
) -> Dict[str, Any]:
    scene_generation = _scene_generation_for_player(player_id) or {}
    updated_generation = dict(scene_generation)
    updated_generation["last_player_input"] = {
        "event_type": _normalize_token(event_type) or "talk",
        "text": str(text or "").strip(),
        "at_ms": _now_ms(),
    }
    if isinstance(intent_summary, dict) and intent_summary:
        updated_generation["last_intent"] = dict(intent_summary)

    _update_scene_generation_for_player(player_id, updated_generation)
    return updated_generation


def _prediction_inventory_resources(
    player_id: str,
    *,
    scene_generation: Optional[Dict[str, Any]] = None,
) -> Dict[str, int]:
    resources: Dict[str, int] = {}

    scene_resources = scene_generation.get("inventory_resources") if isinstance(scene_generation, dict) else None
    if isinstance(scene_resources, dict):
        for key, value in scene_resources.items():
            token = _normalize_token(key)
            amount = _safe_int(value, 0)
            if token and amount > 0:
                resources[token] = amount

    if resources:
        return resources

    try:
        from app.api.story_api import _scene_inventory_state_from_event_log

        inventory_state = _scene_inventory_state_from_event_log(player_id)
    except Exception:
        inventory_state = {}

    raw_resources = inventory_state.get("resources") if isinstance(inventory_state, dict) else {}
    if isinstance(raw_resources, dict):
        for key, value in raw_resources.items():
            token = _normalize_token(key)
            amount = _safe_int(value, 0)
            if token and amount > 0:
                resources[token] = amount

    return resources


def _registry_resources_for_scene_hint(
    player_id: str,
    scene_hint: str | None,
) -> tuple[Dict[str, int], Optional[str], List[Dict[str, Any]]]:
    normalized_hint = _normalize_token(scene_hint)

    try:
        player_items = player_tag_store.list_player_tags(player_id)
    except Exception:
        player_items = []

    if not player_items:
        return {}, None, []

    tokens = [row for row in normalized_hint.split("_") if row] if normalized_hint else []
    candidates = [normalized_hint] if normalized_hint else []
    for token in tokens:
        if token not in candidates:
            candidates.append(token)

    matched_items: List[Dict[str, Any]] = []
    resources: Dict[str, int] = {}
    matched_tag: Optional[str] = None

    for row in player_items:
        if not isinstance(row, dict):
            continue

        tag = _normalize_token(row.get("tag"))
        resource_id = _normalize_token(row.get("resource_id"))
        if not tag or not resource_id:
            continue

        tag_hit = bool(normalized_hint) and (tag in candidates or tag in normalized_hint or normalized_hint in tag)
        if not tag_hit:
            continue

        matched_tag = matched_tag or tag
        resources[resource_id] = int(resources.get(resource_id, 0)) + 1
        matched_items.append(
            {
                "tag": tag,
                "resource_id": resource_id,
                "resource_type": row.get("resource_type"),
                "namespace": row.get("namespace"),
                "source": row.get("source"),
            }
        )

    if matched_items:
        return resources, matched_tag, matched_items

    fallback_mode = _normalize_token(os.environ.get("DRIFT_REGISTRY_FALLBACK_MODE") or "latest_tag")
    if fallback_mode in {"none", "off", "disabled"}:
        return resources, matched_tag, matched_items

    for row in player_items:
        if not isinstance(row, dict):
            continue

        tag = _normalize_token(row.get("tag"))
        resource_id = _normalize_token(row.get("resource_id"))
        if not tag or not resource_id:
            continue

        matched_tag = tag
        resources[resource_id] = int(resources.get(resource_id, 0)) + 1
        matched_items.append(
            {
                "tag": tag,
                "resource_id": resource_id,
                "resource_type": row.get("resource_type"),
                "namespace": row.get("namespace"),
                "source": row.get("source"),
                "fallback": True,
                "match_mode": "latest_tag",
            }
        )
        break

    return resources, matched_tag, matched_items


def _primary_registry_resource_id(registry_resources: Dict[str, int] | None) -> Optional[str]:
    if not isinstance(registry_resources, dict):
        return None

    ranked: List[tuple[str, int]] = []
    for key, value in registry_resources.items():
        token = str(key or "").strip().lower()
        amount = _safe_int(value, 0)
        if token and amount > 0:
            ranked.append((token, amount))

    if not ranked:
        return None

    ranked.sort(key=lambda item: (-item[1], item[0]))
    return ranked[0][0]


def _registry_material_for_resource(resource_id: str) -> str:
    token = str(resource_id or "").strip().lower()
    if ":" in token:
        token = token.split(":", 1)[1]
    token = token.replace("-", "_").replace(" ", "_")

    aliases = {
        "fire": "campfire",
        "bonfire": "campfire",
        "wood": "oak_planks",
        "plank": "oak_planks",
        "planks": "oak_planks",
        "log": "oak_log",
    }
    normalized_token = aliases.get(token, token)

    material_map = {
        "campfire": "CAMPFIRE",
        "torch": "TORCH",
        "lantern": "LANTERN",
        "chest": "CHEST",
        "barrel": "BARREL",
        "crafting_table": "CRAFTING_TABLE",
        "furnace": "FURNACE",
        "oak_planks": "OAK_PLANKS",
        "oak_log": "OAK_LOG",
        "cobblestone": "COBBLESTONE",
        "stone": "STONE",
    }
    if normalized_token in material_map:
        return material_map[normalized_token]

    fallback = "".join(ch if ch.isalnum() else "_" for ch in normalized_token).strip("_").upper()
    return fallback or "OAK_PLANKS"


def _apply_registry_override_to_scene_patch(
    scene_patch: Dict[str, Any] | None,
    registry_resources: Dict[str, int] | None,
) -> Dict[str, Any]:
    if not isinstance(scene_patch, dict):
        return {}

    primary_resource = _primary_registry_resource_id(registry_resources)
    if not primary_resource:
        return dict(scene_patch)

    patched = dict(scene_patch)
    mc_patch = patched.get("mc") if isinstance(patched.get("mc"), dict) else {}
    if not mc_patch:
        return patched

    patched_mc = dict(mc_patch)
    block_event_ids: List[str] = []

    raw_blocks = patched_mc.get("blocks")
    if isinstance(raw_blocks, list):
        next_blocks: List[Dict[str, Any]] = []
        for row in raw_blocks:
            if not isinstance(row, dict):
                continue
            row_payload = dict(row)
            row_payload["type"] = primary_resource
            row_payload["registry_asset_override"] = True
            event_id = str(row_payload.get("_scene_event_id") or "").strip()
            if event_id:
                block_event_ids.append(event_id)
            next_blocks.append(row_payload)
        if next_blocks:
            patched_mc["blocks"] = next_blocks

    material_token = _registry_material_for_resource(primary_resource)
    raw_build_multi = patched_mc.get("build_multi")
    if isinstance(raw_build_multi, list):
        next_build_multi: List[Dict[str, Any]] = []
        for row in raw_build_multi:
            if not isinstance(row, dict):
                continue
            row_payload = dict(row)
            event_id = str(row_payload.get("_scene_event_id") or "").strip()
            if event_id and event_id in block_event_ids:
                row_payload["material"] = material_token
                row_payload["registry_asset_override"] = True
            next_build_multi.append(row_payload)
        if next_build_multi:
            patched_mc["build_multi"] = next_build_multi

    if not block_event_ids:
        base_offset = {
            "dx": 0.0,
            "dy": 0.0,
            "dz": 0.0,
        }
        world_name: Optional[str] = None
        for list_key in ("build_multi", "blocks", "spawn_multi"):
            rows = patched_mc.get(list_key)
            if not isinstance(rows, list):
                continue
            for row in rows:
                if not isinstance(row, dict):
                    continue
                if isinstance(row.get("offset"), dict):
                    offset_payload = row.get("offset") or {}
                    base_offset = {
                        "dx": _safe_float(offset_payload.get("dx"), 0.0),
                        "dy": _safe_float(offset_payload.get("dy"), 0.0),
                        "dz": _safe_float(offset_payload.get("dz"), 0.0),
                    }
                row_world = str(row.get("world") or "").strip()
                if row_world:
                    world_name = row_world
                break
            if world_name:
                break

        event_id = "spawn_registry_resource"
        blocks_payload = list(patched_mc.get("blocks") or []) if isinstance(patched_mc.get("blocks"), list) else []
        block_directive: Dict[str, Any] = {
            "type": primary_resource,
            "offset": dict(base_offset),
            "_scene_event_id": event_id,
            "registry_asset_override": True,
        }
        if world_name:
            block_directive["world"] = world_name
        blocks_payload.append(block_directive)
        patched_mc["blocks"] = blocks_payload

        build_payload = list(patched_mc.get("build_multi") or []) if isinstance(patched_mc.get("build_multi"), list) else []
        build_directive: Dict[str, Any] = {
            "shape": "line",
            "size": 1,
            "material": material_token,
            "offset": dict(base_offset),
            "_scene_event_id": event_id,
            "registry_asset_override": True,
        }
        if world_name:
            build_directive["world"] = world_name
        build_payload.append(build_directive)
        patched_mc["build_multi"] = build_payload

    patched["mc"] = patched_mc
    patched_meta = patched.get("meta") if isinstance(patched.get("meta"), dict) else {}
    patched_meta["registry_asset_override"] = True
    patched_meta["registry_primary_resource"] = primary_resource
    patched["meta"] = patched_meta
    return patched


def _prediction_selection_context(scene_generation: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    if not isinstance(scene_generation, dict):
        return {}

    history = scene_generation.get("root_history") if isinstance(scene_generation.get("root_history"), list) else []
    normalized_history: List[str] = []
    seen: set[str] = set()
    for value in history:
        token = _normalize_token(value)
        if not token or token in seen:
            continue
        seen.add(token)
        normalized_history.append(token)

    selected_root = _normalize_token(scene_generation.get("selected_root"))
    if selected_root:
        normalized_history = [selected_root] + [item for item in normalized_history if item != selected_root]

    if not normalized_history:
        return {}

    return {
        "recent_selected_roots": normalized_history,
    }


def _top_reason_from_candidate_scores(candidate_scores: List[Dict[str, Any]]) -> Optional[str]:
    if not candidate_scores:
        return None

    first = candidate_scores[0] if isinstance(candidate_scores[0], dict) else {}
    reason = str(first.get("reason") or "").strip()
    if reason:
        return reason

    influence = first.get("influence") if isinstance(first.get("influence"), list) else []
    for row in influence:
        if not isinstance(row, dict):
            continue
        semantic = _normalize_token(row.get("semantic"))
        score = float(row.get("score") or 0.0)
        if semantic and score > 0:
            return f"{semantic} semantic +{score:.3f}"

    return None


def _predict_scene_payload_for_player(
    player_id: str,
    *,
    scene_generation: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    resources = _prediction_inventory_resources(player_id, scene_generation=scene_generation)
    selection_context = _prediction_selection_context(scene_generation)

    story_theme = ""
    scene_hint = None
    if isinstance(scene_generation, dict):
        if isinstance(scene_generation.get("scene_theme"), str):
            story_theme = str(scene_generation.get("scene_theme") or "").strip()
        if isinstance(scene_generation.get("scene_hint"), str):
            scene_hint = str(scene_generation.get("scene_hint") or "").strip() or None

    text_semantic = infer_semantic_from_text(scene_hint) if scene_hint else None
    text_semantic_scores: Dict[str, int] = {}
    text_semantic_resolution: List[Dict[str, Any]] = []
    text_semantic_tag: Optional[str] = None
    text_semantic_root: Optional[str] = None
    text_semantic_score = 0
    text_semantic_keyword: Optional[str] = None

    if isinstance(text_semantic, dict):
        raw_scores = text_semantic.get("all_scores") if isinstance(text_semantic.get("all_scores"), dict) else {}
        for key, value in raw_scores.items():
            token = _normalize_token(key)
            amount = _safe_int(value, 0)
            if token and amount > 0:
                text_semantic_scores[token] = amount

        raw_resolution = text_semantic.get("resolution") if isinstance(text_semantic.get("resolution"), list) else []
        text_semantic_resolution = [dict(row) for row in raw_resolution if isinstance(row, dict)]

        text_semantic_tag = _normalize_token(text_semantic.get("semantic"))
        text_semantic_root = _normalize_token(text_semantic.get("predicted_root") or text_semantic.get("root"))
        text_semantic_score = max(0, _safe_int(text_semantic.get("score"), 0))

        raw_keywords = text_semantic.get("matched_keywords") if isinstance(text_semantic.get("matched_keywords"), list) else []
        for keyword in raw_keywords:
            keyword_text = str(keyword or "").strip()
            if keyword_text:
                text_semantic_keyword = keyword_text
                break

    registry_resources, registry_match_tag, registry_bindings = _registry_resources_for_scene_hint(player_id, scene_hint)

    resources_for_selection: Dict[str, int] = dict(resources)
    for token, amount in text_semantic_scores.items():
        resources_for_selection[token] = int(resources_for_selection.get(token, 0)) + max(0, int(amount))
    for token, amount in registry_resources.items():
        resources_for_selection[token] = int(resources_for_selection.get(token, 0)) + max(0, int(amount))

    selection = select_fragments_with_debug(
        resources_for_selection,
        story_theme,
        scene_hint=scene_hint,
        selection_context=selection_context if selection_context else None,
    )
    debug = selection.get("debug") if isinstance(selection.get("debug"), dict) else {}
    candidate_scores = debug.get("candidate_scores") if isinstance(debug.get("candidate_scores"), list) else []
    normalized_scores = [dict(row) for row in candidate_scores if isinstance(row, dict)]

    semantic_scores = debug.get("semantic_scores") if isinstance(debug.get("semantic_scores"), dict) else {}
    normalized_semantic_scores: Dict[str, int] = {}
    for key, value in semantic_scores.items():
        token = _normalize_token(key)
        amount = _safe_int(value, 0)
        if token and amount > 0:
            normalized_semantic_scores[token] = amount
    for token, amount in text_semantic_scores.items():
        normalized_semantic_scores[token] = max(_safe_int(normalized_semantic_scores.get(token), 0), int(amount))

    semantic_resolution = debug.get("semantic_resolution") if isinstance(debug.get("semantic_resolution"), list) else []
    normalized_semantic_resolution = [dict(row) for row in semantic_resolution if isinstance(row, dict)]
    if text_semantic_tag or text_semantic_scores:
        text_resolution_row: Dict[str, Any] = {
            "item": "$talk_text",
            "semantic_tags": list(sorted(text_semantic_scores.keys())) if text_semantic_scores else ([text_semantic_tag] if text_semantic_tag else []),
            "source": "talk_text_v3",
            "adapter_hit": False,
        }
        if text_semantic_keyword:
            text_resolution_row["keyword"] = text_semantic_keyword
        if text_semantic_score > 0:
            text_resolution_row["score"] = text_semantic_score
        if text_semantic_resolution:
            text_resolution_row["details"] = list(text_semantic_resolution)
        normalized_semantic_resolution.append(text_resolution_row)

    predicted_root = _normalize_token(debug.get("selected_root"))
    if not predicted_root and normalized_scores:
        predicted_root = _normalize_token(normalized_scores[0].get("fragment"))
    if not predicted_root and text_semantic_root:
        predicted_root = text_semantic_root

    if not normalized_scores and predicted_root:
        fallback_score = float(max(1, text_semantic_score)) if text_semantic_score > 0 else 1.0
        fallback_reason = "text semantic fallback"
        if text_semantic_tag:
            fallback_reason = f"text semantic: {text_semantic_tag}"
        normalized_scores = [
            {
                "fragment": predicted_root,
                "score": fallback_score,
                "reason": fallback_reason,
                "source": "talk_text_v3",
            }
        ]

    prediction: Dict[str, Any] = {
        "predicted_root": predicted_root or None,
        "candidate_scores": normalized_scores,
        "semantic_scores": dict(normalized_semantic_scores),
        "semantic_resolution": list(normalized_semantic_resolution),
        "inventory_resources": dict(resources),
        "registry_resources": dict(registry_resources),
        "registry_bindings": list(registry_bindings),
    }

    if registry_match_tag:
        prediction["registry_match_tag"] = registry_match_tag

    top_reason = _top_reason_from_candidate_scores(normalized_scores)
    if (not top_reason) and text_semantic_tag:
        top_reason = f"text semantic: {text_semantic_tag}"
    if top_reason:
        prediction["top_reason"] = top_reason

    if text_semantic_tag:
        prediction["semantic"] = text_semantic_tag
    if text_semantic_score > 0:
        prediction["semantic_score"] = text_semantic_score
    if text_semantic_keyword:
        prediction["semantic_keyword"] = text_semantic_keyword
    if text_semantic_scores:
        prediction["all_scores"] = dict(text_semantic_scores)

    return prediction


def _top_semantic_signal_from_prediction(prediction: Dict[str, Any]) -> tuple[Optional[str], int]:
    semantic_scores = prediction.get("semantic_scores") if isinstance(prediction.get("semantic_scores"), dict) else {}
    ranked: List[tuple[str, int]] = []
    for key, value in semantic_scores.items():
        token = _normalize_token(key)
        weight = _safe_int(value, 0)
        if token and weight > 0:
            ranked.append((token, weight))

    if not ranked:
        return None, 0

    ranked.sort(key=lambda item: (-item[1], item[0]))
    return ranked[0]


def _top_candidate_score_from_prediction(prediction: Dict[str, Any]) -> float:
    candidate_scores = prediction.get("candidate_scores") if isinstance(prediction.get("candidate_scores"), list) else []
    if not candidate_scores:
        return 0.0

    first = candidate_scores[0] if isinstance(candidate_scores[0], dict) else {}
    return max(0.0, _safe_float(first.get("score"), 0.0))


def _auto_bootstrap_scene_generation_for_player(
    player_id: str,
    prediction: Dict[str, Any],
) -> tuple[Dict[str, Any], Optional[Dict[str, Any]]]:
    if not isinstance(prediction, dict):
        return {}, None

    predicted_root = _normalize_token(prediction.get("predicted_root"))
    candidate_scores = prediction.get("candidate_scores") if isinstance(prediction.get("candidate_scores"), list) else []
    if not predicted_root and candidate_scores:
        first = candidate_scores[0] if isinstance(candidate_scores[0], dict) else {}
        predicted_root = _normalize_token(first.get("fragment"))

    top_semantic, semantic_score = _top_semantic_signal_from_prediction(prediction)
    top_candidate_score = _top_candidate_score_from_prediction(prediction)

    activation_threshold = max(1, _safe_int(os.environ.get("DRIFT_SCENE_AUTO_BOOTSTRAP_THRESHOLD"), 5))
    candidate_threshold = max(0.0, _safe_float(os.environ.get("DRIFT_SCENE_AUTO_BOOTSTRAP_SCORE_THRESHOLD"), 0.0))

    inventory_raw = prediction.get("inventory_resources") if isinstance(prediction.get("inventory_resources"), dict) else {}
    inventory_resources: Dict[str, int] = {}
    resource_total = 0
    for key, value in inventory_raw.items():
        token = _normalize_token(key)
        amount = _safe_int(value, 0)
        if token and amount > 0:
            inventory_resources[token] = amount
            resource_total += amount

    should_bootstrap = bool(predicted_root) and semantic_score >= activation_threshold
    should_bootstrap = should_bootstrap and top_candidate_score >= candidate_threshold and resource_total > 0

    if not should_bootstrap:
        return {}, None

    semantic_scores = prediction.get("semantic_scores") if isinstance(prediction.get("semantic_scores"), dict) else {}
    normalized_semantic_scores: Dict[str, int] = {}
    for key, value in semantic_scores.items():
        token = _normalize_token(key)
        amount = _safe_int(value, 0)
        if token and amount > 0:
            normalized_semantic_scores[token] = amount

    scene_theme = top_semantic or predicted_root
    scene_hint = predicted_root
    top_reason = str(prediction.get("top_reason") or "").strip() or "semantic_auto_bootstrap"
    semantic_resolution = prediction.get("semantic_resolution") if isinstance(prediction.get("semantic_resolution"), list) else []
    normalized_candidate_scores = [dict(row) for row in candidate_scores if isinstance(row, dict)]

    bootstrap_meta = {
        "triggered": True,
        "predicted_root": predicted_root,
        "semantic": top_semantic,
        "semantic_score": semantic_score,
        "candidate_score": top_candidate_score,
        "threshold": activation_threshold,
        "candidate_threshold": candidate_threshold,
        "resource_total": resource_total,
        "source": "semantic_auto_bootstrap",
    }

    scene_generation = {
        "scene_theme": scene_theme,
        "scene_hint": scene_hint,
        "selected_root": predicted_root,
        "candidate_scores": list(normalized_candidate_scores),
        "selected_children": [],
        "blocked": [],
        "reasons": {
            "selected_root": top_reason,
            "auto_bootstrap": "semantic_threshold_reached",
        },
        "semantic_scores": dict(normalized_semantic_scores),
        "semantic_resolution": [dict(row) for row in semantic_resolution if isinstance(row, dict)],
        "semantic_source": {},
        "inventory_resources": dict(inventory_resources),
        "root_history": [predicted_root],
        "selection_context": {
            "recent_selected_roots": [predicted_root],
        },
        "auto_bootstrap": {
            **bootstrap_meta,
            "timestamp_ms": _now_ms(),
        },
    }

    persisted = _update_scene_generation_for_player(player_id, scene_generation)
    bootstrap_meta["story_state_created"] = bool(persisted)

    return scene_generation, bootstrap_meta


def _scene_candidate_scores(
    scene_generation: Optional[Dict[str, Any]],
    prediction: Optional[Dict[str, Any]],
) -> List[Dict[str, Any]]:
    if isinstance(scene_generation, dict):
        raw_scores = scene_generation.get("candidate_scores")
        if isinstance(raw_scores, list) and raw_scores:
            return [dict(row) for row in raw_scores if isinstance(row, dict)]

    if isinstance(prediction, dict):
        raw_scores = prediction.get("candidate_scores")
        if isinstance(raw_scores, list) and raw_scores:
            return [dict(row) for row in raw_scores if isinstance(row, dict)]

    return []


def _scene_selected_root(
    scene_generation: Optional[Dict[str, Any]],
    prediction: Optional[Dict[str, Any]],
    candidate_scores: List[Dict[str, Any]],
) -> Optional[str]:
    if isinstance(scene_generation, dict):
        selected = _normalize_token(scene_generation.get("selected_root"))
        if selected:
            return selected

    if isinstance(prediction, dict):
        selected = _normalize_token(prediction.get("predicted_root"))
        if selected:
            return selected

    if candidate_scores:
        selected = _normalize_token(candidate_scores[0].get("fragment"))
        if selected:
            return selected

    return None


def _scene_reason_text(
    scene_generation: Optional[Dict[str, Any]],
    prediction: Optional[Dict[str, Any]],
    candidate_scores: List[Dict[str, Any]],
) -> Optional[str]:
    if isinstance(scene_generation, dict):
        reasons = scene_generation.get("reasons") if isinstance(scene_generation.get("reasons"), dict) else {}
        selected_reason = str(reasons.get("selected_root") or "").strip()
        if selected_reason:
            return selected_reason

    if isinstance(prediction, dict):
        top_reason = str(prediction.get("top_reason") or "").strip()
        if top_reason:
            return top_reason

    return _top_reason_from_candidate_scores(candidate_scores)


def _semantic_scores_payload(
    scene_generation: Optional[Dict[str, Any]],
    prediction: Optional[Dict[str, Any]],
) -> Dict[str, int]:
    semantic_scores: Dict[str, int] = {}

    if isinstance(scene_generation, dict) and isinstance(scene_generation.get("semantic_scores"), dict):
        for key, value in scene_generation.get("semantic_scores", {}).items():
            token = _normalize_token(key)
            amount = _safe_int(value, 0)
            if token and amount > 0:
                semantic_scores[token] = amount
        if semantic_scores:
            return semantic_scores

    if isinstance(prediction, dict) and isinstance(prediction.get("semantic_scores"), dict):
        for key, value in prediction.get("semantic_scores", {}).items():
            token = _normalize_token(key)
            amount = _safe_int(value, 0)
            if token and amount > 0:
                semantic_scores[token] = amount

    return semantic_scores


def _semantic_resolution_payload(
    scene_generation: Optional[Dict[str, Any]],
    prediction: Optional[Dict[str, Any]],
) -> List[Dict[str, Any]]:
    if isinstance(scene_generation, dict) and isinstance(scene_generation.get("semantic_resolution"), list):
        return [dict(row) for row in scene_generation.get("semantic_resolution") if isinstance(row, dict)]

    if isinstance(prediction, dict) and isinstance(prediction.get("semantic_resolution"), list):
        return [dict(row) for row in prediction.get("semantic_resolution") if isinstance(row, dict)]

    return []


def _semantic_source_payload(scene_generation: Optional[Dict[str, Any]]) -> Dict[str, int]:
    source = scene_generation.get("semantic_source") if isinstance(scene_generation, dict) else None
    if not isinstance(source, dict):
        return {}

    payload: Dict[str, int] = {}
    for key, value in source.items():
        token = _normalize_token(key)
        if not token:
            continue
        payload[token] = max(0, _safe_int(value, 0))
    return payload


def _semantic_breakdown(semantic_scores: Dict[str, int], *, limit: int = 8) -> List[Dict[str, Any]]:
    ranked = sorted(
        (
            {
                "semantic": token,
                "weight": amount,
            }
            for token, amount in semantic_scores.items()
            if token and amount > 0
        ),
        key=lambda item: (-_safe_int(item.get("weight"), 0), str(item.get("semantic") or "")),
    )
    return ranked[: max(1, int(limit))] if ranked else []


def _semantic_tags_for_resource(resource_token: str) -> tuple[List[str], str, bool]:
    token = _normalize_token(resource_token)
    if not token:
        return [], "fallback", False

    try:
        from app.core.semantic.semantic_adapter import resolve_semantics

        resolved = resolve_semantics(token)
    except Exception:
        resolved = {
            "semantic_tags": [token],
            "source": "fallback",
            "adapter_hit": False,
        }

    tags = _normalize_token_list(resolved.get("semantic_tags"))
    if not tags:
        tags = [token]

    source = _normalize_token(resolved.get("source")) or "fallback"
    adapter_hit = bool(resolved.get("adapter_hit")) and source != "fallback"
    return tags, source, adapter_hit


def _collect_behavior_influence(player_id: str, *, event_limit: int = 15) -> Dict[str, Any]:
    try:
        from app.api.story_api import (
            _collect_rule_event_rows,
            _event_row_timestamp_ms,
            _extract_collect_resource_from_rule_event,
        )

        rows = _collect_rule_event_rows(player_id)
    except Exception:
        rows = []
        _event_row_timestamp_ms = None
        _extract_collect_resource_from_rule_event = None

    events: List[Dict[str, Any]] = []
    semantic_weight: Dict[str, int] = {}
    semantic_sources: Dict[str, int] = {}

    for row in rows:
        if not callable(_extract_collect_resource_from_rule_event):
            continue

        extracted = _extract_collect_resource_from_rule_event(row)
        if not extracted:
            continue

        resource_name, amount = extracted
        resource_token = _normalize_token(resource_name)
        amount_value = _safe_int(amount, 0)
        if not resource_token or amount_value <= 0:
            continue

        tags, source, _ = _semantic_tags_for_resource(resource_token)
        semantic_sources[source] = int(semantic_sources.get(source, 0)) + 1

        for tag in tags:
            semantic_weight[tag] = int(semantic_weight.get(tag, 0)) + amount_value

        timestamp_ms = None
        if callable(_event_row_timestamp_ms):
            timestamp_ms = _event_row_timestamp_ms(row)

        event_payload: Dict[str, Any] = {
            "resource": resource_token,
            "amount": amount_value,
            "semantic_tags": list(tags),
            "source": source,
        }
        if isinstance(timestamp_ms, int) and timestamp_ms > 0:
            event_payload["timestamp_ms"] = timestamp_ms

        events.append(event_payload)

    semantic_rows = sorted(
        (
            {
                "semantic": token,
                "weight": amount,
            }
            for token, amount in semantic_weight.items()
            if token and amount > 0
        ),
        key=lambda item: (-_safe_int(item.get("weight"), 0), str(item.get("semantic") or "")),
    )

    event_rows = events[-max(1, int(event_limit)) :] if events else []

    return {
        "window_events": len(events),
        "recent_collect_events": event_rows,
        "behavior_semantic_weights": semantic_rows,
        "semantic_source": semantic_sources,
    }


def _scene_history_payload(
    scene_generation: Optional[Dict[str, Any]],
    selected_root: Optional[str],
) -> Dict[str, Any]:
    raw_history = scene_generation.get("root_history") if isinstance(scene_generation, dict) else []
    recent_history = _normalize_token_list(raw_history)

    if selected_root:
        recent_history = [selected_root] + [row for row in recent_history if row != selected_root]

    history_oldest_first = list(reversed(recent_history))

    def _history_pick(index: int) -> Optional[str]:
        if not history_oldest_first:
            return None
        idx = min(max(index, 0), len(history_oldest_first) - 1)
        return history_oldest_first[idx]

    latest_transition = None
    if len(recent_history) >= 2:
        latest_transition = {
            "from": recent_history[1],
            "to": recent_history[0],
        }

    return {
        "recent_roots": list(recent_history),
        "timeline": {
            "day1": _history_pick(0),
            "day3": _history_pick(2),
            "day5": _history_pick(4),
        },
        "latest_transition": latest_transition,
    }


def _scene_explanation_payload(player_id: str, scene_generation: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    generation = dict(scene_generation) if isinstance(scene_generation, dict) else None
    prediction = _predict_scene_payload_for_player(player_id, scene_generation=generation)

    resources = _prediction_inventory_resources(player_id, scene_generation=generation)
    candidate_scores = _scene_candidate_scores(generation, prediction)
    selected_root = _scene_selected_root(generation, prediction, candidate_scores)
    reason = _scene_reason_text(generation, prediction, candidate_scores)

    semantic_scores = _semantic_scores_payload(generation, prediction)
    semantic_resolution = _semantic_resolution_payload(generation, prediction)
    semantic_source = _semantic_source_payload(generation)
    semantic_ranked = _semantic_breakdown(semantic_scores, limit=8)

    selected_children: List[str] = []
    if isinstance(generation, dict) and isinstance(generation.get("selected_children"), list):
        selected_children = _normalize_token_list(generation.get("selected_children"))

    top_semantic = semantic_ranked[0].get("semantic") if semantic_ranked else None

    influence_payload = _collect_behavior_influence(player_id, event_limit=15)
    history_payload = _scene_history_payload(generation, selected_root)

    return {
        "semantic": top_semantic,
        "resources": dict(resources),
        "selected_root": selected_root,
        "reason": reason,
        "semantic_scores": dict(semantic_scores),
        "semantic_ranked": semantic_ranked,
        "semantic_resolution": semantic_resolution,
        "semantic_source": semantic_source,
        "selected_children": selected_children,
        "candidate_scores": candidate_scores,
        "influence": influence_payload,
        "history": history_payload,
        "prediction": prediction,
    }


def _update_scene_generation_for_player(player_id: str, scene_generation: Dict[str, Any]) -> bool:
    if not isinstance(scene_generation, dict):
        return False

    level = _scene_level_for_player(player_id)
    if level is None:
        semantic_bootstrap_state_by_player[player_id] = dict(scene_generation)
        return True

    semantic_bootstrap_state_by_player.pop(player_id, None)

    level_meta = getattr(level, "meta", None)
    if not isinstance(level_meta, dict):
        level_meta = {}
        setattr(level, "meta", level_meta)
    level_meta["scene_generation"] = dict(scene_generation)

    raw_payload = getattr(level, "_raw_payload", None)
    if isinstance(raw_payload, dict):
        raw_meta = raw_payload.get("meta")
        if not isinstance(raw_meta, dict):
            raw_meta = {}
            raw_payload["meta"] = raw_meta
        raw_meta["scene_generation"] = dict(scene_generation)

    return True


def _narrative_state_for_player(
    player_id: str,
    *,
    snapshot: Optional[Dict[str, Any]] = None,
    scene_generation: Optional[Dict[str, Any]] = None,
    story_snapshot: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    scene_payload = scene_generation if isinstance(scene_generation, dict) else {}
    stored_narrative_state = scene_payload.get("narrative_state") if isinstance(scene_payload.get("narrative_state"), dict) else {}
    stored_last_decision = None
    if isinstance(stored_narrative_state.get("last_decision"), dict):
        stored_last_decision = dict(stored_narrative_state.get("last_decision") or {})
    elif isinstance(scene_payload.get("last_decision"), dict):
        stored_last_decision = dict(scene_payload.get("last_decision") or {})

    try:
        from app.core.story.narrative_graph_evaluator import evaluate_narrative_state

        level_state = snapshot.get("level_state") if isinstance(snapshot, dict) else None
        recent_rule_events = snapshot.get("recent_rule_events") if isinstance(snapshot, dict) else None
        current_node_hint = None
        if isinstance(scene_generation, dict):
            current_node_hint = (
                (scene_generation.get("narrative_state") or {}).get("current_node")
                if isinstance(scene_generation.get("narrative_state"), dict)
                else None
            )

        evaluated_state = evaluate_narrative_state(
            level_state=level_state if isinstance(level_state, dict) else None,
            scene_generation=scene_generation if isinstance(scene_generation, dict) else None,
            recent_rule_events=recent_rule_events if isinstance(recent_rule_events, list) else None,
            current_node_hint=current_node_hint,
        )
        if isinstance(stored_last_decision, dict):
            evaluated_state["last_decision"] = dict(stored_last_decision)
        return evaluated_state
    except Exception:
        fallback_current_level = None
        if isinstance(story_snapshot, dict):
            fallback_current_level = story_snapshot.get("player_current_level")

        fallback_state = {
            "version": "narrative_state_v1",
            "graph_version": "p8a_v1",
            "current_arc": "main",
            "current_node": "",
            "unlocked_nodes": [],
            "completed_nodes": [],
            "transition_candidates": [],
            "blocked_by": [],
            "observed_signals": [],
            "level_id": fallback_current_level,
            "player_id": player_id,
        }
        if isinstance(stored_last_decision, dict):
            fallback_state["last_decision"] = dict(stored_last_decision)
        return fallback_state


def _narrative_fields_payload(narrative_state: Dict[str, Any]) -> Dict[str, Any]:
    state = dict(narrative_state) if isinstance(narrative_state, dict) else {}
    candidates = state.get("transition_candidates") if isinstance(state.get("transition_candidates"), list) else []
    blocked_by = state.get("blocked_by") if isinstance(state.get("blocked_by"), list) else []
    last_decision = state.get("last_decision") if isinstance(state.get("last_decision"), dict) else {}
    return {
        "narrative_state": state,
        "current_node": state.get("current_node"),
        "transition_candidates": list(candidates),
        "blocked_by": list(blocked_by),
        "last_decision": dict(last_decision),
        "narrative_decision": dict(last_decision),
    }


def _asset_registry_observability_payload(scene_generation: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    registry_version = None
    asset_count = 0
    builtin_asset_count = 0
    pack_asset_count = 0
    registry_enabled_packs: List[str] = []
    try:
        from app.core.assets.asset_loader import asset_registry_info

        info = asset_registry_info()
        if isinstance(info, dict):
            registry_version = info.get("version")
            asset_count = _safe_int(info.get("asset_count"), 0)
            builtin_asset_count = _safe_int(info.get("builtin_asset_count"), 0)
            pack_asset_count = _safe_int(info.get("pack_asset_count"), 0)
            raw_registry_packs = info.get("enabled_packs") if isinstance(info.get("enabled_packs"), list) else []
            registry_enabled_packs = [_normalize_token(row) for row in raw_registry_packs if _normalize_token(row)]
    except Exception:
        registry_version = None
        asset_count = 0
        builtin_asset_count = 0
        pack_asset_count = 0
        registry_enabled_packs = []

    scene_payload = scene_generation if isinstance(scene_generation, dict) else {}
    selected_assets = scene_payload.get("selected_assets") if isinstance(scene_payload.get("selected_assets"), list) else []
    asset_sources = scene_payload.get("asset_sources") if isinstance(scene_payload.get("asset_sources"), list) else []
    asset_selection = scene_payload.get("asset_selection") if isinstance(scene_payload.get("asset_selection"), dict) else {}
    fragment_source = scene_payload.get("fragment_source") if isinstance(scene_payload.get("fragment_source"), list) else []
    theme_filter = scene_payload.get("theme_filter") if isinstance(scene_payload.get("theme_filter"), dict) else {}

    if not asset_selection:
        asset_selection = {
            "selected_assets": list(selected_assets),
            "candidate_assets": [],
        }

    if not theme_filter:
        theme_filter = {
            "theme": scene_payload.get("scene_theme"),
            "applied": False,
            "allowed_fragments": [],
        }

    return {
        "asset_registry_version": registry_version,
        "asset_count": int(asset_count),
        "builtin_asset_count": int(builtin_asset_count),
        "pack_asset_count": int(pack_asset_count),
        "asset_registry_enabled_packs": list(registry_enabled_packs),
        "selected_assets": list(selected_assets),
        "asset_sources": list(asset_sources),
        "asset_selection": dict(asset_selection),
        "fragment_source": list(fragment_source),
        "theme_filter": dict(theme_filter),
    }


def _enabled_packs_payload() -> Dict[str, Any]:
    try:
        from app.core.packs.pack_registry import get_pack_registry

        registry = get_pack_registry()
        enabled_ids = registry.enabled_ids() if hasattr(registry, "enabled_ids") else []
        if not isinstance(enabled_ids, list):
            enabled_ids = []

        normalized: List[str] = []
        seen = set()
        for row in enabled_ids:
            token = _normalize_token(row)
            if not token or token in seen:
                continue
            seen.add(token)
            normalized.append(token)

        return {
            "enabled_packs": normalized,
        }
    except Exception:
        return {
            "enabled_packs": [],
        }


def _record_fallback_state(
    *,
    player_id: str,
    fallback_flag: bool,
    reason: str,
    level_id: Optional[str] = None,
    inject_version: Optional[str] = None,
) -> Dict[str, Any]:
    state = {
        "last_fallback_flag": bool(fallback_flag),
        "last_fallback_reason": reason,
        "last_fallback_level_id": level_id,
        "last_fallback_inject_version": inject_version,
        "last_fallback_at": datetime.now(timezone.utc).isoformat(),
    }
    fallback_state_by_player[player_id] = state
    return state

# ============================================================
# MODELS
# ============================================================
class MoveAction(BaseModel):
    x: float
    y: float
    z: float
    speed: float = 0.0
    moving: bool = False


class WorldAction(BaseModel):
    move: Optional[MoveAction] = None
    say: Optional[str] = None


class ApplyInput(BaseModel):
    action: WorldAction
    player_id: Optional[str] = "default"


class WorldApplyResponse(BaseModel):
    status: str
    world_state: Dict[str, Any]
    ai_option: Optional[str] = None              # ⭐ 已修复：必须是 str
    story_node: Optional[Dict[str, Any]] = None
    world_patch: Optional[Dict[str, Any]] = None
    trigger: Optional[Dict[str, Any]] = None


class EnterStoryRequest(BaseModel):
    player_id: str
    level_id: Optional[str] = None


class EndStoryRequest(BaseModel):
    player_id: str
    level_id: Optional[str] = None


class RuleTriggerEvent(BaseModel):
    player_id: str
    event_type: Optional[str] = None
    payload: Dict[str, Any] = Field(default_factory=dict)


class SpawnFragmentRequest(BaseModel):
    scene_theme: Optional[str] = None
    scene_hint: Optional[str] = None
    anchor: Optional[str] = None
    player_position: Optional[Dict[str, Any]] = None


class StoryResetRequest(BaseModel):
    clear_memory: bool = True
    clear_history: bool = True
    clear_inventory: bool = True
    clear_persisted_state: bool = True


class NarrativeChooseRequest(BaseModel):
    mode: Optional[str] = "auto_best"
    transition_id: Optional[str] = None


class ApplyReportInput(BaseModel):
    build_id: str = Field(min_length=1)
    player_id: str = Field(min_length=1)
    status: Literal["EXECUTED", "REJECTED", "PARTIAL"]
    failure_code: str = Field(min_length=1)
    executed: int = Field(ge=0)
    failed: int = Field(ge=0)
    duration_ms: int = Field(ge=0)
    payload_hash: str = Field(min_length=1)


# ============================================================
# APPLY API — v3（最终版）
# ============================================================
@router.post("/apply", response_model=WorldApplyResponse)
def apply_action(inp: ApplyInput):

    player_id = inp.player_id
    act = inp.action.dict(exclude_none=True)

    # 1) 世界物理更新
    new_state = world_engine.apply(act)
    vars_ = new_state.get("variables") or {}
    x = vars_.get("x", 0)
    y = vars_.get("y", 0)
    z = vars_.get("z", 0)

    # 2) 文本 → 意图解析
    say_text = act.get("say")
    intent_result = parse_intent(player_id, say_text, new_state, story_engine) if say_text else None
    
    # 提取第一个 intent（如果有多个，这里只处理第一个）
    intent = None
    if intent_result and "intents" in intent_result and len(intent_result["intents"]) > 0:
        intent = intent_result["intents"][0]

    # ============================================================
    # ⭐ 白名单世界指令（不走剧情）
    # ============================================================
    if intent:
        t = intent["type"]

        # ---------- 创建故事关卡（AI生成完整世界） ----------
        if t == "CREATE_STORY":
            import hashlib
            import time
            from app.api.story_api import InjectPayload, api_story_inject
            
            # 生成唯一level_id
            raw_text = intent.get("raw_text", "story")
            level_id = f"flagship_story_{hashlib.md5(f'{raw_text}{time.time()}'.encode()).hexdigest()[:8]}"
            
            # 调用story_api创建关卡（AI会生成完整世界）
            try:
                payload = InjectPayload(
                    level_id=level_id,
                    title=intent.get("title", "自由创作"),
                    text=raw_text,
                    player_id=player_id,
                    scene_theme=intent.get("scene_theme"),
                    scene_hint=intent.get("scene_hint"),
                )
                inject_result = api_story_inject(payload)

                if isinstance(inject_result, dict) and inject_result.get("version") == "plugin_payload_v1":
                    _record_fallback_state(
                        player_id=player_id,
                        fallback_flag=False,
                        reason="payload_v1",
                        level_id=level_id,
                        inject_version="plugin_payload_v1",
                    )
                    return WorldApplyResponse(
                        status="ok",
                        world_state=new_state,
                        story_node={
                            "title": "✨ 世界已创建",
                            "text": f"AI为你生成了新世界：{intent.get('title', '自由创作')}"
                        },
                        world_patch=inject_result,
                    )

                inject_version = inject_result.get("version") if isinstance(inject_result, dict) else None
                fallback_reason = "inject_non_payload_v1"
                _record_fallback_state(
                    player_id=player_id,
                    fallback_flag=True,
                    reason=fallback_reason,
                    level_id=level_id,
                    inject_version=str(inject_version) if inject_version is not None else None,
                )
                logger.warning(
                    "[CREATE_STORY] fell back to legacy world_patch; player_id=%s level_id=%s reason=%s inject_version=%s",
                    player_id,
                    level_id,
                    fallback_reason,
                    inject_version,
                )
                
                # 立即加载生成的关卡
                patch = story_engine.load_level_for_player(player_id, level_id)
                new_state = world_engine.apply_patch(patch)
                
                return WorldApplyResponse(
                    status="ok",
                    world_state=new_state,
                    story_node={
                        "title": "✨ 世界已创建", 
                        "text": f"AI为你生成了新世界：{intent.get('title', '自由创作')}"
                    },
                    world_patch=patch,
                    ai_response=inject_result.get("world_preview")
                )
            except Exception as e:
                # 创建失败时返回错误信息
                return WorldApplyResponse(
                    status="error",
                    world_state=new_state,
                    story_node={
                        "title": "创建失败", 
                        "text": f"世界生成出错: {str(e)}"
                    }
                )

        # ---------- 跳关 ----------
        if t == "GOTO_LEVEL":
            level = intent.get("level_id")
            canonical = story_engine.graph.canonicalize_level_id(level) if level else None
            level = canonical or level
            patch = story_engine.load_level_for_player(player_id, level)
            new_state = world_engine.apply_patch(patch)

            return WorldApplyResponse(
                status="ok",
                world_state=new_state,
                story_node={"title": "跳转关卡", "text": f"进入 {level}"},
                world_patch=patch
            )

        if t == "GOTO_NEXT_LEVEL":
            next_level = story_engine.get_next_level_id(None, player_id=player_id)
            patch = story_engine.load_level_for_player(player_id, next_level)
            new_state = world_engine.apply_patch(patch)

            return WorldApplyResponse(
                status="ok",
                world_state=new_state,
                story_node={"title": "下一关", "text": f"进入 {next_level}"},
                world_patch=patch
            )

        # ---------- 小地图 ----------
        if t == "SHOW_MINIMAP":
            mm = story_engine.minimap.to_dict(player_id)
            return WorldApplyResponse(
                status="ok",
                world_state=new_state,
                story_node={"title": "小地图", "text": "显示当前世界地图"},
                world_patch={"minimap": mm},
            )

        # ---------- 时间 ----------
        if t == "SET_DAY":
            patch = {"mc": {"time": "day"}}
            new_state = world_engine.apply_patch(patch)
            return WorldApplyResponse(status="ok", world_state=new_state, world_patch=patch)

        if t == "SET_NIGHT":
            patch = {"mc": {"time": "night"}}
            new_state = world_engine.apply_patch(patch)
            return WorldApplyResponse(status="ok", world_state=new_state, world_patch=patch)

        # ---------- 天气 ----------
        if t == "SET_WEATHER":
            w = intent.get("weather", "clear")
            patch = {"mc": {"weather": w}}
            new_state = world_engine.apply_patch(patch)
            return WorldApplyResponse(status="ok", world_state=new_state, world_patch=patch)

        # ---------- 造实体 ----------
        if t == "SPAWN_ENTITY":
            patch = {"mc": {
                "spawn": {
                    "type": intent.get("entity", "villager"),
                    "name": "NPC",
                    "offset": {"dx": 1, "dy": 0, "dz": 1}
                }
            }}
            new_state = world_engine.apply_patch(patch)
            return WorldApplyResponse(status="ok", world_state=new_state, world_patch=patch)

        # ---------- 建筑 ----------
        if t == "BUILD_STRUCTURE":
            patch = {"mc": {"build": intent.get("build")}}
            new_state = world_engine.apply_patch(patch)
            return WorldApplyResponse(status="ok", world_state=new_state, world_patch=patch)

    # ============================================================
    # ⭐ 剧情推进（只要说话一定触发）
    # ============================================================
    if say_text:
        option, node, patch = story_engine.advance(player_id, new_state, act)

        # 🛡️ 确保 ai_option 始终为字符串，兼容 DeepSeek 返回数组/对象
        option_value = None
        if isinstance(option, str) or option is None:
            option_value = option
        elif isinstance(option, (list, tuple)):
            if option:
                option_value = str(option[0])
        elif isinstance(option, (dict, int, float, bool)):
            option_value = str(option)
        else:
            option_value = None

        return WorldApplyResponse(
            status="ok",
            world_state=new_state,
            ai_option=option_value,
            story_node=node,
            world_patch=patch
        )

    # ============================================================
    # ⭐ 触发器（走路触发 level）
    # ============================================================
    tp = trigger_engine.check(player_id, x, y, z)

    if tp and tp.action == "load_level":
        patch = story_engine.load_level_for_player(player_id, tp.level_id)
        new_state = world_engine.apply_patch(patch)

        return WorldApplyResponse(
            status="ok",
            world_state=new_state,
            story_node={"title": "世界触发点", "text": f"成功加载 {tp.level_id}"},
            world_patch=patch,
            trigger={"id": tp.id, "level_id": tp.level_id}
        )

    # ============================================================
    # 默认（比如走路，没有剧情）
    # ============================================================
    return WorldApplyResponse(
        status="ok",
        world_state=new_state
    )


@router.get("/state/{player_id}")
def world_state(player_id: str):
    """Return a combined snapshot of the simulated world and story engine."""

    story_snapshot = story_engine.get_public_state(player_id)
    state = world_engine.get_state() or {}
    world_snapshot = {
        "variables": dict(state.get("variables", {})),
        "entities": dict(state.get("entities", {})),
    }
    debug_snapshot = quest_runtime.get_debug_snapshot(player_id)
    scene_generation = _scene_generation_for_player(player_id)
    narrative_state = _narrative_state_for_player(
        player_id,
        snapshot=debug_snapshot,
        scene_generation=scene_generation,
        story_snapshot=story_snapshot if isinstance(story_snapshot, dict) else None,
    )

    response = {
        "status": "ok",
        "player_id": player_id,
        "world": world_snapshot,
        "story": story_snapshot,
    }
    response.update(_narrative_fields_payload(narrative_state))
    response.update(_generation_policy_observability_payload(scene_generation))
    response.update(_asset_registry_observability_payload(scene_generation))
    response.update(_enabled_packs_payload())
    return response


# ============================================================
# Phase 1.5 skeleton endpoints
# ============================================================


@router.post("/story/enter")
def story_enter(request: EnterStoryRequest):
    target_level = request.level_id or story_engine.get_next_level_id(None, player_id=request.player_id)
    patch = None
    if target_level:
        patch = story_engine.load_level_for_player(request.player_id, target_level)
    logger.info("story_enter", extra={"player_id": request.player_id, "level_id": target_level})
    return {
        "status": "ok",
        "level_id": target_level,
        "world_patch": patch,
    }


@router.post("/story/start")
def story_start(request: EnterStoryRequest):
    preferred_level = request.level_id
    if not preferred_level:
        preferred_level = (
            story_engine.graph.get_start_level()
            or story_engine.DEFAULT_ENTRY_LEVEL
        )

    patch = None
    if preferred_level:
        patch = story_engine.load_level_for_player(request.player_id, preferred_level)

    logger.info(
        "story_start",
        extra={"player_id": request.player_id, "level_id": preferred_level},
    )

    return {
        "status": "ok",
        "level_id": preferred_level,
        "world_patch": patch,
    }


@router.post("/story/end")
def story_end(request: EndStoryRequest):
    player_state = story_engine.players.get(request.player_id, {})
    level = player_state.get("level")
    cleanup_patch = None
    if level:
        cleanup_patch = story_engine.exit_level_with_cleanup(request.player_id, level)
    else:
        quest_runtime.exit_level(request.player_id)
    logger.info("story_end", extra={"player_id": request.player_id, "level_id": getattr(level, "level_id", None)})
    return {
        "status": "ok",
        "world_patch": cleanup_patch,
    }


@router.post("/story/rule-event")
def story_rule_event(event: RuleTriggerEvent):
    normalized_event_type = _normalize_token(event.event_type)
    payload_dict = dict(event.payload or {}) if isinstance(event.payload, dict) else {}
    talk_text = _text_from_rule_event_payload(payload_dict) if normalized_event_type in {"talk", "chat"} else ""

    rule_payload: Dict[str, Any] = {
        "event_type": event.event_type,
        "payload": dict(payload_dict),
    }
    for key, value in payload_dict.items():
        if key not in rule_payload:
            rule_payload[key] = value
    if talk_text:
        rule_payload["text"] = talk_text

    response = quest_runtime.handle_rule_trigger(event.player_id, rule_payload)
    logger.debug(
        "story_rule_event",
        extra={"player_id": event.player_id, "event_type": event.event_type},
    )

    intent_summary: Dict[str, Any] | None = None
    intent_error: str | None = None
    registry_preview_resources: Dict[str, int] = {}
    registry_preview_match_tag: str | None = None
    registry_preview_bindings: List[Dict[str, Any]] = []
    if talk_text:
        try:
            parsed_intent = parse_intent(
                event.player_id,
                talk_text,
                world_engine.get_state() or {},
                story_engine,
            )
            intent_summary = _intent_summary_from_result(parsed_intent)
            logger.info(
                "intent_received",
                extra={
                    "player_id": event.player_id,
                    "event_type": normalized_event_type or "talk",
                    "text": talk_text,
                    "intent_type": (intent_summary or {}).get("type"),
                },
            )
        except Exception as exc:
            intent_error = str(exc)
            logger.warning(
                "intent_received_failed",
                extra={
                    "player_id": event.player_id,
                    "event_type": normalized_event_type or "talk",
                    "error": intent_error,
                },
            )

        _remember_input_trace(
            event.player_id,
            event_type=normalized_event_type or "talk",
            text=talk_text,
            intent_summary=intent_summary,
        )

        try:
            (
                registry_preview_resources,
                registry_preview_match_tag,
                registry_preview_bindings,
            ) = _registry_resources_for_scene_hint(event.player_id, talk_text)

            scene_generation_snapshot = _scene_generation_for_player(event.player_id) or {}
            updated_scene_generation = dict(scene_generation_snapshot)
            updated_scene_generation["registry_resources"] = dict(registry_preview_resources)
            updated_scene_generation["registry_bindings"] = list(registry_preview_bindings)
            if registry_preview_match_tag:
                updated_scene_generation["registry_match_tag"] = registry_preview_match_tag
            else:
                updated_scene_generation.pop("registry_match_tag", None)

            _update_scene_generation_for_player(event.player_id, updated_scene_generation)
        except Exception as exc:
            logger.warning(
                "registry_preview_capture_failed",
                extra={
                    "player_id": event.player_id,
                    "event_type": normalized_event_type or "talk",
                    "error": str(exc),
                },
            )

    result = {"status": "ok", "result": response}
    if talk_text:
        result["player_input"] = {
            "text": talk_text,
            "event_type": normalized_event_type or "talk",
        }
        result["intent_received"] = bool(intent_summary)
        if isinstance(intent_summary, dict) and intent_summary:
            result["intent"] = dict(intent_summary)
        result["registry_resources"] = dict(registry_preview_resources)
        result["registry_bindings_count"] = len(registry_preview_bindings)
        if registry_preview_match_tag:
            result["registry_match_tag"] = registry_preview_match_tag
    if isinstance(response, dict):
        story_engine.apply_quest_updates(event.player_id, response)
        if response.get("world_patch"):
            result["world_patch"] = response["world_patch"]
        if response.get("nodes"):
            result["nodes"] = response["nodes"]
        if response.get("completed_tasks"):
            result["completed_tasks"] = response["completed_tasks"]
        if response.get("milestones"):
            result["milestones"] = response["milestones"]
        if response.get("commands"):
            result["commands"] = response["commands"]
        if response.get("active_tasks"):
            result["active_tasks"] = response["active_tasks"]
        if response.get("memory_flags"):
            result["memory_flags"] = response["memory_flags"]
        for key in ("task_titles", "milestone_names", "remaining_total", "active_count", "milestone_count"):
            if key in response:
                result[key] = response[key]

    scene_generation_before = _scene_generation_for_player(event.player_id)
    gate_seed = _planned_rule_event_gate_seed(event)
    gate_result = _evaluate_generation_policy_gate(
        scene_generation_before,
        event_type=event.event_type,
        payload=payload_dict,
        deterministic_seed=gate_seed,
    )
    generation_allowed = bool(gate_result.get("allowed"))
    scene_generation_applied = False

    if not generation_allowed:
        result["msg"] = "Scene generation skipped by policy gate."
        logger.info(
            "generation_policy_gate_blocked",
            extra={
                "player_id": event.player_id,
                "event_type": event.event_type,
                "reason": gate_result.get("reason"),
                "next_available_in": gate_result.get("next_available_in"),
            },
        )

    interaction_tx: Dict[str, Any] | None = None
    interaction_tx_error: str | None = None
    if generation_allowed and _as_bool_env("DRIFT_ENABLE_PLUGIN_TRNG", default=True):
        try:
            interaction_tx = _ingest_rule_event_via_trng(event)
        except Exception as exc:
            interaction_tx_error = str(exc)
            logger.warning(
                "plugin_rule_event_trng_ingest_failed",
                extra={
                    "player_id": event.player_id,
                    "event_type": event.event_type,
                    "error": interaction_tx_error,
                },
            )

    scene_evolution: Dict[str, Any] | None = None
    scene_evolution_error: str | None = None
    if generation_allowed:
        try:
            from app.api.story_api import evolve_scene_for_rule_event, merge_world_patches

            scene_evolution = evolve_scene_for_rule_event(
                player_id=event.player_id,
                event_type=event.event_type,
                payload=payload_dict,
            )

            if isinstance(scene_evolution, dict):
                scene_patch = scene_evolution.get("scene_world_patch")
                if isinstance(scene_patch, dict) and scene_patch:
                    existing_patch = result.get("world_patch") if isinstance(result.get("world_patch"), dict) else {}
                    result["world_patch"] = merge_world_patches(existing_patch, scene_patch)
                    scene_generation_applied = True

                scene_diff = scene_evolution.get("scene_diff")
                if isinstance(scene_diff, dict):
                    result["scene_diff"] = scene_diff
        except Exception as exc:
            scene_evolution_error = str(exc)
            logger.warning(
                "scene_evolution_apply_failed",
                extra={
                    "player_id": event.player_id,
                    "event_type": event.event_type,
                    "error": scene_evolution_error,
                },
            )

    talk_bootstrap: Dict[str, Any] | None = None
    talk_bootstrap_error: str | None = None
    try:
        talk_bootstrap = _bootstrap_scene_generation_for_talk_event(
            event.player_id,
            event.event_type,
            payload_dict,
        )
    except Exception as exc:
        talk_bootstrap_error = str(exc)
        logger.warning(
            "talk_scene_bootstrap_failed",
            extra={
                "player_id": event.player_id,
                "event_type": event.event_type,
                "error": talk_bootstrap_error,
            },
        )

    talk_scene_bridge: Dict[str, Any] | None = None
    talk_scene_bridge_error: str | None = None
    if generation_allowed and normalized_event_type in {"talk", "chat"} and talk_text:
        try:
            from app.api.story_api import (
                _scene_event_plan_to_world_patch,
                _scene_meta_payload,
                _selection_context_from_scene_generation,
                build_scene_events,
                merge_world_patches,
            )

            latest_scene_generation = _scene_generation_for_player(event.player_id) or {}
            scene_theme = str((intent_summary or {}).get("scene_theme") or "").strip()
            if not scene_theme:
                scene_theme = str(latest_scene_generation.get("scene_theme") or "").strip()
            if not scene_theme:
                scene_theme = str(os.environ.get("DRIFT_DEFAULT_SCENE_THEME", "camp") or "camp").strip() or "camp"

            scene_hint = str((intent_summary or {}).get("scene_hint") or talk_text).strip() or talk_text
            player_position = _location_from_event_payload(payload_dict)

            selection_context = _selection_context_from_scene_generation(latest_scene_generation)
            registry_resources, registry_match_tag, registry_bindings = _registry_resources_for_scene_hint(
                event.player_id,
                scene_hint,
            )
            if registry_match_tag:
                selection_context = dict(selection_context or {})
                selection_context["registry_match_tag"] = registry_match_tag

            scene_output = build_scene_events(
                player_id=event.player_id,
                scene_theme=scene_theme,
                scene_hint=scene_hint,
                text=talk_text,
                anchor=None,
                player_position=player_position,
                selection_context=selection_context if selection_context else None,
                registry_resources=registry_resources,
            )

            scene_patch = _scene_event_plan_to_world_patch(scene_output)
            scene_patch = _apply_registry_override_to_scene_patch(scene_patch, registry_resources)

            if isinstance(scene_patch, dict) and scene_patch:
                bridge_patch = dict(scene_patch)
                patch_meta = bridge_patch.get("meta") if isinstance(bridge_patch.get("meta"), dict) else {}
                patch_meta["registry_resources"] = dict(registry_resources)
                patch_meta["registry_match_tag"] = registry_match_tag
                patch_meta["registry_bindings_count"] = len(registry_bindings)
                patch_meta["talk_bridge"] = True
                bridge_patch["meta"] = patch_meta
                bridge_patch.setdefault("type", "spawnfragment")

                existing_patch = result.get("world_patch") if isinstance(result.get("world_patch"), dict) else {}
                merged_patch = merge_world_patches(existing_patch, bridge_patch)
                merged_patch.setdefault("type", "spawnfragment")
                merged_meta = merged_patch.get("meta") if isinstance(merged_patch.get("meta"), dict) else {}
                merged_meta.update(patch_meta)
                merged_patch["meta"] = merged_meta
                result["world_patch"] = merged_patch
                scene_generation_applied = True

            if isinstance(scene_output, dict):
                updated_scene_generation = dict(latest_scene_generation)
                updated_scene_generation.update(_scene_meta_payload(scene_output))
                updated_scene_generation["last_player_input"] = {
                    "event_type": normalized_event_type or "talk",
                    "text": talk_text,
                    "at_ms": _now_ms(),
                }
                if isinstance(intent_summary, dict) and intent_summary:
                    updated_scene_generation["last_intent"] = dict(intent_summary)
                _update_scene_generation_for_player(event.player_id, updated_scene_generation)

            result["registry_resources"] = dict(registry_resources)
            result["registry_match_tag"] = registry_match_tag
            talk_scene_bridge = {
                "scene_hint": scene_hint,
                "scene_theme": scene_theme,
                "registry_bindings_count": len(registry_bindings),
                "event_count": len(scene_output.get("event_plan") or []) if isinstance(scene_output, dict) else 0,
                "fragment_count": len(((scene_output.get("scene_plan") or {}).get("fragments") or [])) if isinstance(scene_output, dict) else 0,
                "has_world_patch": bool(result.get("world_patch")),
            }
        except Exception as exc:
            talk_scene_bridge_error = str(exc)
            logger.warning(
                "talk_spawnfragment_bridge_failed",
                extra={
                    "player_id": event.player_id,
                    "event_type": event.event_type,
                    "error": talk_scene_bridge_error,
                },
            )

    gate_record_error: str | None = None
    try:
        latest_scene_generation = _scene_generation_for_player(event.player_id)
        recorded_generation = _record_generation_policy_gate(
            event.player_id,
            latest_scene_generation,
            gate_result,
            generated=scene_generation_applied,
        )
        result.update(_generation_policy_observability_payload(recorded_generation))
    except Exception as exc:
        gate_record_error = str(exc)
        logger.warning(
            "generation_policy_gate_record_failed",
            extra={
                "player_id": event.player_id,
                "event_type": event.event_type,
                "error": gate_record_error,
            },
        )
        result.update(_generation_policy_observability_payload(_scene_generation_for_player(event.player_id)))

    if _as_bool_env("DRIFT_DEBUG_TRACE", default=False):
        gate_debug = dict(gate_result)
        gate_debug.pop("_recent_timestamps", None)
        result["generation_policy_gate_eval"] = gate_debug
        if intent_error:
            result["intent_received_error"] = intent_error
        if gate_record_error:
            result["generation_policy_gate_record_error"] = gate_record_error
        if interaction_tx is not None:
            result["interaction_transaction"] = interaction_tx
        if interaction_tx_error:
            result["interaction_transaction_error"] = interaction_tx_error
        if scene_evolution is not None:
            result["scene_evolution"] = scene_evolution
        if scene_evolution_error:
            result["scene_evolution_error"] = scene_evolution_error
        if talk_bootstrap is not None:
            result["talk_scene_bootstrap"] = talk_bootstrap
        if talk_bootstrap_error:
            result["talk_scene_bootstrap_error"] = talk_bootstrap_error
        if talk_scene_bridge is not None:
            result["talk_scene_bridge"] = talk_scene_bridge
        if talk_scene_bridge_error:
            result["talk_scene_bridge_error"] = talk_scene_bridge_error

    if talk_text:
        try:
            scene_generation_snapshot = _scene_generation_for_player(event.player_id) or {}
            updated_scene_generation = dict(scene_generation_snapshot)
            updated_scene_generation["last_rule_event_result"] = {
                "event_type": normalized_event_type or "talk",
                "player_input": {
                    "text": talk_text,
                    "event_type": normalized_event_type or "talk",
                },
                "intent_received": bool(intent_summary),
                "intent": dict(intent_summary) if isinstance(intent_summary, dict) and intent_summary else None,
                "registry_resources": dict(result.get("registry_resources") or {}),
                "registry_match_tag": result.get("registry_match_tag"),
                "world_patch": dict(result.get("world_patch")) if isinstance(result.get("world_patch"), dict) else None,
                "at_ms": _now_ms(),
            }
            _update_scene_generation_for_player(event.player_id, updated_scene_generation)
        except Exception as exc:
            logger.warning(
                "rule_event_result_persist_failed",
                extra={
                    "player_id": event.player_id,
                    "event_type": normalized_event_type or "talk",
                    "error": str(exc),
                },
            )
    return result


@router.get("/story/{player_id}/memory")
def story_memory(player_id: str):
    flags = story_engine.get_player_memory(player_id)
    return {
        "status": "ok",
        "player_id": player_id,
        "flags": flags,
    }


@router.get("/story/{player_id}/emotional-weather")
def story_emotional_weather(player_id: str):
    summary = story_engine.get_emotional_profile(player_id)
    return {
        "status": "ok",
        "player_id": player_id,
        "emotional_state": summary or None,
    }


@router.get("/story/{player_id}/recommendations")
def story_recommendations(player_id: str, current_level: Optional[str] = None, limit: int = 3):
    recs = story_engine.get_level_recommendations(player_id, current_level_id=current_level, limit=limit)
    return {
        "status": "ok",
        "recommendations": recs,
    }


@router.get("/story/{player_id}/debug/tasks")
def story_debug_tasks(player_id: str, request: Request, token: Optional[str] = None):
    expected_token = os.environ.get("DRIFT_TASK_DEBUG_TOKEN")
    if expected_token:
        provided = token or request.headers.get("X-Debug-Token")
        if provided != expected_token:
            raise HTTPException(status_code=403, detail="Task debug access denied.")

    recent_reports = _recent_reports_for_player(player_id)
    last_report = recent_reports[0] if recent_reports else None
    fallback_state = fallback_state_by_player.get(player_id, {})
    scene_generation = _scene_generation_for_player(player_id)
    prediction = None
    scene_candidate_scores = scene_generation.get("candidate_scores") if isinstance(scene_generation, dict) else None
    if not isinstance(scene_generation, dict) or not isinstance(scene_candidate_scores, list) or not scene_candidate_scores:
        prediction = _predict_scene_payload_for_player(player_id, scene_generation=scene_generation)

    snapshot = quest_runtime.get_debug_snapshot(player_id)
    recent_rule_events_fallback: List[Dict[str, Any]] = []
    recent_fetch = getattr(quest_runtime, "get_recent_rule_events", None)
    if callable(recent_fetch):
        try:
            rows = recent_fetch(player_id)
            if isinstance(rows, list):
                recent_rule_events_fallback = [row for row in rows if isinstance(row, dict)]
        except Exception:
            recent_rule_events_fallback = []

    fallback_last_rule_event = recent_rule_events_fallback[-1] if recent_rule_events_fallback else None

    narrative_state = _narrative_state_for_player(
        player_id,
        snapshot=snapshot,
        scene_generation=scene_generation,
    )
    asset_observability = _asset_registry_observability_payload(scene_generation)
    policy_observability = _generation_policy_observability_payload(scene_generation)
    pack_observability = _enabled_packs_payload()
    if not snapshot:
        result = {
            "status": "error",
            "msg": "No active task state for player.",
            "recent_apply_reports": recent_reports,
            "last_apply_report": last_report,
            "scene_generation": scene_generation,
            "last_fallback_flag": fallback_state.get("last_fallback_flag", False),
            "last_fallback_reason": fallback_state.get("last_fallback_reason", "none"),
            "last_fallback_level_id": fallback_state.get("last_fallback_level_id"),
            "last_fallback_inject_version": fallback_state.get("last_fallback_inject_version"),
            "last_fallback_at": fallback_state.get("last_fallback_at"),
            "recent_rule_events": recent_rule_events_fallback,
            "last_rule_event": fallback_last_rule_event,
        }
        if isinstance(prediction, dict):
            result["prediction"] = prediction
        result.update(_narrative_fields_payload(narrative_state))
        result.update(policy_observability)
        result.update(asset_observability)
        result.update(pack_observability)
        return result

    payload: Dict[str, Any] = {"status": "ok"}
    payload.update(snapshot)
    payload["recent_apply_reports"] = recent_reports
    payload["last_apply_report"] = last_report
    payload["scene_generation"] = scene_generation
    payload["last_fallback_flag"] = fallback_state.get("last_fallback_flag", False)
    payload["last_fallback_reason"] = fallback_state.get("last_fallback_reason", "none")
    payload["last_fallback_level_id"] = fallback_state.get("last_fallback_level_id")
    payload["last_fallback_inject_version"] = fallback_state.get("last_fallback_inject_version")
    payload["last_fallback_at"] = fallback_state.get("last_fallback_at")
    if isinstance(prediction, dict):
        payload["prediction"] = prediction
    payload.update(_narrative_fields_payload(narrative_state))
    payload.update(policy_observability)
    payload.update(asset_observability)
    payload.update(pack_observability)
    return payload


@router.get("/story/{player_id}/predict_scene")
def story_predict_scene(player_id: str, request: Request, token: Optional[str] = None):
    expected_token = os.environ.get("DRIFT_TASK_DEBUG_TOKEN")
    if expected_token:
        provided = token or request.headers.get("X-Debug-Token")
        if provided != expected_token:
            raise HTTPException(status_code=403, detail="Task debug access denied.")

    normalized_player = str(player_id or "").strip()
    if not normalized_player:
        raise HTTPException(status_code=400, detail="player_id is required")

    scene_generation = _scene_generation_for_player(normalized_player)
    prediction = _predict_scene_payload_for_player(normalized_player, scene_generation=scene_generation)

    return {
        "status": "ok",
        "player_id": normalized_player,
        "prediction": prediction,
    }


@router.get("/story/{player_id}/explain_scene")
def story_explain_scene(player_id: str, request: Request, token: Optional[str] = None):
    expected_token = os.environ.get("DRIFT_TASK_DEBUG_TOKEN")
    if expected_token:
        provided = token or request.headers.get("X-Debug-Token")
        if provided != expected_token:
            raise HTTPException(status_code=403, detail="Task debug access denied.")

    normalized_player = str(player_id or "").strip()
    if not normalized_player:
        raise HTTPException(status_code=400, detail="player_id is required")

    scene_generation = _scene_generation_for_player(normalized_player)
    explanation = _scene_explanation_payload(normalized_player, scene_generation=scene_generation)

    return {
        "status": "ok",
        "player_id": normalized_player,
        "semantic": explanation.get("semantic"),
        "resources": explanation.get("resources"),
        "selected_root": explanation.get("selected_root"),
        "reason": explanation.get("reason"),
        "influence": explanation.get("influence"),
        "history": explanation.get("history"),
        "explanation": explanation,
    }


@router.post("/story/{player_id}/narrative/choose")
def story_narrative_choose(player_id: str, payload: Optional[NarrativeChooseRequest] = None):
    normalized_player = str(player_id or "").strip()
    if not normalized_player:
        raise HTTPException(status_code=400, detail="player_id is required")

    level = _scene_level_for_player(normalized_player)
    if level is None:
        raise HTTPException(status_code=404, detail="No active story level for player.")

    request_payload = payload or NarrativeChooseRequest()
    mode = str(request_payload.mode or "auto_best").strip().lower() or "auto_best"
    transition_id = _normalize_token(request_payload.transition_id)

    snapshot = quest_runtime.get_debug_snapshot(normalized_player)
    scene_generation = _scene_generation_for_player(normalized_player) or {}
    story_snapshot = story_engine.get_public_state(normalized_player)
    narrative_state = _narrative_state_for_player(
        normalized_player,
        snapshot=snapshot,
        scene_generation=scene_generation,
        story_snapshot=story_snapshot if isinstance(story_snapshot, dict) else None,
    )

    level_state = snapshot.get("level_state") if isinstance(snapshot, dict) and isinstance(snapshot.get("level_state"), dict) else None
    recent_rule_events = snapshot.get("recent_rule_events") if isinstance(snapshot, dict) and isinstance(snapshot.get("recent_rule_events"), list) else None

    from app.core.story.narrative_decision import choose_transition

    decision_result = choose_transition(
        normalized_player,
        mode=mode,
        transition_id=transition_id or None,
        narrative_state=narrative_state,
        scene_generation=scene_generation,
        level_state=level_state,
        recent_rule_events=recent_rule_events,
    )

    decision_payload = decision_result.get("decision") if isinstance(decision_result.get("decision"), dict) else {}
    updated_narrative_state = decision_result.get("narrative_state") if isinstance(decision_result.get("narrative_state"), dict) else dict(narrative_state)
    transition_log_entry = decision_result.get("transition_log_entry") if isinstance(decision_result.get("transition_log_entry"), dict) else None
    candidate_scores = decision_result.get("candidate_scores") if isinstance(decision_result.get("candidate_scores"), list) else []

    updated_scene_generation = dict(scene_generation)
    updated_scene_generation["narrative_state"] = dict(updated_narrative_state)
    updated_scene_generation["last_decision"] = dict(decision_payload)
    _update_scene_generation_for_player(normalized_player, updated_scene_generation)

    logger.info(
        "story_narrative_choose",
        extra={
            "player_id": normalized_player,
            "mode": mode,
            "transition_id": transition_id or None,
            "chosen_transition": decision_payload.get("chosen_transition") if isinstance(decision_payload, dict) else None,
            "target_node": decision_payload.get("target_node") if isinstance(decision_payload, dict) else None,
        },
    )

    return {
        "status": "ok",
        "player_id": normalized_player,
        "mode": mode,
        "narrative_state": dict(updated_narrative_state),
        "current_node": updated_narrative_state.get("current_node"),
        "transition_candidates": list(updated_narrative_state.get("transition_candidates") or []),
        "blocked_by": list(updated_narrative_state.get("blocked_by") or []),
        "narrative_decision": dict(decision_payload),
        "last_decision": dict(decision_payload),
        "transition_log_entry": transition_log_entry,
        "candidate_scores": list(candidate_scores),
        "world_patch": None,
    }


@router.post("/story/{player_id}/spawnfragment")
def story_spawn_fragment(player_id: str, payload: Optional[SpawnFragmentRequest] = None):
    normalized_player = str(player_id or "").strip()
    if not normalized_player:
        raise HTTPException(status_code=400, detail="player_id is required")

    request_payload = payload or SpawnFragmentRequest()
    explicit_scene_theme = isinstance(request_payload.scene_theme, str) and bool(request_payload.scene_theme.strip())
    scene_generation = _scene_generation_for_player(normalized_player) or {}
    auto_bootstrap = None

    if not scene_generation:
        prediction = _predict_scene_payload_for_player(normalized_player, scene_generation=None)
        bootstrap_scene_generation, bootstrap_meta = _auto_bootstrap_scene_generation_for_player(normalized_player, prediction)
        if bootstrap_scene_generation:
            scene_generation = dict(bootstrap_scene_generation)
        if isinstance(bootstrap_meta, dict):
            auto_bootstrap = dict(bootstrap_meta)

    requested_theme = request_payload.scene_theme
    if not isinstance(requested_theme, str) or not requested_theme.strip():
        requested_theme = scene_generation.get("scene_theme")
    if not isinstance(requested_theme, str) or not requested_theme.strip():
        requested_theme = os.environ.get("DRIFT_DEFAULT_SCENE_THEME", "camp")
    scene_theme = str(requested_theme or "camp").strip() or "camp"

    requested_hint = request_payload.scene_hint
    if not isinstance(requested_hint, str) or not requested_hint.strip():
        requested_hint = scene_generation.get("scene_hint")
    scene_hint = str(requested_hint).strip() if isinstance(requested_hint, str) and requested_hint.strip() else None

    if not explicit_scene_theme:
        prediction_for_theme = _predict_scene_payload_for_player(normalized_player, scene_generation=scene_generation)
        theme_override = _scene_theme_override_from_prediction(prediction_for_theme, current_scene_theme=scene_theme)
        if isinstance(theme_override, str) and theme_override.strip():
            scene_theme = theme_override
            if isinstance(scene_generation, dict):
                scene_generation = dict(scene_generation)
                scene_generation["scene_theme"] = scene_theme

    anchor = request_payload.anchor
    if isinstance(anchor, str) and anchor.strip():
        anchor = anchor.strip()
    else:
        anchor = None

    player_position = request_payload.player_position if isinstance(request_payload.player_position, dict) else None
    request_text = scene_hint or f"spawn fragment {scene_theme}"

    gate_payload: Dict[str, Any] = {}
    if isinstance(player_position, dict):
        gate_payload["player_position"] = dict(player_position)

    gate_seed = _core_build_generation_seed(
        player_id=normalized_player,
        event_type="spawnfragment",
        payload={
            "scene_theme": scene_theme,
            "scene_hint": scene_hint,
            "anchor": anchor,
            "player_position": player_position if isinstance(player_position, dict) else {},
        },
    )

    gate_result = _evaluate_generation_policy_gate(
        scene_generation,
        event_type="spawnfragment",
        payload=gate_payload,
        deterministic_seed=gate_seed,
    )
    if not bool(gate_result.get("allowed")):
        recorded_generation = _record_generation_policy_gate(
            normalized_player,
            scene_generation,
            gate_result,
            generated=False,
        )
        logger.info(
            "story_spawn_fragment_skipped_by_policy",
            extra={
                "player_id": normalized_player,
                "scene_theme": scene_theme,
                "reason": gate_result.get("reason"),
                "next_available_in": gate_result.get("next_available_in"),
            },
        )
        response_payload = {
            "status": "ok",
            "msg": "Scene generation skipped by policy gate.",
            "player_id": normalized_player,
            "scene_theme": scene_theme,
            "scene_hint": scene_hint,
            "fragment_count": 0,
            "event_count": 0,
            "scene": {},
            "world_patch": {},
            "auto_bootstrap": auto_bootstrap,
        }
        response_payload.update(_generation_policy_observability_payload(recorded_generation))
        return response_payload

    from app.api.story_api import build_scene_events, _scene_event_plan_to_world_patch, _scene_meta_payload, _selection_context_from_scene_generation

    selection_context = _selection_context_from_scene_generation(scene_generation)
    registry_resources, registry_match_tag, registry_bindings = _registry_resources_for_scene_hint(normalized_player, scene_hint)
    if registry_match_tag:
        selection_context = dict(selection_context or {})
        selection_context["registry_match_tag"] = registry_match_tag

    scene_output = build_scene_events(
        player_id=normalized_player,
        scene_theme=scene_theme,
        scene_hint=scene_hint,
        text=request_text,
        anchor=anchor,
        player_position=player_position,
        selection_context=selection_context if selection_context else None,
        registry_resources=registry_resources,
    )
    scene_patch = _scene_event_plan_to_world_patch(scene_output)
    scene_patch = _apply_registry_override_to_scene_patch(scene_patch, registry_resources)

    if isinstance(scene_output, dict) and registry_resources:
        scoring_debug = scene_output.get("scoring_debug") if isinstance(scene_output.get("scoring_debug"), dict) else {}
        scoring_payload = dict(scoring_debug)
        reasons_payload = scoring_payload.get("reasons") if isinstance(scoring_payload.get("reasons"), dict) else {}
        reasons = dict(reasons_payload)
        reasons["registry_world_patch_override"] = True
        reasons["registry_primary_resource"] = _primary_registry_resource_id(registry_resources)
        scoring_payload["reasons"] = reasons
        scene_output["scoring_debug"] = scoring_payload

    if isinstance(scene_output, dict):
        updated_scene_generation = dict(scene_generation)
        updated_scene_generation.update(_scene_meta_payload(scene_output))
        _update_scene_generation_for_player(normalized_player, updated_scene_generation)

    scene_plan = scene_output.get("scene_plan") if isinstance(scene_output.get("scene_plan"), dict) else {}
    event_plan = scene_output.get("event_plan") if isinstance(scene_output.get("event_plan"), list) else []
    fragments = scene_plan.get("fragments") if isinstance(scene_plan.get("fragments"), list) else []

    world_patch = dict(scene_patch) if isinstance(scene_patch, dict) else {}
    if world_patch:
        patch_meta = world_patch.get("meta") if isinstance(world_patch.get("meta"), dict) else {}
        patch_meta["registry_resources"] = dict(registry_resources)
        patch_meta["registry_match_tag"] = registry_match_tag
        patch_meta["registry_bindings_count"] = len(registry_bindings)
        world_patch["meta"] = patch_meta
        world_patch.setdefault("type", "spawnfragment")
    has_patch = bool(world_patch)

    policy_observability: Dict[str, Any]
    gate_record_error: str | None = None
    try:
        latest_scene_generation = _scene_generation_for_player(normalized_player)
        recorded_generation = _record_generation_policy_gate(
            normalized_player,
            latest_scene_generation if isinstance(latest_scene_generation, dict) else scene_generation,
            gate_result,
            generated=has_patch,
        )
        policy_observability = _generation_policy_observability_payload(recorded_generation)
    except Exception as exc:
        gate_record_error = str(exc)
        logger.warning(
            "story_spawn_fragment_policy_record_failed",
            extra={
                "player_id": normalized_player,
                "error": gate_record_error,
            },
        )
        policy_observability = _generation_policy_observability_payload(_scene_generation_for_player(normalized_player))

    logger.info(
        "story_spawn_fragment",
        extra={
            "player_id": normalized_player,
            "scene_theme": scene_theme,
            "fragment_count": len(fragments),
            "event_count": len(event_plan),
            "has_world_patch": has_patch,
            "auto_bootstrap": bool(auto_bootstrap and auto_bootstrap.get("triggered")),
            "generation_allowed": bool(gate_result.get("allowed")),
            "generation_reason": gate_result.get("reason"),
        },
    )

    response_payload = {
        "status": "ok",
        "msg": "Scene fragment generated." if has_patch else "Scene fragment generated (no executable patch).",
        "player_id": normalized_player,
        "scene_theme": scene_theme,
        "scene_hint": scene_hint,
        "fragment_count": len(fragments),
        "event_count": len(event_plan),
        "scene": scene_output,
        "world_patch": world_patch,
        "auto_bootstrap": auto_bootstrap,
        "registry_resources": dict(registry_resources),
        "registry_bindings": list(registry_bindings),
        "registry_match_tag": registry_match_tag,
    }
    response_payload.update(policy_observability)
    if gate_record_error and _as_bool_env("DRIFT_DEBUG_TRACE", default=False):
        response_payload["generation_policy_gate_record_error"] = gate_record_error
    return response_payload


@router.post("/story/{player_id}/reset")
def story_reset(player_id: str, payload: Optional[StoryResetRequest] = None):
    normalized_player = str(player_id or "").strip()
    if not normalized_player:
        raise HTTPException(status_code=400, detail="player_id is required")

    request_payload = payload or StoryResetRequest()

    reset_summary = story_engine.reset_player_runtime(
        normalized_player,
        clear_memory=bool(request_payload.clear_memory),
        clear_history=bool(request_payload.clear_history),
        clear_persisted_state=bool(request_payload.clear_persisted_state),
        clear_inventory=bool(request_payload.clear_inventory),
    )

    cleared_scene_state = 0
    try:
        from app.core.narrative.scene_state_store import scene_state_store

        cleared_scene_state = scene_state_store.delete_player_states(normalized_player)
    except Exception:
        cleared_scene_state = 0

    if isinstance(reset_summary, dict):
        reset_summary["cleared_scene_state"] = int(cleared_scene_state)

    apply_reports_by_player.pop(normalized_player, None)
    fallback_state_by_player.pop(normalized_player, None)
    semantic_bootstrap_state_by_player.pop(normalized_player, None)

    logger.info(
        "story_reset",
        extra={
            "player_id": normalized_player,
            "clear_memory": bool(request_payload.clear_memory),
            "clear_history": bool(request_payload.clear_history),
            "clear_persisted_state": bool(request_payload.clear_persisted_state),
            "clear_inventory": bool(request_payload.clear_inventory),
        },
    )

    return {
        "status": "ok",
        "msg": "Story runtime reset completed.",
        "player_id": normalized_player,
        "reset": reset_summary,
    }


@router.get("/story/{player_id}/quest-log")
def story_quest_log(player_id: str):
    snapshot = quest_runtime.get_active_tasks_snapshot(player_id)
    response: Dict[str, Any] = {
        "status": "ok",
        "active_tasks": snapshot,
    }
    if snapshot:
        for key in ("task_titles", "milestone_names", "remaining_total", "active_count", "milestone_count"):
            if key in snapshot:
                response[key] = snapshot[key]
    return response


@router.post("/apply/report")
def apply_report(report: ApplyReportInput):
    merged = _upsert_apply_report(report)

    logger.info(
        "world_apply_report",
        extra={
            "player_id": report.player_id,
            "build_id": report.build_id,
            "status": report.status,
            "failure_code": report.failure_code,
            "executed": report.executed,
            "failed": report.failed,
            "duration_ms": report.duration_ms,
        },
    )

    return {
        "status": "ok",
        "accepted": True,
        "player_id": report.player_id,
        "build_id": report.build_id,
        "report_count": merged.get("report_count", 1),
        "last_status": merged.get("last_status"),
        "status_rank": merged.get("status_rank"),
    }
