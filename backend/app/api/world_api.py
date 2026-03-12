import os
import time
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
from app.core.quest.runtime import quest_runtime
from app.core.runtime.interaction_event import create_interaction_event, interaction_event_to_dict

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


def _normalize_token(value: Any) -> str:
    token = str(value or "").strip().lower()
    if not token:
        return ""
    return token.replace("-", "_").replace(" ", "_").strip("_")


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


def _ingest_rule_event_via_trng(event: "RuleTriggerEvent") -> Dict[str, Any]:
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

    interaction_event = create_interaction_event(
        event_type=interaction_type,
        player_id=event.player_id,
        npc_id=npc_id,
        anchor=_anchor_from_rule_payload(payload),
        data=data,
        event_id=str(payload.get("event_id") or f"plugin_{incoming_type}_{_now_ms()}"),
        timestamp_ms=_safe_int(payload.get("timestamp_ms"), _now_ms()),
    )
    interaction_payload = interaction_event_to_dict(interaction_event)

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


def _update_scene_generation_for_player(player_id: str, scene_generation: Dict[str, Any]) -> bool:
    if not isinstance(scene_generation, dict):
        return False

    level = _scene_level_for_player(player_id)
    if level is None:
        return False

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
    response = quest_runtime.handle_rule_trigger(event.player_id, {
        "event_type": event.event_type,
        "payload": event.payload,
    })
    logger.debug(
        "story_rule_event",
        extra={"player_id": event.player_id, "event_type": event.event_type},
    )

    interaction_tx: Dict[str, Any] | None = None
    interaction_tx_error: str | None = None
    if _as_bool_env("DRIFT_ENABLE_PLUGIN_TRNG", default=True):
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

    result = {"status": "ok", "result": response}
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

    scene_evolution: Dict[str, Any] | None = None
    scene_evolution_error: str | None = None
    try:
        from app.api.story_api import evolve_scene_for_rule_event, merge_world_patches

        scene_evolution = evolve_scene_for_rule_event(
            player_id=event.player_id,
            event_type=event.event_type,
            payload=event.payload,
        )

        if isinstance(scene_evolution, dict):
            scene_patch = scene_evolution.get("scene_world_patch")
            if isinstance(scene_patch, dict) and scene_patch:
                existing_patch = result.get("world_patch") if isinstance(result.get("world_patch"), dict) else {}
                result["world_patch"] = merge_world_patches(existing_patch, scene_patch)

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

    if _as_bool_env("DRIFT_DEBUG_TRACE", default=False):
        if interaction_tx is not None:
            result["interaction_transaction"] = interaction_tx
        if interaction_tx_error:
            result["interaction_transaction_error"] = interaction_tx_error
        if scene_evolution is not None:
            result["scene_evolution"] = scene_evolution
        if scene_evolution_error:
            result["scene_evolution_error"] = scene_evolution_error
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

    snapshot = quest_runtime.get_debug_snapshot(player_id)
    narrative_state = _narrative_state_for_player(
        player_id,
        snapshot=snapshot,
        scene_generation=scene_generation,
    )
    asset_observability = _asset_registry_observability_payload(scene_generation)
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
        }
        result.update(_narrative_fields_payload(narrative_state))
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
    payload.update(_narrative_fields_payload(narrative_state))
    payload.update(asset_observability)
    payload.update(pack_observability)
    return payload


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
    scene_generation = _scene_generation_for_player(normalized_player) or {}

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

    anchor = request_payload.anchor
    if isinstance(anchor, str) and anchor.strip():
        anchor = anchor.strip()
    else:
        anchor = None

    player_position = request_payload.player_position if isinstance(request_payload.player_position, dict) else None
    request_text = scene_hint or f"spawn fragment {scene_theme}"

    from app.api.story_api import build_scene_events, _scene_event_plan_to_world_patch

    scene_output = build_scene_events(
        player_id=normalized_player,
        scene_theme=scene_theme,
        scene_hint=scene_hint,
        text=request_text,
        anchor=anchor,
        player_position=player_position,
    )
    scene_patch = _scene_event_plan_to_world_patch(scene_output)

    scene_plan = scene_output.get("scene_plan") if isinstance(scene_output.get("scene_plan"), dict) else {}
    event_plan = scene_output.get("event_plan") if isinstance(scene_output.get("event_plan"), list) else []
    fragments = scene_plan.get("fragments") if isinstance(scene_plan.get("fragments"), list) else []

    world_patch = scene_patch if isinstance(scene_patch, dict) else {}
    has_patch = bool(world_patch)

    logger.info(
        "story_spawn_fragment",
        extra={
            "player_id": normalized_player,
            "scene_theme": scene_theme,
            "fragment_count": len(fragments),
            "event_count": len(event_plan),
            "has_world_patch": has_patch,
        },
    )

    return {
        "status": "ok",
        "msg": "Scene fragment generated." if has_patch else "Scene fragment generated (no executable patch).",
        "player_id": normalized_player,
        "scene_theme": scene_theme,
        "scene_hint": scene_hint,
        "fragment_count": len(fragments),
        "event_count": len(event_plan),
        "scene": scene_output,
        "world_patch": world_patch,
    }


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
