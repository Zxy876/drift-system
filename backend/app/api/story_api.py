# backend/app/api/story_api.py

from fastapi import APIRouter, HTTPException
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from typing import Dict, Any, Optional, List
import os
import json
import re
import time

from app.core.story.story_loader import (
    list_levels,
    load_level,
    DATA_DIR,          # ⭐ 使用 story_loader 的同一个目录
)
from app.core.story.story_engine import story_engine
from app.core.scene.scene_orchestrator_v1 import compose_scene_and_structure
from app.core.scene.scene_orchestrator_v2 import compose_scene_and_structure_v2
from app.core.executor.plugin_payload_v1 import build_plugin_payload_v1
from app.core.executor.plugin_payload_v2 import build_plugin_payload_v2_with_trace, PayloadV2BuildError
from app.core.runtime.resource_canonical import normalize_inventory_resource_token
from app.core.trng.graph_state import GraphState, InternalState
from app.core.trng.transaction import TransactionShell

router = APIRouter(prefix="/story")


class PayloadV1BuildError(Exception):
    def __init__(self, failure_code: str, debug_payload: dict | None = None):
        super().__init__(failure_code)
        self.failure_code = failure_code
        self.debug_payload = debug_payload or {}


class PayloadV2BuildErrorWrapper(Exception):
    def __init__(self, failure_code: str, debug_payload: dict | None = None):
        super().__init__(failure_code)
        self.failure_code = failure_code
        self.debug_payload = debug_payload or {}


class StoryTransactionError(Exception):
    pass


def _story_tx_events_for_inject(*, text: str, payload: dict, anchor: str | None) -> list[dict]:
    payload_hash = payload.get("hash") if isinstance(payload, dict) else {}
    final_hash = ""
    if isinstance(payload_hash, dict):
        final_hash = str(payload_hash.get("final_commands") or payload_hash.get("merged_blocks") or "")
    if not final_hash and isinstance(payload, dict):
        final_hash = str(payload.get("final_commands_hash_v2") or "")

    version = str(payload.get("version") or payload.get("payload_version") or "payload_unknown")
    events = [
        {
            "event_id": "scene_generation",
            "type": "input",
            "text": str(text or "scene_generation"),
        }
    ]

    if final_hash:
        events.append(
            {
                "event_id": "resource_bind",
                "type": "input",
                "text": f"{version}:{final_hash}",
            }
        )

    if isinstance(anchor, str) and anchor.strip():
        events.append(
            {
                "event_id": "anchor_select",
                "type": "input",
                "text": anchor.strip(),
            }
        )

    return events


def _normalize_scene_theme(raw_theme: str | None) -> str | None:
    if raw_theme is None:
        return None
    if not isinstance(raw_theme, str):
        return None
    normalized = raw_theme.strip()
    return normalized or None


def _normalize_scene_hint(raw_hint: str | None) -> str | None:
    if raw_hint is None:
        return None
    if not isinstance(raw_hint, str):
        return None
    normalized = raw_hint.strip()
    return normalized or None


def _coerce_positive_int(value: Any, default: int = 1) -> int:
    try:
        parsed = int(float(value))
    except (TypeError, ValueError):
        parsed = int(default)
    return parsed if parsed > 0 else int(default)


def _normalize_collect_resource_token(raw_value: Any) -> str:
    return normalize_inventory_resource_token(raw_value)


def _to_event_dict(row: Dict[str, Any]) -> Dict[str, Any]:
    if isinstance(row.get("event"), dict):
        return row.get("event")
    return row if isinstance(row, dict) else {}


def _collect_payload_candidates(row: Dict[str, Any]) -> list[Dict[str, Any]]:
    candidates: list[Dict[str, Any]] = []
    event_payload = _to_event_dict(row)
    raw_payload = row.get("raw_payload") if isinstance(row.get("raw_payload"), dict) else {}

    for candidate in (
        raw_payload.get("payload"),
        event_payload.get("payload"),
        event_payload.get("meta"),
        row.get("payload"),
        row.get("meta"),
    ):
        if isinstance(candidate, dict):
            candidates.append(candidate)

    return candidates


def _resolve_rule_event_type(row: Dict[str, Any]) -> str:
    event_payload = _to_event_dict(row)
    raw_payload = row.get("raw_payload") if isinstance(row.get("raw_payload"), dict) else {}

    for candidate in (
        raw_payload.get("event_type"),
        event_payload.get("event_type"),
        row.get("event_type"),
        event_payload.get("type"),
        row.get("type"),
    ):
        normalized = str(candidate or "").strip().lower()
        if normalized:
            return normalized

    return ""


def _collect_quest_event_tokens(row: Dict[str, Any]) -> list[str]:
    tokens: list[str] = []
    event_payload = _to_event_dict(row)
    raw_payload = row.get("raw_payload") if isinstance(row.get("raw_payload"), dict) else {}
    payload_candidates = _collect_payload_candidates(row)

    for candidate in (
        row.get("quest_event"),
        event_payload.get("quest_event"),
        raw_payload.get("quest_event"),
    ):
        normalized = str(candidate or "").strip().lower()
        if normalized:
            tokens.append(normalized)

    for payload in payload_candidates:
        normalized = str(payload.get("quest_event") or "").strip().lower()
        if normalized:
            tokens.append(normalized)

    return tokens


def _event_row_timestamp_ms(row: Dict[str, Any]) -> int | None:
    event_payload = _to_event_dict(row)
    raw_payload = row.get("raw_payload") if isinstance(row.get("raw_payload"), dict) else {}

    candidates = (
        row.get("timestamp_ms"),
        event_payload.get("timestamp_ms"),
        raw_payload.get("timestamp_ms"),
        row.get("timestamp"),
        event_payload.get("timestamp"),
        raw_payload.get("timestamp"),
    )

    for candidate in candidates:
        if candidate is None:
            continue
        try:
            numeric = float(candidate)
        except (TypeError, ValueError):
            continue
        if numeric <= 0:
            continue
        if numeric < 10_000_000_000:
            numeric *= 1000.0
        return int(numeric)

    return None


def _coerce_float(value: Any) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _location_payload_to_anchor_origin(raw_location: Any) -> Dict[str, Any] | None:
    if not isinstance(raw_location, dict):
        return None

    raw_x = raw_location.get("x", raw_location.get("base_x"))
    raw_y = raw_location.get("y", raw_location.get("base_y"))
    raw_z = raw_location.get("z", raw_location.get("base_z"))

    x = _coerce_float(raw_x)
    y = _coerce_float(raw_y)
    z = _coerce_float(raw_z)
    if x is None or y is None or z is None:
        return None

    world = str(raw_location.get("world") or "").strip() or None

    return {
        "x": x,
        "y": y,
        "z": z,
        "world": world,
    }


def _origin_from_anchor_location(raw_location: Any, *, fallback_origin: Dict[str, Any], anchor_mode: str) -> Dict[str, Any] | None:
    parsed = _location_payload_to_anchor_origin(raw_location)
    if not parsed:
        return None

    return {
        "base_x": int(round(float(parsed["x"]))),
        "base_y": int(round(float(parsed["y"]))),
        "base_z": int(round(float(parsed["z"]))),
        "anchor_mode": anchor_mode,
        "world": str(parsed.get("world") or fallback_origin.get("world") or os.environ.get("DRIFT_SCENE_WORLD", "world")),
    }


def _position_from_anchor_origin(anchor_origin: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "world": str(anchor_origin.get("world") or os.environ.get("DRIFT_SCENE_WORLD", "world")),
        "x": float(anchor_origin.get("base_x", anchor_origin.get("x", 0.0))),
        "y": float(anchor_origin.get("base_y", anchor_origin.get("y", 64.0))),
        "z": float(anchor_origin.get("base_z", anchor_origin.get("z", 0.0))),
    }


def _extract_location_from_rule_event(row: Dict[str, Any]) -> Dict[str, Any] | None:
    event_payload = _to_event_dict(row)
    raw_payload = row.get("raw_payload") if isinstance(row.get("raw_payload"), dict) else {}

    location_candidates: list[Any] = [
        row.get("location"),
        row.get("position"),
        row.get("anchor"),
        event_payload.get("location"),
        event_payload.get("position"),
        event_payload.get("anchor"),
        raw_payload.get("location"),
        raw_payload.get("position"),
        raw_payload.get("anchor"),
    ]

    payload_candidates = _collect_payload_candidates(row)
    for payload in payload_candidates:
        location_candidates.extend([
            payload.get("location"),
            payload.get("position"),
            payload.get("anchor"),
        ])

    for candidate in location_candidates:
        parsed = _location_payload_to_anchor_origin(candidate)
        if parsed:
            return parsed

    return None


UNSAFE_GROUND_BLOCK_TOKENS = {
    "water",
    "flowing_water",
    "lava",
    "flowing_lava",
    "air",
    "cave_air",
    "void_air",
    "seagrass",
    "tall_seagrass",
    "kelp",
    "kelp_plant",
    "bubble_column",
}


def _extract_block_tokens_from_rule_event(row: Dict[str, Any]) -> set[str]:
    tokens: set[str] = set()
    payload_candidates = _collect_payload_candidates(row)
    for payload in payload_candidates:
        for key in ("block_type", "block", "material", "resource", "item_type"):
            normalized = _normalize_collect_resource_token(payload.get(key))
            if normalized:
                tokens.add(normalized)

    for quest_token in _collect_quest_event_tokens(row):
        normalized = _normalize_collect_resource_token(quest_token)
        if normalized:
            tokens.add(normalized)

    return tokens


def _anchor_priority_from_rule_event(row: Dict[str, Any]) -> int:
    event_type = _resolve_rule_event_type(row)
    block_tokens = _extract_block_tokens_from_rule_event(row)
    if block_tokens & UNSAFE_GROUND_BLOCK_TOKENS:
        return 0

    if event_type in {"interact_block", "block_interact"}:
        return 4
    if event_type in {"collect", "pickup", "pickup_item", "item_pickup"}:
        return 3
    if event_type in {"interact_entity", "near", "trigger", "quest_event"}:
        return 2
    if event_type in {"chat", "talk"}:
        return 1
    return 0


def _safe_ground_origin_from_rule_events(
    *,
    player_id: str,
    fallback_origin: Dict[str, Any],
    reference_origin: Dict[str, Any] | None = None,
    max_horizontal_distance: float | None = None,
) -> Dict[str, Any] | None:
    rows = _collect_rule_event_rows(player_id)
    if not rows:
        return None

    reference_x = None
    reference_z = None
    if isinstance(reference_origin, dict):
        reference_x = _coerce_float(reference_origin.get("base_x", reference_origin.get("x")))
        reference_z = _coerce_float(reference_origin.get("base_z", reference_origin.get("z")))

    distance_limit_sq: float | None = None
    if max_horizontal_distance is not None:
        try:
            parsed_distance = float(max_horizontal_distance)
        except (TypeError, ValueError):
            parsed_distance = 0.0
        if parsed_distance > 0:
            distance_limit_sq = parsed_distance * parsed_distance

    best_candidate: tuple[int, int, int, int, Dict[str, Any]] | None = None
    for index, row in enumerate(rows):
        if not isinstance(row, dict):
            continue

        location = _extract_location_from_rule_event(row)
        if not location:
            continue

        priority = _anchor_priority_from_rule_event(row)
        if priority <= 0:
            continue

        distance_sq = None
        if reference_x is not None and reference_z is not None:
            delta_x = float(location["x"]) - float(reference_x)
            delta_z = float(location["z"]) - float(reference_z)
            distance_sq = (delta_x * delta_x) + (delta_z * delta_z)
            if distance_limit_sq is not None and distance_sq > distance_limit_sq:
                continue

        timestamp_ms = _event_row_timestamp_ms(row) or 0
        candidate = {
            "x": float(location["x"]),
            "y": float(location["y"]),
            "z": float(location["z"]),
            "world": location.get("world") or str(fallback_origin.get("world") or "world"),
            "priority": priority,
            "timestamp_ms": timestamp_ms,
            "index": index,
            "distance_sq": distance_sq,
        }

        distance_rank = 0
        if distance_sq is not None:
            distance_rank = -int(round(float(distance_sq) * 1000.0))

        candidate_key = (priority, timestamp_ms, distance_rank, index)
        if best_candidate is None or candidate_key > best_candidate[:4]:
            best_candidate = (priority, timestamp_ms, distance_rank, index, candidate)

    if best_candidate is None:
        return None

    selected = dict(best_candidate[4])
    y = selected["y"]
    if selected["priority"] >= 4:
        y += 1.0

    y = max(1.0, min(320.0, y))

    return {
        "base_x": int(round(float(selected["x"]))),
        "base_y": int(round(float(y))),
        "base_z": int(round(float(selected["z"]))),
        "anchor_mode": "safe_ground",
        "world": str(selected.get("world") or fallback_origin.get("world") or "world"),
    }


def _extract_collect_resource_from_rule_event(row: Dict[str, Any]) -> tuple[str, int] | None:
    event_type = _resolve_rule_event_type(row)
    if event_type not in {"collect", "pickup", "pickup_item", "item_pickup", "quest_event"}:
        return None

    payload_candidates = _collect_payload_candidates(row)
    resource_name = ""
    for payload in payload_candidates:
        for key in ("resource", "item", "item_type", "block_type"):
            normalized = _normalize_collect_resource_token(payload.get(key))
            if normalized:
                resource_name = normalized
                break
        if resource_name:
            break

    if not resource_name:
        for token in _collect_quest_event_tokens(row):
            normalized = _normalize_collect_resource_token(token)
            if normalized:
                resource_name = normalized
                break

    if not resource_name and event_type.startswith("collect_"):
        resource_name = _normalize_collect_resource_token(event_type)

    if not resource_name:
        return None

    event_payload = _to_event_dict(row)
    amount_source: Any = None
    for payload in payload_candidates:
        amount_source = payload.get("amount") or payload.get("count")
        if amount_source is not None:
            break

    if amount_source is None:
        amount_source = row.get("count")
    if amount_source is None:
        amount_source = event_payload.get("count")

    amount = _coerce_positive_int(amount_source, 1)

    return resource_name, amount


def _collect_rule_event_rows(player_id: str) -> list[Dict[str, Any]]:
    try:
        from app.core.quest.runtime import quest_runtime
    except Exception:
        return []

    rows: list[Dict[str, Any]] = []

    try:
        recent_fetch = getattr(quest_runtime, "get_recent_rule_events", None)
        if callable(recent_fetch):
            recent_rows = recent_fetch(player_id)
            if isinstance(recent_rows, list):
                rows.extend([row for row in recent_rows if isinstance(row, dict)])
    except Exception:
        pass

    snapshot = quest_runtime.get_debug_snapshot(player_id)
    if isinstance(snapshot, dict):
        recent_rule_events = snapshot.get("recent_rule_events")
        if isinstance(recent_rule_events, list):
            rows.extend([row for row in recent_rule_events if isinstance(row, dict)])

        last_rule_event = snapshot.get("last_rule_event")
        if isinstance(last_rule_event, dict):
            rows.append(last_rule_event)

    players_state = getattr(quest_runtime, "_players", None)
    if isinstance(players_state, dict):
        state = players_state.get(player_id)
        if isinstance(state, dict):
            recent_state_events = state.get("recent_rule_events")
            if isinstance(recent_state_events, list):
                rows.extend([row for row in recent_state_events if isinstance(row, dict)])

            history_events = state.get("rule_events")
            if isinstance(history_events, list):
                for event in history_events:
                    if isinstance(event, dict):
                        rows.append({"event": dict(event)})

            state_last_rule_event = state.get("last_rule_event")
            if isinstance(state_last_rule_event, dict):
                rows.append(state_last_rule_event)

    deduped_rows: list[Dict[str, Any]] = []
    seen_keys: set[str] = set()
    for row in rows:
        try:
            dedupe_key = json.dumps(row, ensure_ascii=False, sort_keys=True, default=str)
        except Exception:
            dedupe_key = str(row)
        if dedupe_key in seen_keys:
            continue
        seen_keys.add(dedupe_key)
        deduped_rows.append(row)

    return deduped_rows


def _scene_resources_from_persistent_inventory(player_id: str) -> Dict[str, int]:
    try:
        from app.core.quest.runtime import quest_runtime
    except Exception:
        return {}

    read_resources = getattr(quest_runtime, "get_inventory_resources", None)
    if not callable(read_resources):
        return {}

    try:
        raw_resources = read_resources(player_id)
    except Exception:
        return {}

    normalized: Dict[str, int] = {}
    if isinstance(raw_resources, dict):
        for key, value in raw_resources.items():
            resource_name = _normalize_collect_resource_token(key)
            if not resource_name:
                continue
            amount = _coerce_positive_int(value, 0)
            if amount > 0:
                normalized[resource_name] = int(normalized.get(resource_name, 0)) + amount

    return normalized


def _scene_resources_from_recent_rule_events(player_id: str) -> Dict[str, int]:
    persisted_resources = _scene_resources_from_persistent_inventory(player_id)
    if persisted_resources:
        return persisted_resources

    rows = _collect_rule_event_rows(player_id)

    resources: Dict[str, int] = {}
    for row in rows:
        extracted = _extract_collect_resource_from_rule_event(row)
        if not extracted:
            continue
        resource_name, amount = extracted
        resources[resource_name] = int(resources.get(resource_name, 0)) + int(amount)

    return resources


def _scene_inventory_state_from_event_log(player_id: str) -> Dict[str, Any]:
    rows = _collect_rule_event_rows(player_id)
    latest_timestamp_ms = 0
    for row in rows:
        ts_ms = _event_row_timestamp_ms(row)
        if ts_ms and ts_ms > latest_timestamp_ms:
            latest_timestamp_ms = ts_ms

    if latest_timestamp_ms <= 0:
        latest_timestamp_ms = int(time.time() * 1000)

    return {
        "player_id": str(player_id or "default"),
        "resources": _scene_resources_from_recent_rule_events(str(player_id or "default")),
        "updated_at_ms": latest_timestamp_ms,
    }


def _scene_state_payload_from_scene_output(
    *,
    level_id: str,
    scene_output: Dict[str, Any] | None,
) -> Dict[str, Any] | None:
    if not isinstance(scene_output, dict):
        return None

    from app.core.narrative.scene_state import SceneState

    scene_state_payload = scene_output.get("scene_state")
    if isinstance(scene_state_payload, dict):
        state = SceneState.from_dict(scene_state_payload, fallback_level_id=level_id)
        return state.to_dict()

    scene_graph = scene_output.get("scene_graph")
    layout = scene_output.get("layout")
    scene_plan = scene_output.get("scene_plan") if isinstance(scene_output.get("scene_plan"), dict) else {}
    fragments = scene_plan.get("fragments") if isinstance(scene_plan.get("fragments"), list) else []

    state = SceneState.from_scene_payload(
        level_id=level_id,
        scene_graph=scene_graph if isinstance(scene_graph, dict) else {},
        layout=layout if isinstance(layout, dict) else {},
        spawned_nodes=fragments,
        version=1,
    )
    return state.to_dict()


def _persist_scene_state_for_player(
    *,
    player_id: str,
    level_id: str,
    scene_output: Dict[str, Any] | None,
) -> None:
    normalized_player = str(player_id or "").strip()
    normalized_level = str(level_id or "").strip()
    if not normalized_player or not normalized_level:
        return

    state_payload = _scene_state_payload_from_scene_output(level_id=normalized_level, scene_output=scene_output)
    if not isinstance(state_payload, dict):
        return

    try:
        from app.core.narrative.scene_state_store import scene_state_store

        scene_state_store.save_state(normalized_player, normalized_level, state_payload)
    except Exception:
        pass


def _scene_anchor_position_for_inject(
    *,
    text: str,
    requested_anchor: str | None,
    player_id: str | None,
    player_position: Dict[str, Any] | None = None,
) -> tuple[str, Dict[str, Any], Dict[str, Any] | None, Dict[str, Any], str]:
    selected_anchor = _resolve_scene_anchor(text=text, requested_anchor=requested_anchor)

    base_origin = _fixed_anchor_from_env()
    fixed_scene_anchors = _scene_anchors_from_env(base_origin)
    normalized_player_origin = _origin_from_anchor_location(
        player_position,
        fallback_origin=base_origin,
        anchor_mode="player",
    )

    if selected_anchor == "player" and normalized_player_origin:
        initial_anchor_origin = dict(normalized_player_origin)
    else:
        initial_anchor_origin = dict(fixed_scene_anchors.get(selected_anchor) or base_origin)

    anchor_origin = dict(initial_anchor_origin)
    safe_ground_applied = False

    if _as_bool_env("DRIFT_ENABLE_SAFE_GROUND_ANCHOR", default=True):
        if selected_anchor == "player":
            safe_ground_distance = _coerce_float(os.environ.get("DRIFT_SAFE_GROUND_PLAYER_RADIUS", "10"))
            if safe_ground_distance is None or safe_ground_distance <= 0:
                safe_ground_distance = 10.0
        else:
            safe_ground_distance = _coerce_float(os.environ.get("DRIFT_SAFE_GROUND_MAX_DISTANCE", "32"))
            if safe_ground_distance is not None and safe_ground_distance <= 0:
                safe_ground_distance = None

        safe_ground_origin = _safe_ground_origin_from_rule_events(
            player_id=str(player_id or "default"),
            fallback_origin=anchor_origin,
            reference_origin=initial_anchor_origin,
            max_horizontal_distance=safe_ground_distance,
        )
        if safe_ground_origin:
            anchor_origin = safe_ground_origin
            safe_ground_applied = True

    scene_anchors = _scene_anchors_from_env(anchor_origin)
    if selected_anchor == "player" and normalized_player_origin and not _as_bool_env("DRIFT_SAFE_GROUND_FORCE_PLAYER_OFFSET", default=False):
        anchor_payload = dict(anchor_origin)
    else:
        anchor_payload = scene_anchors.get(selected_anchor) or anchor_origin

    anchor_position = {
        "world": str(anchor_payload.get("world") or anchor_origin.get("world") or os.environ.get("DRIFT_SCENE_WORLD", "world")),
        "x": float(anchor_payload.get("base_x", anchor_origin["base_x"])),
        "y": float(anchor_payload.get("base_y", anchor_origin["base_y"])),
        "z": float(anchor_payload.get("base_z", anchor_origin["base_z"])),
    }

    player_position_payload = None
    if normalized_player_origin:
        player_position_payload = _position_from_anchor_origin(normalized_player_origin)

    initial_anchor_position = _position_from_anchor_origin(initial_anchor_origin)
    if safe_ground_applied:
        final_anchor = f"{selected_anchor}_safe_ground"
    else:
        final_anchor = selected_anchor

    return selected_anchor, anchor_position, player_position_payload, initial_anchor_position, final_anchor


def build_scene_events(
    *,
    player_id: str,
    scene_theme: str,
    scene_hint: str | None,
    text: str,
    anchor: str | None,
    player_position: Dict[str, Any] | None = None,
    level_id: str | None = None,
    patch_mode: str = "full",
    rule_events: Optional[List[Dict[str, Any]]] = None,
) -> Dict[str, Any]:
    from app.core.narrative import SceneState, assemble_scene, evolve_scene_state

    selected_anchor, anchor_position, player_position_payload, initial_anchor_position, final_anchor = _scene_anchor_position_for_inject(
        text=text,
        requested_anchor=anchor,
        player_id=player_id,
        player_position=player_position,
    )
    inventory_state = _scene_inventory_state_from_event_log(str(player_id or "default"))

    assembled_scene = assemble_scene(
        inventory_state,
        scene_theme,
        scene_hint=scene_hint,
        anchor_position=anchor_position,
    )

    scene_plan = dict(assembled_scene.get("scene_plan") or {})
    base_fragments = list(scene_plan.get("fragments") or [])
    base_scene_graph = dict(assembled_scene.get("scene_graph") or {})
    base_layout = dict(assembled_scene.get("layout") or {})

    base_scene_state = SceneState.from_scene_payload(
        level_id=str(level_id or "runtime"),
        scene_graph=base_scene_graph,
        layout=base_layout,
        spawned_nodes=base_fragments,
        version=1,
    )

    evolution_input_rows = rule_events if isinstance(rule_events, list) else _collect_rule_event_rows(str(player_id or "default"))
    evolution_result = evolve_scene_state(
        scene_state=base_scene_state,
        rule_events=evolution_input_rows,
        scene_hint=scene_hint,
        anchor_position=anchor_position,
    )

    evolved_scene_state = evolution_result.get("scene_state")
    evolved_scene_diff = evolution_result.get("scene_diff")
    evolved_scene_graph = dict(evolution_result.get("scene_graph") or base_scene_graph)
    evolved_layout = dict(evolution_result.get("layout") or base_layout)
    evolved_fragments = list(evolution_result.get("fragments") or base_fragments)
    evolved_event_plan = list(evolution_result.get("event_plan") or assembled_scene.get("event_plan") or [])
    incremental_event_plan = list(evolution_result.get("incremental_event_plan") or [])

    scene_state_payload = evolved_scene_state.to_dict() if hasattr(evolved_scene_state, "to_dict") else base_scene_state.to_dict()
    scene_diff_payload = evolved_scene_diff.to_dict() if hasattr(evolved_scene_diff, "to_dict") else {
        "added_nodes": [],
        "added_edges": [],
        "added_positions": {},
        "trigger_event_keys": [],
    }
    selected_assets = assembled_scene.get("selected_assets") if isinstance(assembled_scene.get("selected_assets"), list) else []
    asset_sources = assembled_scene.get("asset_sources") if isinstance(assembled_scene.get("asset_sources"), list) else []
    asset_selection = assembled_scene.get("asset_selection") if isinstance(assembled_scene.get("asset_selection"), dict) else {}
    fragment_source = assembled_scene.get("fragment_source") if isinstance(assembled_scene.get("fragment_source"), list) else []
    theme_filter = assembled_scene.get("theme_filter") if isinstance(assembled_scene.get("theme_filter"), dict) else {}

    normalized_patch_mode = str(patch_mode or "full").strip().lower()
    if normalized_patch_mode not in {"full", "incremental"}:
        normalized_patch_mode = "full"

    return {
        "scene_theme": scene_theme,
        "scene_hint": scene_hint,
        "level_id": str(level_id or "runtime"),
        "selected_anchor": selected_anchor,
        "initial_anchor": selected_anchor,
        "final_anchor": final_anchor,
        "initial_anchor_position": initial_anchor_position,
        "final_anchor_position": anchor_position,
        "anchor_position": anchor_position,
        "player_position": player_position_payload,
        "inventory_state": dict(assembled_scene.get("inventory_state") or inventory_state),
        "scene_plan": {
            **scene_plan,
            "fragments": list(evolved_fragments),
            "scene_graph": dict(evolved_scene_graph),
            "layout": dict(evolved_layout),
            "scene_hint": scene_hint,
        },
        "scene_graph": dict(evolved_scene_graph),
        "layout": dict(evolved_layout),
        "scoring_debug": dict(assembled_scene.get("scoring_debug") or {}),
        "asset_registry_version": assembled_scene.get("asset_registry_version"),
        "selected_assets": list(selected_assets),
        "asset_sources": list(asset_sources),
        "asset_selection": dict(asset_selection),
        "fragment_source": list(fragment_source),
        "theme_filter": dict(theme_filter),
        "scene_state": scene_state_payload,
        "scene_diff": scene_diff_payload,
        "patch_mode": normalized_patch_mode,
        "event_plan": evolved_event_plan,
        "incremental_event_plan": incremental_event_plan,
    }


def _resolve_inject_transaction_plan(
    *,
    player_id: str,
    text: str,
    payload: dict,
    requested_anchor: str | None,
    scene_theme: str | None,
    scene_hint: str | None,
    player_position: Dict[str, Any] | None = None,
    level_id: str | None = None,
) -> Dict[str, Any]:
    selected_anchor = _resolve_scene_anchor(text=text, requested_anchor=requested_anchor)
    tx_events = _story_tx_events_for_inject(
        text=text,
        payload=payload,
        anchor=selected_anchor,
    )

    scene_output: Dict[str, Any] | None = None
    normalized_theme = _normalize_scene_theme(scene_theme)
    normalized_hint = _normalize_scene_hint(scene_hint)
    if normalized_theme:
        scene_output = build_scene_events(
            player_id=player_id,
            scene_theme=normalized_theme,
            scene_hint=normalized_hint,
            text=text,
            anchor=selected_anchor,
            player_position=player_position,
            level_id=level_id,
            patch_mode="full",
        )
        scene_events = scene_output.get("event_plan") if isinstance(scene_output, dict) else None
        if isinstance(scene_events, list) and scene_events:
            tx_events = scene_events
            selected_anchor = str(scene_output.get("selected_anchor") or selected_anchor)

    return {
        "selected_anchor": selected_anchor,
        "tx_events": tx_events,
        "scene_output": scene_output,
    }


def _scene_meta_payload(scene_output: dict) -> dict:
    scene_plan = scene_output.get("scene_plan") if isinstance(scene_output.get("scene_plan"), dict) else {}
    inventory_state = scene_output.get("inventory_state") if isinstance(scene_output.get("inventory_state"), dict) else {}
    event_plan = scene_output.get("event_plan") if isinstance(scene_output.get("event_plan"), list) else []
    scoring_debug = scene_output.get("scoring_debug") if isinstance(scene_output.get("scoring_debug"), dict) else {}
    scene_graph = scene_output.get("scene_graph") if isinstance(scene_output.get("scene_graph"), dict) else {}
    layout = scene_output.get("layout") if isinstance(scene_output.get("layout"), dict) else {}
    scene_state = scene_output.get("scene_state") if isinstance(scene_output.get("scene_state"), dict) else {}
    scene_diff = scene_output.get("scene_diff") if isinstance(scene_output.get("scene_diff"), dict) else {}
    incremental_event_plan = scene_output.get("incremental_event_plan") if isinstance(scene_output.get("incremental_event_plan"), list) else []

    selected_root = scoring_debug.get("selected_root")
    candidate_scores = scoring_debug.get("candidate_scores") if isinstance(scoring_debug.get("candidate_scores"), list) else []
    selected_children = scoring_debug.get("selected_children") if isinstance(scoring_debug.get("selected_children"), list) else []
    blocked = scoring_debug.get("blocked") if isinstance(scoring_debug.get("blocked"), list) else []
    reasons = scoring_debug.get("reasons") if isinstance(scoring_debug.get("reasons"), dict) else {}
    semantic_scores = scoring_debug.get("semantic_scores") if isinstance(scoring_debug.get("semantic_scores"), dict) else {}
    semantic_resolution = scoring_debug.get("semantic_resolution") if isinstance(scoring_debug.get("semantic_resolution"), list) else []
    semantic_source = scoring_debug.get("semantic_source") if isinstance(scoring_debug.get("semantic_source"), dict) else {}
    semantic_adapter_hits = _safe_int(scoring_debug.get("semantic_adapter_hits"), 0)
    asset_registry_version = scene_output.get("asset_registry_version")
    if asset_registry_version is None:
        asset_registry_version = scoring_debug.get("asset_registry_version")
    selected_assets = scene_output.get("selected_assets") if isinstance(scene_output.get("selected_assets"), list) else []
    if not selected_assets and isinstance(scoring_debug.get("selected_assets"), list):
        selected_assets = list(scoring_debug.get("selected_assets") or [])
    asset_sources = scene_output.get("asset_sources") if isinstance(scene_output.get("asset_sources"), list) else []
    if not asset_sources and isinstance(scoring_debug.get("asset_sources"), list):
        asset_sources = list(scoring_debug.get("asset_sources") or [])
    asset_selection = scene_output.get("asset_selection") if isinstance(scene_output.get("asset_selection"), dict) else {}
    if not asset_selection and isinstance(scoring_debug.get("asset_selection"), dict):
        asset_selection = dict(scoring_debug.get("asset_selection") or {})
    if not asset_selection:
        asset_selection = {
            "selected_assets": list(selected_assets),
            "candidate_assets": [],
        }
    fragment_source = scene_output.get("fragment_source") if isinstance(scene_output.get("fragment_source"), list) else []
    if not fragment_source and isinstance(scoring_debug.get("fragment_source"), list):
        fragment_source = list(scoring_debug.get("fragment_source") or [])
    theme_filter = scene_output.get("theme_filter") if isinstance(scene_output.get("theme_filter"), dict) else {}
    if not theme_filter and isinstance(scoring_debug.get("theme_filter"), dict):
        theme_filter = dict(scoring_debug.get("theme_filter") or {})
    if not theme_filter:
        theme_filter = {
            "theme": scene_output.get("scene_theme"),
            "applied": False,
            "allowed_fragments": [],
        }

    return {
        "scene_theme": scene_output.get("scene_theme"),
        "scene_hint": scene_output.get("scene_hint"),
        "selected_anchor": scene_output.get("selected_anchor"),
        "initial_anchor": scene_output.get("initial_anchor") or scene_output.get("selected_anchor"),
        "final_anchor": scene_output.get("final_anchor") or scene_output.get("selected_anchor"),
        "player_pos": dict(scene_output.get("player_position") or {}) if isinstance(scene_output.get("player_position"), dict) else {},
        "initial_anchor_pos": dict(scene_output.get("initial_anchor_position") or {}) if isinstance(scene_output.get("initial_anchor_position"), dict) else {},
        "final_anchor_pos": dict(scene_output.get("final_anchor_position") or scene_output.get("anchor_position") or {}) if isinstance(scene_output.get("final_anchor_position") or scene_output.get("anchor_position"), dict) else {},
        "anchor_pos": dict(scene_output.get("anchor_position") or {}) if isinstance(scene_output.get("anchor_position"), dict) else {},
        "fragments": list(scene_plan.get("fragments") or []),
        "event_count": len(event_plan),
        "event_plan": list(event_plan),
        "scene_graph": dict(scene_graph),
        "layout": dict(layout),
        "scene_state": dict(scene_state),
        "scene_diff": dict(scene_diff),
        "patch_mode": str(scene_output.get("patch_mode") or "full"),
        "incremental_event_count": len(incremental_event_plan),
        "incremental_event_plan": list(incremental_event_plan),
        "inventory_resources": dict(inventory_state.get("resources") or {}),
        "selected_root": selected_root,
        "candidate_scores": list(candidate_scores),
        "selected_children": list(selected_children),
        "blocked": list(blocked),
        "reasons": dict(reasons),
        "semantic_scores": dict(semantic_scores),
        "semantic_resolution": list(semantic_resolution),
        "semantic_source": dict(semantic_source),
        "semantic_adapter_hits": semantic_adapter_hits,
        "asset_registry_version": asset_registry_version,
        "selected_assets": list(selected_assets),
        "asset_sources": list(asset_sources),
        "asset_selection": dict(asset_selection),
        "fragment_source": list(fragment_source),
        "theme_filter": dict(theme_filter),
    }


def _scene_npc_name_for_template(template: str) -> str:
    template_key = str(template or "").strip().lower()
    if template_key == "wanderer":
        return "阿无"
    if template_key == "merchant":
        return "商人"
    if template_key == "guard":
        return "守卫"
    return "旅人"


def _scene_offset_for_anchor_ref(anchor_ref: str) -> Dict[str, float]:
    normalized_ref = str(anchor_ref or "").strip().lower()
    if normalized_ref == "camp_edge":
        return {"dx": 2.0, "dy": 0.0, "dz": 1.0}
    if normalized_ref == "camp_center":
        return {"dx": 0.0, "dy": 0.0, "dz": 0.0}
    return {"dx": 1.0, "dy": 0.0, "dz": 1.0}


def _scene_float(value: Any, default: float) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return float(default)


def _scene_offset_for_event(event: Dict[str, Any], anchor_ref: str) -> Dict[str, float]:
    base_offset = dict(_scene_offset_for_anchor_ref(anchor_ref))

    data = event.get("data") if isinstance(event.get("data"), dict) else {}
    raw_offset = None
    if isinstance(event.get("offset"), dict):
        raw_offset = event.get("offset")
    elif isinstance(data.get("offset"), dict):
        raw_offset = data.get("offset")

    if not isinstance(raw_offset, dict):
        return base_offset

    return {
        "dx": _scene_float(raw_offset.get("dx"), base_offset["dx"]),
        "dy": _scene_float(raw_offset.get("dy"), base_offset["dy"]),
        "dz": _scene_float(raw_offset.get("dz"), base_offset["dz"]),
    }


def _project_legacy_world_patch_to_anchor(
    mc_patch: Dict[str, Any],
    anchor_position: Dict[str, Any] | None,
) -> Dict[str, Any]:
    if not isinstance(mc_patch, dict) or not isinstance(anchor_position, dict):
        return dict(mc_patch or {})

    anchor_x = _coerce_float(anchor_position.get("x"))
    anchor_y = _coerce_float(anchor_position.get("y"))
    anchor_z = _coerce_float(anchor_position.get("z"))
    if anchor_x is None or anchor_y is None or anchor_z is None:
        return dict(mc_patch)

    reference_x = _coerce_float(os.environ.get("DRIFT_AI_WORLD_REFERENCE_X", "0"))
    reference_y = _coerce_float(os.environ.get("DRIFT_AI_WORLD_REFERENCE_Y", "70"))
    reference_z = _coerce_float(os.environ.get("DRIFT_AI_WORLD_REFERENCE_Z", "0"))

    ref_x = float(reference_x if reference_x is not None else 0.0)
    ref_y = float(reference_y if reference_y is not None else 70.0)
    ref_z = float(reference_z if reference_z is not None else 0.0)

    delta_x = float(anchor_x) - ref_x
    delta_y = float(anchor_y) - ref_y
    delta_z = float(anchor_z) - ref_z

    shift_limit = _coerce_float(os.environ.get("DRIFT_AI_WORLD_SHIFT_LIMIT", "512"))
    if shift_limit is None or shift_limit <= 0:
        shift_limit = 512.0

    anchor_world = str(anchor_position.get("world") or os.environ.get("DRIFT_SCENE_WORLD", "world"))

    def _should_shift(x_value: float, z_value: float) -> bool:
        return abs(x_value - ref_x) <= shift_limit and abs(z_value - ref_z) <= shift_limit

    def _shift_xyz(raw: Any) -> Any:
        if not isinstance(raw, dict):
            return raw

        row = dict(raw)
        x_value = _coerce_float(row.get("x"))
        y_value = _coerce_float(row.get("y"))
        z_value = _coerce_float(row.get("z"))

        if x_value is None or y_value is None or z_value is None:
            if "world" not in row and anchor_world:
                row["world"] = anchor_world
            return row

        if _should_shift(float(x_value), float(z_value)):
            row["x"] = int(round(float(x_value) + delta_x))
            row["y"] = int(round(float(y_value) + delta_y))
            row["z"] = int(round(float(z_value) + delta_z))

        if "world" not in row and anchor_world:
            row["world"] = anchor_world
        return row

    projected = dict(mc_patch)

    if isinstance(projected.get("spawn"), dict):
        projected["spawn"] = _shift_xyz(projected.get("spawn"))

    for list_key in ("spawns", "blocks"):
        rows = projected.get(list_key)
        if not isinstance(rows, list):
            continue
        projected[list_key] = [_shift_xyz(row) for row in rows]

    teleport = projected.get("teleport")
    if isinstance(teleport, dict):
        teleport_mode = str(teleport.get("mode") or "").strip().lower()
        if teleport_mode in {"", "absolute"}:
            projected["teleport"] = _shift_xyz(teleport)

    return projected


def _scene_offset_add(base_offset: Dict[str, float], *, dx: float = 0.0, dy: float = 0.0, dz: float = 0.0) -> Dict[str, float]:
    return {
        "dx": _scene_float(base_offset.get("dx"), 0.0) + float(dx),
        "dy": _scene_float(base_offset.get("dy"), 0.0) + float(dy),
        "dz": _scene_float(base_offset.get("dz"), 0.0) + float(dz),
    }


def _scene_material_for_block(block_name: str) -> str:
    block_key = str(block_name or "").strip().lower()
    if ":" in block_key:
        block_key = block_key.split(":", 1)[1]

    aliases = {
        "fire": "campfire",
        "bonfire": "campfire",
        "wood": "oak_planks",
        "plank": "oak_planks",
        "planks": "oak_planks",
        "log": "oak_log",
    }
    normalized_key = aliases.get(block_key, block_key)

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

    if normalized_key in material_map:
        return material_map[normalized_key]

    fallback = re.sub(r"[^a-z0-9]+", "_", normalized_key).strip("_").upper()
    return fallback or "OAK_PLANKS"


def _scene_build_directives_for_structure(template: str, *, base_offset: Dict[str, float]) -> list[Dict[str, Any]]:
    template_key = str(template or "").strip().lower()

    if template_key == "camp_small":
        return [
            {
                "shape": "platform",
                "size": 2,
                "material": "OAK_PLANKS",
                "offset": dict(base_offset),
            },
            {
                "shape": "line",
                "size": 2,
                "material": "OAK_FENCE",
                "offset": _scene_offset_add(base_offset, dx=-1.0, dy=0.0, dz=-1.0),
            },
        ]

    if template_key == "cooking_area_basic":
        return [
            {
                "shape": "line",
                "size": 2,
                "material": "COBBLESTONE",
                "offset": dict(base_offset),
            },
            {
                "shape": "line",
                "size": 1,
                "material": "FURNACE",
                "offset": _scene_offset_add(base_offset, dx=1.0, dy=0.0, dz=0.0),
            },
        ]

    return [
        {
            "shape": "platform",
            "size": 1,
            "material": "OAK_PLANKS",
            "offset": dict(base_offset),
        }
    ]


def _scene_event_plan_to_world_patch(scene_output: Dict[str, Any] | None) -> Dict[str, Any]:
    if not isinstance(scene_output, dict):
        return {}

    patch_mode = str(scene_output.get("patch_mode") or "full").strip().lower()
    event_plan = scene_output.get("event_plan")
    if patch_mode == "incremental":
        incremental_plan = scene_output.get("incremental_event_plan")
        if isinstance(incremental_plan, list) and incremental_plan:
            event_plan = incremental_plan

    if not isinstance(event_plan, list) or not event_plan:
        return {}

    spawn_multi: list[Dict[str, Any]] = []
    build_multi: list[Dict[str, Any]] = []
    blocks: list[Dict[str, Any]] = []
    structures: list[Dict[str, Any]] = []

    for event in event_plan:
        if not isinstance(event, dict):
            continue

        event_type = str(event.get("type") or "").strip().lower()
        data = event.get("data") if isinstance(event.get("data"), dict) else {}
        anchor = event.get("anchor") if isinstance(event.get("anchor"), dict) else {}

        anchor_ref = str(anchor.get("ref") or "player")
        offset = _scene_offset_for_event(event, anchor_ref)
        world_name = str(anchor.get("world") or "").strip()
        event_id = str(event.get("event_id") or event_type or "scene_event")

        if event_type == "spawn_npc":
            npc_template = str(data.get("npc_template") or "wanderer")

            spawn_directive: Dict[str, Any] = {
                "type": "villager",
                "name": _scene_npc_name_for_template(npc_template),
                "offset": offset,
                "_scene_event_id": event_id,
            }

            if world_name:
                spawn_directive["world"] = world_name

            spawn_multi.append(spawn_directive)
            continue

        if event_type in {"spawn_block", "spawn_fire"}:
            block_name = str(data.get("block") or ("campfire" if event_type == "spawn_fire" else "oak_planks"))

            block_directive: Dict[str, Any] = {
                "type": block_name,
                "offset": offset,
                "_scene_event_id": event_id,
            }
            if world_name:
                block_directive["world"] = world_name
            blocks.append(block_directive)

            build_directive: Dict[str, Any] = {
                "shape": "line",
                "size": 1,
                "material": _scene_material_for_block(block_name),
                "offset": dict(offset),
                "_scene_event_id": event_id,
            }
            if world_name:
                build_directive["world"] = world_name
            build_multi.append(build_directive)
            continue

        if event_type == "spawn_structure":
            template = str(data.get("template") or data.get("name") or event.get("name") or "camp_small")

            structure_directive: Dict[str, Any] = {
                "template": template,
                "offset": offset,
                "_scene_event_id": event_id,
            }
            if isinstance(data.get("scene_variant"), str) and data.get("scene_variant"):
                structure_directive["scene_variant"] = str(data.get("scene_variant"))
            if world_name:
                structure_directive["world"] = world_name
            structures.append(structure_directive)

            for build_shape in _scene_build_directives_for_structure(template, base_offset=offset):
                executable_directive: Dict[str, Any] = dict(build_shape)
                executable_directive["_scene_event_id"] = event_id
                if world_name and "world" not in executable_directive:
                    executable_directive["world"] = world_name
                build_multi.append(executable_directive)
            continue

    if not spawn_multi and not build_multi and not blocks and not structures:
        return {}

    mc_patch: Dict[str, Any] = {}
    if spawn_multi:
        mc_patch["spawn_multi"] = spawn_multi
    if build_multi:
        mc_patch["build_multi"] = build_multi
    if blocks:
        mc_patch["blocks"] = blocks
    if structures:
        mc_patch["structure"] = structures

    return {
        "mc": mc_patch,
    }


def _merge_scene_world_patch(base_payload: Dict[str, Any], scene_patch: Dict[str, Any]) -> Dict[str, Any]:
    merged_payload: Dict[str, Any] = dict(base_payload or {})
    if not isinstance(scene_patch, dict) or not scene_patch:
        return merged_payload

    scene_mc = scene_patch.get("mc")
    if not isinstance(scene_mc, dict) or not scene_mc:
        return merged_payload

    base_mc_raw = merged_payload.get("mc")
    merged_mc: Dict[str, Any] = dict(base_mc_raw) if isinstance(base_mc_raw, dict) else {}

    list_merge_keys = {"spawn_multi", "build_multi", "blocks", "structure"}

    for merge_key in list_merge_keys:
        scene_list = scene_mc.get(merge_key)
        if not isinstance(scene_list, list) or not scene_list:
            continue

        merged_list: list[Any] = []
        existing_list = merged_mc.get(merge_key)
        if isinstance(existing_list, list):
            for item in existing_list:
                merged_list.append(dict(item) if isinstance(item, dict) else item)

        for item in scene_list:
            merged_list.append(dict(item) if isinstance(item, dict) else item)

        merged_mc[merge_key] = merged_list

    for key, value in scene_mc.items():
        if key in list_merge_keys:
            continue
        if key not in merged_mc:
            merged_mc[key] = value

    if merged_mc:
        merged_payload["mc"] = merged_mc

    return merged_payload


def merge_world_patches(base_patch: Dict[str, Any] | None, overlay_patch: Dict[str, Any] | None) -> Dict[str, Any]:
    base_payload = dict(base_patch or {})
    if not isinstance(overlay_patch, dict) or not overlay_patch:
        return base_payload
    return _merge_scene_world_patch(base_payload, overlay_patch)


def _scene_level_for_player(player_id: str):
    player_state = story_engine.players.get(player_id) if isinstance(story_engine.players, dict) else None
    if not isinstance(player_state, dict):
        return None
    return player_state.get("level")


def _scene_generation_for_level(level: Any) -> Dict[str, Any] | None:
    if level is None:
        return None

    level_meta = getattr(level, "meta", None)
    if isinstance(level_meta, dict):
        scene_generation = level_meta.get("scene_generation")
        if isinstance(scene_generation, dict):
            return dict(scene_generation)

    raw_payload = getattr(level, "_raw_payload", None)
    if isinstance(raw_payload, dict):
        raw_meta = raw_payload.get("meta")
        if isinstance(raw_meta, dict):
            scene_generation = raw_meta.get("scene_generation")
            if isinstance(scene_generation, dict):
                return dict(scene_generation)

    return None


def _update_scene_generation_for_level(level: Any, scene_generation: Dict[str, Any]) -> None:
    if level is None or not isinstance(scene_generation, dict):
        return

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


def _anchor_position_from_rule_payload(payload: Dict[str, Any]) -> Dict[str, Any] | None:
    if not isinstance(payload, dict):
        return None

    parsed = _location_payload_to_anchor_origin(payload.get("location") or payload.get("anchor") or payload.get("position"))
    if not isinstance(parsed, dict):
        return None

    return {
        "world": str(parsed.get("world") or os.environ.get("DRIFT_SCENE_WORLD", "world")),
        "x": float(parsed.get("x", 0.0)),
        "y": float(parsed.get("y", 64.0)),
        "z": float(parsed.get("z", 0.0)),
    }


def evolve_scene_for_rule_event(
    *,
    player_id: str,
    event_type: str | None,
    payload: Dict[str, Any] | None,
) -> Dict[str, Any] | None:
    normalized_player = str(player_id or "").strip()
    if not normalized_player:
        return None

    level = _scene_level_for_player(normalized_player)
    if level is None:
        return None

    level_id = str(getattr(level, "level_id", "") or "").strip()
    if not level_id:
        return None

    scene_generation = _scene_generation_for_level(level)
    if not isinstance(scene_generation, dict):
        return None

    from app.core.narrative.scene_evolution import evolve_scene_state
    from app.core.narrative.scene_state import SceneState
    from app.core.narrative.scene_state_store import scene_state_store

    stored_state_payload = scene_state_store.load_state(normalized_player, level_id)
    if isinstance(stored_state_payload, dict):
        current_state = SceneState.from_dict(stored_state_payload, fallback_level_id=level_id)
    else:
        generation_state = scene_generation.get("scene_state") if isinstance(scene_generation.get("scene_state"), dict) else None
        if isinstance(generation_state, dict):
            current_state = SceneState.from_dict(generation_state, fallback_level_id=level_id)
        else:
            scene_graph = scene_generation.get("scene_graph") if isinstance(scene_generation.get("scene_graph"), dict) else {}
            layout = scene_generation.get("layout") if isinstance(scene_generation.get("layout"), dict) else {}
            fragments = scene_generation.get("fragments") if isinstance(scene_generation.get("fragments"), list) else []
            current_state = SceneState.from_scene_payload(
                level_id=level_id,
                scene_graph=scene_graph,
                layout=layout,
                spawned_nodes=fragments,
                version=_safe_int(scene_generation.get("scene_state_version"), 1),
            )

    scene_hint_raw = scene_generation.get("scene_hint")
    scene_hint = str(scene_hint_raw).strip() if isinstance(scene_hint_raw, str) and scene_hint_raw.strip() else None

    anchor_position = None
    for key in ("anchor_pos", "final_anchor_pos", "anchor_position"):
        candidate = scene_generation.get(key)
        if isinstance(candidate, dict):
            anchor_position = dict(candidate)
            break
    if anchor_position is None:
        anchor_position = _anchor_position_from_rule_payload(payload or {})

    rule_event = {
        "event_type": str(event_type or "").strip().lower(),
        "payload": dict(payload or {}),
        "timestamp_ms": int(time.time() * 1000),
    }

    evolution_result = evolve_scene_state(
        scene_state=current_state,
        rule_events=[rule_event],
        scene_hint=scene_hint,
        anchor_position=anchor_position,
    )

    evolved_state = evolution_result.get("scene_state")
    evolved_diff = evolution_result.get("scene_diff")
    if not hasattr(evolved_state, "to_dict") or not hasattr(evolved_diff, "to_dict"):
        return None

    evolved_state_payload = evolved_state.to_dict()
    evolved_diff_payload = evolved_diff.to_dict()
    incremental_event_plan = list(evolution_result.get("incremental_event_plan") or [])
    full_event_plan = list(evolution_result.get("event_plan") or [])

    updated_generation = dict(scene_generation)
    updated_generation["scene_graph"] = dict(evolution_result.get("scene_graph") or updated_generation.get("scene_graph") or {})
    updated_generation["layout"] = dict(evolution_result.get("layout") or updated_generation.get("layout") or {})
    updated_generation["fragments"] = list(evolution_result.get("fragments") or updated_generation.get("fragments") or [])
    updated_generation["event_plan"] = full_event_plan
    updated_generation["event_count"] = len(full_event_plan)
    updated_generation["scene_state"] = evolved_state_payload
    updated_generation["scene_state_version"] = int(evolved_state_payload.get("version") or 1)
    updated_generation["scene_diff"] = evolved_diff_payload
    updated_generation["incremental_event_plan"] = incremental_event_plan
    updated_generation["incremental_event_count"] = len(incremental_event_plan)
    updated_generation["patch_mode"] = "incremental"

    scene_output = {
        "patch_mode": "incremental",
        "event_plan": full_event_plan,
        "incremental_event_plan": incremental_event_plan,
    }
    scene_world_patch = _scene_event_plan_to_world_patch(scene_output)

    _update_scene_generation_for_level(level, updated_generation)
    scene_state_store.save_state(normalized_player, level_id, evolved_state_payload)

    return {
        "scene_generation": updated_generation,
        "scene_diff": evolved_diff_payload,
        "scene_world_patch": scene_world_patch,
    }


def run_transaction(
    events: list[Dict[str, Any]],
    *,
    rule_version: str | None = None,
    engine_version: str | None = None,
) -> dict:
    normalized_events: list[dict] = []
    for index, event in enumerate(events or [], start=1):
        if not isinstance(event, dict):
            continue
        normalized_events.append(
            {
                "event_id": str(event.get("event_id") or f"story_evt_{index}"),
                "type": str(event.get("type") or "input"),
                "text": str(event.get("text") or ""),
            }
        )

    if not normalized_events:
        raise StoryTransactionError("TX_EVENTS_EMPTY")

    try:
        shell = TransactionShell()
        committed_graph = GraphState()
        committed_state = InternalState()
        tx = shell.begin_tx(committed_graph, committed_state)

        if isinstance(engine_version, str) and engine_version.strip():
            tx.metadata["engine_version"] = engine_version.strip()

        for event in normalized_events:
            shell.apply_event(tx, event)

        receipt = shell.commit(
            tx,
            committed_graph=committed_graph,
            committed_state=committed_state,
            rule_version=str(rule_version or "rule_v2_2"),
        )
        return {
            "tx_id": receipt.get("tx_id"),
            "base_state_hash": receipt.get("base_state_hash"),
            "committed_state_hash": receipt.get("committed_state_hash"),
            "committed_graph_hash": receipt.get("committed_graph_hash"),
            "commit_timestamp": receipt.get("commit_timestamp"),
            "rule_version": receipt.get("rule_version"),
            "engine_version": receipt.get("engine_version"),
            "event_count": len(normalized_events),
            "audit_trace": list(tx.audit_trace),
        }
    except Exception as exc:  # pragma: no cover - defensive boundary
        raise StoryTransactionError(f"TX_COMMIT_FAILED:{exc}") from exc


def _transaction_meta_payload(transaction_result: dict) -> dict:
    return {
        "tx_id": transaction_result.get("tx_id"),
        "base_state_hash": transaction_result.get("base_state_hash"),
        "committed_state_hash": transaction_result.get("committed_state_hash"),
        "committed_graph_hash": transaction_result.get("committed_graph_hash"),
        "commit_timestamp": transaction_result.get("commit_timestamp"),
        "rule_version": transaction_result.get("rule_version"),
        "engine_version": transaction_result.get("engine_version"),
        "event_count": int(transaction_result.get("event_count") or 0),
    }


def _normalize_injected_level_id(raw_level_id: str) -> str:
    """Ensure injected level ids follow the flagship_* convention."""

    sanitized = (raw_level_id or "").strip()
    if not sanitized:
        return "flagship_custom"

    if sanitized.endswith(".json"):
        sanitized = sanitized[:-5]

    lowered = sanitized.lower()

    if lowered.startswith("flagship_"):
        return sanitized

    if lowered.startswith("level_"):
        suffix = sanitized.split("_", 1)[1]
        if suffix:
            try:
                return f"flagship_{int(suffix):02d}"
            except ValueError:
                return f"flagship_{suffix}"

    if lowered.startswith("custom_") or lowered.startswith("story_"):
        return f"flagship_{sanitized}"

    if lowered.isdigit():
        return f"flagship_{int(lowered):02d}"

    return sanitized

# ============================================================
# ✔ Pydantic 模型（用于 JSON 注入）
# ============================================================
class InjectPayload(BaseModel):
    level_id: str     # test_inject
    title: str        # 测试剧情
    text: str         # 单段剧情文本（自动转成 list）
    player_id: Optional[str] = "default"
    player_position: Optional[Dict[str, Any]] = None
    anchor: Optional[str] = None
    scene_theme: Optional[str] = None
    scene_hint: Optional[str] = None


SCENE_ANCHOR_ID_PATTERN = re.compile(r"^[a-z0-9][a-z0-9_-]{0,31}$")
SCENE_ANCHOR_IDS = ("player", "home", "npc_zone", "interaction_zone", "memory_scene")


def _normalize_scene_anchor_id(raw_anchor: str | None) -> str | None:
    if raw_anchor is None:
        return None
    if not isinstance(raw_anchor, str):
        return None

    normalized = raw_anchor.strip().lower()
    if not normalized:
        return None
    if not SCENE_ANCHOR_ID_PATTERN.fullmatch(normalized):
        return None

    return normalized


def _scene_anchor_from_text(text: str) -> str:
    lowered = (text or "").lower()

    memory_keywords = ("回忆", "记忆", "往事", "梦境", "memory", "flashback")
    npc_keywords = ("npc", "守卫", "村民", "商人", "villager", "zombie", "skeleton")
    interaction_keywords = ("互动", "交互", "对话", "任务", "解谜", "interaction")

    if any(keyword in lowered for keyword in memory_keywords):
        return "memory_scene"
    if any(keyword in lowered for keyword in npc_keywords):
        return "npc_zone"
    if any(keyword in lowered for keyword in interaction_keywords):
        return "interaction_zone"
    return "player"


def _origin_from_scene_anchor_env(anchor_id: str, fallback: dict) -> dict:
    env_prefix = f"DRIFT_SCENE_ANCHOR_{anchor_id.upper()}"
    fallback_world = str(fallback.get("world") or os.environ.get("DRIFT_SCENE_WORLD", "world"))
    return {
        "base_x": int(os.environ.get(f"{env_prefix}_X", str(fallback["base_x"]))),
        "base_y": int(os.environ.get(f"{env_prefix}_Y", str(fallback["base_y"]))),
        "base_z": int(os.environ.get(f"{env_prefix}_Z", str(fallback["base_z"]))),
        "anchor_mode": fallback.get("anchor_mode", "fixed"),
        "world": str(os.environ.get(f"{env_prefix}_WORLD", fallback_world)),
    }


def _scene_anchors_from_env(base_origin: dict) -> dict:
    home = {
        "base_x": int(base_origin["base_x"]),
        "base_y": int(base_origin["base_y"]),
        "base_z": int(base_origin["base_z"]),
        "anchor_mode": str(base_origin.get("anchor_mode") or "fixed"),
        "world": str(base_origin.get("world") or os.environ.get("DRIFT_SCENE_WORLD", "world")),
    }

    player = {
        "base_x": int(home["base_x"]),
        "base_y": int(home["base_y"]),
        "base_z": int(home["base_z"]),
        "anchor_mode": "player",
        "world": home["world"],
    }

    npc_zone_default = {
        "base_x": home["base_x"] + 24,
        "base_y": home["base_y"],
        "base_z": home["base_z"],
        "anchor_mode": home["anchor_mode"],
    }
    interaction_zone_default = {
        "base_x": home["base_x"],
        "base_y": home["base_y"],
        "base_z": home["base_z"] + 24,
        "anchor_mode": home["anchor_mode"],
    }
    memory_scene_default = {
        "base_x": home["base_x"] - 32,
        "base_y": home["base_y"] + 6,
        "base_z": home["base_z"] - 32,
        "anchor_mode": home["anchor_mode"],
    }

    return {
        "player": _origin_from_scene_anchor_env("player", player),
        "home": _origin_from_scene_anchor_env("home", home),
        "npc_zone": _origin_from_scene_anchor_env("npc_zone", npc_zone_default),
        "interaction_zone": _origin_from_scene_anchor_env("interaction_zone", interaction_zone_default),
        "memory_scene": _origin_from_scene_anchor_env("memory_scene", memory_scene_default),
    }


def _resolve_scene_anchor(*, text: str, requested_anchor: str | None) -> str:
    normalized_requested = _normalize_scene_anchor_id(requested_anchor)
    if normalized_requested in SCENE_ANCHOR_IDS:
        return normalized_requested

    env_anchor = _normalize_scene_anchor_id(os.environ.get("DRIFT_SCENE_ANCHOR"))
    if env_anchor in SCENE_ANCHOR_IDS:
        return env_anchor

    inferred = _scene_anchor_from_text(text)
    if inferred in SCENE_ANCHOR_IDS:
        return inferred
    return "player"


def _build_level_document(level_id: str, title: str, text: str, bootstrap_patch: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "id": level_id,
        "title": title,
        "text": [text],
        "tags": [],
        "mood": {"base": "calm", "intensity": 0.5},
        "choices": [],
        "meta": {},
        "npcs": [],
        "bootstrap_patch": bootstrap_patch,
        "world_patch": bootstrap_patch,
        "tree": None,
    }


def _as_bool_env(name: str, default: bool = False) -> bool:
    raw = os.environ.get(name)
    if raw is None:
        return default
    return str(raw).strip().lower() in {"1", "true", "yes", "on"}


def _fixed_anchor_from_env() -> dict:
    return {
        "base_x": int(os.environ.get("DRIFT_FIXED_ANCHOR_X", "0")),
        "base_y": int(os.environ.get("DRIFT_FIXED_ANCHOR_Y", "64")),
        "base_z": int(os.environ.get("DRIFT_FIXED_ANCHOR_Z", "0")),
        "anchor_mode": "fixed",
        "world": str(os.environ.get("DRIFT_SCENE_WORLD", "world")),
    }


def _extract_debug_payload(compose_result: dict) -> dict:
    mapping_result = compose_result.get("mapping_result") or {}
    decision_trace = compose_result.get("decision_trace") or mapping_result.get("trace") or {}
    rule_version = decision_trace.get("rule_version") if isinstance(decision_trace, dict) else None
    engine_version = decision_trace.get("engine_version") if isinstance(decision_trace, dict) else None
    return {
        "mapping_status": mapping_result.get("status", "UNAVAILABLE"),
        "mapping_failure_code": mapping_result.get("failure_code", "UNAVAILABLE"),
        "degrade_reason": mapping_result.get("degrade_reason"),
        "lost_semantics": mapping_result.get("lost_semantics") or [],
        "rule_version": rule_version,
        "engine_version": engine_version,
        "decision_trace": decision_trace,
        "compose_path": compose_result.get("compose_path", "unknown"),
    }


def _build_payload_v1_for_inject(*, player_id: str, text: str) -> tuple[dict, dict]:
    use_v2_mapper = _as_bool_env("DRIFT_USE_V2_MAPPER", default=False)
    strict_mode = _as_bool_env("DRIFT_V2_STRICT_MODE", default=False)

    if use_v2_mapper:
        compose_result = compose_scene_and_structure_v2(text, strict_mode=strict_mode)
    else:
        compose_result = compose_scene_and_structure(text)

    if compose_result.get("status") != "SUCCESS":
        debug_payload = _extract_debug_payload(compose_result) if _as_bool_env("DRIFT_DEBUG_TRACE", default=False) else {}
        raise PayloadV1BuildError(compose_result.get("failure_code", "COMPOSE_FAILED"), debug_payload)

    payload_v1 = build_plugin_payload_v1(
        compose_result,
        player_id=player_id,
        origin=_fixed_anchor_from_env(),
    )

    debug_payload: dict = {}
    if _as_bool_env("DRIFT_DEBUG_TRACE", default=False):
        debug_payload = _extract_debug_payload(compose_result)

    return payload_v1, debug_payload


def _build_payload_v2_for_inject(
    *,
    player_id: str,
    text: str,
    anchor: str | None = None,
    player_position: Dict[str, Any] | None = None,
) -> tuple[dict, dict]:
    strict_mode = _as_bool_env("DRIFT_V2_STRICT_MODE", default=False)

    compose_result = compose_scene_and_structure_v2(text, strict_mode=strict_mode)
    if compose_result.get("status") != "SUCCESS":
        debug_payload = _extract_debug_payload(compose_result) if _as_bool_env("DRIFT_DEBUG_TRACE", default=False) else {}
        raise PayloadV2BuildErrorWrapper(compose_result.get("failure_code", "COMPOSE_FAILED"), debug_payload)

    base_origin = _fixed_anchor_from_env()
    selected_anchor, final_anchor_position, _, _, _ = _scene_anchor_position_for_inject(
        text=text,
        requested_anchor=anchor,
        player_id=player_id,
        player_position=player_position,
    )

    scene_anchors = _scene_anchors_from_env(base_origin)
    selected_anchor_origin = _origin_from_anchor_location(
        final_anchor_position,
        fallback_origin=base_origin,
        anchor_mode="player" if selected_anchor == "player" else "fixed",
    )
    if selected_anchor_origin:
        scene_anchors[selected_anchor] = selected_anchor_origin

    active_origin = dict(scene_anchors.get(selected_anchor) or base_origin)

    try:
        payload_v2, payload_trace = build_plugin_payload_v2_with_trace(
            compose_result,
            player_id=player_id,
            origin=active_origin,
            strict_mode=strict_mode,
            anchor=selected_anchor,
            anchors=scene_anchors,
        )
    except PayloadV2BuildError as exc:
        debug_payload = {}
        if _as_bool_env("DRIFT_DEBUG_TRACE", default=False):
            debug_payload = _extract_debug_payload(compose_result)
            debug_payload.update({
                "payload_v2_failure_code": exc.failure_code,
                "payload_v2_trace": exc.trace or {},
            })
        raise PayloadV2BuildErrorWrapper(exc.failure_code, debug_payload) from exc

    debug_payload: dict = {}
    if _as_bool_env("DRIFT_DEBUG_TRACE", default=False):
        debug_payload = _extract_debug_payload(compose_result)
        debug_payload["payload_v2_trace"] = payload_trace
        debug_payload["scene_anchor"] = selected_anchor

    return payload_v2, debug_payload


# ============================================================
# ✔ 获取所有关卡
# ============================================================
@router.get("/levels")
def api_story_levels():
    return {"status": "ok", "levels": list_levels()}


# ============================================================
# ✔ 获取关卡详情
# ============================================================
@router.get("/level/{level_id}")
def api_story_level(level_id: str):
    try:
        lv = load_level(level_id)
        return {"status": "ok", "level": lv.__dict__}
    except FileNotFoundError:
        return {"status": "error", "msg": f"Level {level_id} not found"}


# ============================================================
# ✔ 加载关卡（Minecraft 进入剧情）
# ============================================================
@router.post("/load/{player_id}/{level_id}")
def api_story_load(player_id: str, level_id: str):
    try:
        patch = story_engine.load_level_for_player(player_id, level_id)
        return {"status": "ok", "msg": f"{level_id} loaded", "bootstrap_patch": patch}
    except FileNotFoundError:
        return {"status": "error", "msg": f"Level {level_id} not found"}


# ============================================================
# ✔ 推进剧情
# ============================================================
@router.post("/advance/{player_id}")
def api_story_advance(player_id: str, payload: Dict[str, Any]):
    world_state = payload.get("world_state", {}) or {}
    action = payload.get("action", {}) or {}

    option, node, patch = story_engine.advance(player_id, world_state, action)
    return {
        "status": "ok",
        "option": option,
        "node": node,
        "world_patch": patch
    }


# ============================================================
# ✔ 获取玩家当前 Story 状态
# ============================================================
@router.get("/state/{player_id}")
def api_story_state(player_id: str):
    return {"status": "ok", "state": story_engine.get_public_state(player_id)}


# ============================================================
# ⭐ NEW：创建新的剧情关卡（以 JSON Body 注入）
# ============================================================
@router.post("/inject")
def api_story_inject(payload: InjectPayload):
    """
    JSON Body 示例：
    {
        "level_id": "test_inject",
        "title": "测试剧情",
        "text": "这是自动注入的剧情节点"
    }
    """
    LEVEL_DIR = DATA_DIR                         # ⭐ 与 story_loader 使用相同目录
    os.makedirs(LEVEL_DIR, exist_ok=True)

    level_id = _normalize_injected_level_id(payload.level_id)

    file_path = os.path.join(LEVEL_DIR, f"{level_id}.json")

    if os.path.exists(file_path):
        raise HTTPException(
            status_code=400,
            detail=f"Level {level_id} already exists"
        )

    use_payload_v1 = _as_bool_env("DRIFT_USE_PAYLOAD_V1", default=False)
    use_payload_v2 = _as_bool_env("DRIFT_USE_PAYLOAD_V2", default=False)

    if use_payload_v2:
        try:
            player_id = (payload.player_id or "default").strip() or "default"
            payload_v2, debug_payload = _build_payload_v2_for_inject(
                player_id=player_id,
                text=payload.text,
                anchor=payload.anchor,
                player_position=payload.player_position,
            )

            tx_plan = _resolve_inject_transaction_plan(
                player_id=player_id,
                text=payload.text,
                payload=payload_v2,
                requested_anchor=payload.anchor,
                scene_theme=payload.scene_theme,
                scene_hint=payload.scene_hint,
                player_position=payload.player_position,
                level_id=level_id,
            )

            scene_patch = _scene_event_plan_to_world_patch(tx_plan.get("scene_output"))
            payload_with_scene = _merge_scene_world_patch(payload_v2, scene_patch)

            selected_anchor = str(tx_plan.get("selected_anchor") or _resolve_scene_anchor(text=payload.text, requested_anchor=payload.anchor))
            transaction_result = run_transaction(
                tx_plan.get("tx_events") or _story_tx_events_for_inject(text=payload.text, payload=payload_v2, anchor=selected_anchor),
                rule_version=str(payload_v2.get("rule_version") or "rule_v2_2"),
                engine_version=str(payload_v2.get("engine_version") or "engine_v2_1"),
            )

            level_doc = _build_level_document(
                level_id=level_id,
                title=payload.title,
                text=payload.text,
                bootstrap_patch=payload_with_scene,
            )
            level_doc["meta"] = dict(level_doc.get("meta") or {})
            level_doc["meta"]["trng_transaction"] = _transaction_meta_payload(transaction_result)
            if tx_plan.get("scene_output"):
                level_doc["meta"]["scene_generation"] = _scene_meta_payload(tx_plan["scene_output"])
                _persist_scene_state_for_player(
                    player_id=player_id,
                    level_id=level_id,
                    scene_output=tx_plan.get("scene_output"),
                )

            with open(file_path, "w", encoding="utf-8") as f:
                json.dump(level_doc, f, ensure_ascii=False, indent=2)

            result = dict(payload_with_scene)
            result.update({
                "status": "ok",
                "msg": f"Level {level_id} created with payload_v2",
                "level_id": level_id,
                "file": file_path,
            })
            if debug_payload:
                result.update(debug_payload)
            if tx_plan.get("scene_output"):
                result["scene"] = tx_plan["scene_output"]
            if scene_patch:
                result["scene_world_patch"] = scene_patch
            if _as_bool_env("DRIFT_DEBUG_TRACE", default=False):
                result["transaction"] = transaction_result
            return result
        except StoryTransactionError as exc:
            response = {
                "detail": f"story_transaction_failed: {exc}",
            }
            if _as_bool_env("DRIFT_DEBUG_TRACE", default=False):
                response["failure_code"] = "TRNG_TRANSACTION_FAILED"
            return JSONResponse(status_code=422, content=response)
        except PayloadV2BuildErrorWrapper as exc:
            response = {
                "detail": f"payload_v2_build_failed: {exc.failure_code}",
            }
            if _as_bool_env("DRIFT_DEBUG_TRACE", default=False) and exc.debug_payload:
                response.update(exc.debug_payload)
            return JSONResponse(status_code=422, content=response)
        except Exception as exc:
            raise HTTPException(status_code=422, detail=f"payload_v2_build_failed: {exc}") from exc

    if use_payload_v1:
        try:
            player_id = (payload.player_id or "default").strip() or "default"
            payload_v1, debug_payload = _build_payload_v1_for_inject(player_id=player_id, text=payload.text)

            tx_plan = _resolve_inject_transaction_plan(
                player_id=player_id,
                text=payload.text,
                payload=payload_v1,
                requested_anchor=payload.anchor,
                scene_theme=payload.scene_theme,
                scene_hint=payload.scene_hint,
                player_position=payload.player_position,
                level_id=level_id,
            )

            scene_patch = _scene_event_plan_to_world_patch(tx_plan.get("scene_output"))
            payload_with_scene = _merge_scene_world_patch(payload_v1, scene_patch)

            transaction_result = run_transaction(
                tx_plan.get("tx_events") or _story_tx_events_for_inject(text=payload.text, payload=payload_v1, anchor=None),
                rule_version=str(debug_payload.get("rule_version") or "rule_v2_2") if isinstance(debug_payload, dict) else "rule_v2_2",
                engine_version=str(debug_payload.get("engine_version") or "engine_v2_1") if isinstance(debug_payload, dict) else "engine_v2_1",
            )

            level_doc = _build_level_document(
                level_id=level_id,
                title=payload.title,
                text=payload.text,
                bootstrap_patch=payload_with_scene,
            )
            level_doc["meta"] = dict(level_doc.get("meta") or {})
            level_doc["meta"]["trng_transaction"] = _transaction_meta_payload(transaction_result)
            if tx_plan.get("scene_output"):
                level_doc["meta"]["scene_generation"] = _scene_meta_payload(tx_plan["scene_output"])
                _persist_scene_state_for_player(
                    player_id=player_id,
                    level_id=level_id,
                    scene_output=tx_plan.get("scene_output"),
                )

            with open(file_path, "w", encoding="utf-8") as f:
                json.dump(level_doc, f, ensure_ascii=False, indent=2)

            result = dict(payload_with_scene)
            result.update({
                "status": "ok",
                "msg": f"Level {level_id} created with payload_v1",
                "level_id": level_id,
                "file": file_path,
            })
            if debug_payload:
                result.update(debug_payload)
            if tx_plan.get("scene_output"):
                result["scene"] = tx_plan["scene_output"]
            if scene_patch:
                result["scene_world_patch"] = scene_patch
            if _as_bool_env("DRIFT_DEBUG_TRACE", default=False):
                result["transaction"] = transaction_result
            return result
        except StoryTransactionError as exc:
            response = {
                "detail": f"story_transaction_failed: {exc}",
            }
            if _as_bool_env("DRIFT_DEBUG_TRACE", default=False):
                response["failure_code"] = "TRNG_TRANSACTION_FAILED"
            return JSONResponse(status_code=422, content=response)
        except PayloadV1BuildError as exc:
            response = {
                "detail": f"payload_v1_build_failed: {exc.failure_code}",
            }
            if _as_bool_env("DRIFT_DEBUG_TRACE", default=False) and exc.debug_payload:
                response.update(exc.debug_payload)
            return JSONResponse(status_code=422, content=response)
        except Exception as exc:
            raise HTTPException(status_code=422, detail=f"payload_v1_build_failed: {exc}") from exc

    player_id = (payload.player_id or "default").strip() or "default"
    tx_plan = _resolve_inject_transaction_plan(
        player_id=player_id,
        text=payload.text,
        payload={"version": "legacy_ai_world"},
        requested_anchor=payload.anchor,
        scene_theme=payload.scene_theme,
        scene_hint=payload.scene_hint,
        player_position=payload.player_position,
        level_id=level_id,
    )

    try:
        transaction_result = run_transaction(
            tx_plan.get("tx_events")
            or _story_tx_events_for_inject(
                text=payload.text,
                payload={"version": "legacy_ai_world"},
                anchor=str(tx_plan.get("selected_anchor") or _resolve_scene_anchor(text=payload.text, requested_anchor=payload.anchor)),
            ),
            rule_version="rule_v2_2",
            engine_version="engine_v2_1",
        )
    except StoryTransactionError as exc:
        response = {
            "detail": f"story_transaction_failed: {exc}",
        }
        if _as_bool_env("DRIFT_DEBUG_TRACE", default=False):
            response["failure_code"] = "TRNG_TRANSACTION_FAILED"
        return JSONResponse(status_code=422, content=response)

    # ⭐ 使用AI生成完整的世界内容（NPC、环境、建筑等）
    from app.core.ai.deepseek_agent import call_deepseek
    
    ai_prompt = f"""
基于用户的故事描述生成一个完整的Minecraft世界场景。
用户描述：{payload.text}

要求：
1. 生成spawn点（玩家出生位置）
2. 生成至少1-3个NPC（类型从villager/zombie/skeleton/cow/pig选择）
3. 生成环境建筑（使用简单方块如stone/oak_planks/glass等）
4. 设置天气和时间（如晴天/白天，或雨天/夜晚营造氛围）

返回JSON格式：
{{
  "spawn": {{"x": 0, "y": 70, "z": 0}},
  "npcs": [
    {{"type": "villager", "name": "商人", "x": 5, "y": 70, "z": 0, "dialog": "欢迎光临！"}},
    {{"type": "cow", "name": "奶牛", "x": -3, "y": 70, "z": 2}}
  ],
  "blocks": [
    {{"type": "stone", "x": 0, "y": 69, "z": 0}},
    {{"type": "oak_planks", "x": 1, "y": 70, "z": 1}}
  ],
  "time": "day",
  "weather": "clear"
}}
"""
    
    try:
        ai_result = call_deepseek(
            context={"type": "world_generation", "story": payload.text},
            messages=[{"role": "user", "content": ai_prompt}],
            temperature=0.8
        )
        
        # 解析AI返回的世界数据
        world_data = json.loads(ai_result.get("response", "{}"))
        
        # 构造bootstrap_patch包含AI生成的完整世界
        bootstrap_patch = {
            "variables": {
                "story_world_generated": True,
                "story_title": payload.title
            },
            "mc": {
                "tell": f"§6{payload.title}§r\n{payload.text}",
                "spawn": world_data.get("spawn", {"x": 0, "y": 70, "z": 0}),
                "time": world_data.get("time", "day"),
                "weather": world_data.get("weather", "clear")
            }
        }
        
        # 添加NPC生成指令
        npcs_data = world_data.get("npcs", [])
        if npcs_data:
            bootstrap_patch["mc"]["spawns"] = [
                {
                    "type": npc.get("type", "villager"),
                    "name": npc.get("name", "NPC"),
                    "x": npc.get("x", 0),
                    "y": npc.get("y", 70),
                    "z": npc.get("z", 0),
                    "dialog": npc.get("dialog", "")
                }
                for npc in npcs_data
            ]
        
        # 添加建筑方块（简化处理）
        blocks_data = world_data.get("blocks", [])
        if blocks_data:
            bootstrap_patch["mc"]["blocks"] = blocks_data[:50]  # 限制数量避免卡顿
            
    except Exception as e:
        # AI调用失败时回退到基础版本
        print(f"AI world generation failed: {e}")
        bootstrap_patch = {
            "variables": {},
            "mc": {
                "tell": f"§6{payload.title}§r\n{payload.text}",
                "spawn": {"x": 0, "y": 70, "z": 0}
            }
        }

    scene_patch = _scene_event_plan_to_world_patch(tx_plan.get("scene_output"))

    scene_output = tx_plan.get("scene_output") if isinstance(tx_plan.get("scene_output"), dict) else {}
    scene_anchor_position = scene_output.get("anchor_position") if isinstance(scene_output.get("anchor_position"), dict) else None
    if scene_anchor_position and isinstance(bootstrap_patch.get("mc"), dict):
        bootstrap_patch["mc"] = _project_legacy_world_patch_to_anchor(
            bootstrap_patch.get("mc") or {},
            scene_anchor_position,
        )

    bootstrap_patch = _merge_scene_world_patch(bootstrap_patch, scene_patch)

    data = _build_level_document(
        level_id=level_id,
        title=payload.title,
        text=payload.text,
        bootstrap_patch=bootstrap_patch,
    )
    data["meta"] = dict(data.get("meta") or {})
    data["meta"]["trng_transaction"] = _transaction_meta_payload(transaction_result)
    if tx_plan.get("scene_output"):
        data["meta"]["scene_generation"] = _scene_meta_payload(tx_plan["scene_output"])
        _persist_scene_state_for_player(
            player_id=player_id,
            level_id=level_id,
            scene_output=tx_plan.get("scene_output"),
        )

    with open(file_path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

    result = {
        "status": "ok",
        "msg": f"Level {level_id} created with AI-generated world",
        "level_id": level_id,
        "file": file_path,
        "world_preview": bootstrap_patch.get("mc", {}),
    }
    if tx_plan.get("scene_output"):
        result["scene"] = tx_plan["scene_output"]
    if scene_patch:
        result["scene_world_patch"] = scene_patch
    if _as_bool_env("DRIFT_DEBUG_TRACE", default=False):
        result["transaction"] = transaction_result
    return result