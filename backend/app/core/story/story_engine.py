# backend/app/core/story/story_engine.py
from __future__ import annotations

import logging
import time
from copy import deepcopy
from difflib import SequenceMatcher
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Set, Tuple

from app.core.ai.deepseek_agent import deepseek_decide
from app.core.story.story_loader import (
    DATA_DIR,
    load_level,
    build_level_prompt,
    Level,
)
from app.core.story.story_graph import StoryGraph
from app.core.world.minimap import MiniMap
from app.core.world.scene_generator import SceneGenerator
from app.core.world.trigger import trigger_engine
from app.core.world.trigger import TriggerPoint
from app.core.npc import npc_engine
from app.core.quest.runtime import quest_runtime
from app.core.story.level_schema import (
    ensure_level_extensions,
    MemoryCondition,
    MemoryMutation,
    EmotionalWorldPatchConfig,
)
from app.core.events.event_manager import EventManager


logger = logging.getLogger(__name__)


CINEMATIC_LIBRARY: Dict[str, Dict[str, Any]] = {
    "scene_grid_intro": {
        "mc": {
            "tell": "🏁 漂移热身开启，赛道灯光逐段点亮。",
            "title": {
                "main": "§6漂移节奏",
                "sub": "桃子挥旗示意，你的油门已就绪。",
                "fade_in": 10,
                "stay": 60,
                "fade_out": 20,
            },
            "sound": {
                "type": "MUSIC_DISC_BLOCKS",
                "volume": 0.8,
                "pitch": 1.0,
            },
            "particle": {
                "type": "CLOUD",
                "count": 90,
                "radius": 2.2,
                "speed": 0.01,
            },
            "_cinematic": {
                "slow_motion": 0.85,
                "sequence": [
                    {"action": "fade_out", "duration": 1.0},
                    {"action": "wait", "duration": 0.25},
                    {"action": "camera", "offset": {"yaw": 22.0, "pitch": -8.0}, "hold": 0.6},
                    {
                        "action": "sound",
                        "sound": "ENTITY_PLAYER_LEVELUP",
                        "volume": 0.8,
                        "pitch": 1.3,
                        "hold": 0.35,
                    },
                    {
                        "action": "particle",
                        "particle": "CRIT",
                        "count": 100,
                        "radius": 1.6,
                        "offset": {"y": 0.4},
                        "hold": 0.45,
                    },
                    {"action": "fade_in", "duration": 0.8},
                ],
            },
        }
    },
    "scene_midfield_boost": {
        "mc": {
            "actionbar": "§e赛道加速区开启，保持油门别松！",
            "sound": {
                "type": "ENTITY_BLAZE_SHOOT",
                "volume": 0.9,
                "pitch": 1.1,
            },
            "particle": {
                "type": "FLAME",
                "count": 120,
                "radius": 1.4,
                "speed": 0.05,
            },
            "_cinematic": {
                "sequence": [
                    {"action": "camera", "offset": {"yaw": -18.0, "pitch": -5.0}, "hold": 0.45},
                    {
                        "action": "particle",
                        "particle": "FLAME",
                        "count": 140,
                        "radius": 1.5,
                        "offset": {"y": 0.2},
                        "hold": 0.5,
                    },
                ],
            },
        }
    },
    "scene_podium": {
        "mc": {
            "title": {
                "main": "§6终点庆典",
                "sub": "桃子为你点亮终点烟火。",
                "fade_in": 12,
                "stay": 80,
                "fade_out": 30,
            },
            "sound": {
                "type": "UI_TOAST_CHALLENGE_COMPLETE",
                "volume": 1.3,
                "pitch": 1.0,
            },
            "particle": {
                "type": "FIREWORKS_SPARK",
                "count": 160,
                "radius": 2.6,
                "speed": 0.04,
            },
            "_cinematic": {
                "slow_motion": 0.65,
                "sequence": [
                    {"action": "fade_out", "duration": 1.1},
                    {"action": "wait", "duration": 0.2},
                    {"action": "camera", "offset": {"yaw": -30.0, "pitch": -10.0}, "hold": 0.7},
                    {
                        "action": "sound",
                        "sound": "ENTITY_FIREWORK_ROCKET_LAUNCH",
                        "volume": 1.4,
                        "pitch": 1.0,
                        "hold": 0.5,
                    },
                    {
                        "action": "particle",
                        "particle": "FIREWORKS_SPARK",
                        "count": 140,
                        "radius": 2.4,
                        "offset": {"y": 1.2},
                        "hold": 0.6,
                    },
                    {"action": "fade_in", "duration": 1.0},
                ],
            },
        }
    },
    "scene_base_camp": {
        "mc": {
            "title": {
                "main": "§b登山营地",
                "sub": "帐篷灯光在雪线下闪烁。",
                "fade_in": 10,
                "stay": 70,
                "fade_out": 20,
            },
            "sound": {
                "type": "MUSIC_DISC_CHIRP",
                "volume": 0.7,
                "pitch": 1.0,
            },
            "particle": {
                "type": "CAMPFIRE_COSY_SMOKE",
                "count": 90,
                "radius": 1.8,
                "speed": 0.01,
            },
            "_cinematic": {
                "slow_motion": 0.9,
                "sequence": [
                    {"action": "fade_out", "duration": 0.8},
                    {"action": "camera", "offset": {"pitch": -20.0}, "hold": 0.5},
                    {
                        "action": "sound",
                        "sound": "BLOCK_NOTE_BLOCK_FLUTE",
                        "volume": 0.8,
                        "pitch": 1.2,
                        "hold": 0.4,
                    },
                    {
                        "action": "particle",
                        "particle": "FALLING_SPORE_BLOSSOM",
                        "count": 80,
                        "radius": 1.5,
                        "offset": {"y": 1.0},
                        "hold": 0.5,
                    },
                    {"action": "fade_in", "duration": 0.9},
                ],
            },
        }
    },
    "scene_mid_camp": {
        "mc": {
            "actionbar": "§b半山腰补给点 · 棉花糖香味弥漫。",
            "sound": {
                "type": "BLOCK_CAMPFIRE_CRACKLE",
                "volume": 1.0,
                "pitch": 1.0,
            },
            "particle": {
                "type": "CAMPFIRE_SIGNAL_SMOKE",
                "count": 120,
                "radius": 2.0,
                "speed": 0.02,
            },
            "_cinematic": {
                "sequence": [
                    {"action": "camera", "offset": {"yaw": 18.0}, "hold": 0.4},
                    {
                        "action": "particle",
                        "particle": "CAMPFIRE_SIGNAL_SMOKE",
                        "count": 120,
                        "radius": 1.9,
                        "offset": {"y": 1.0},
                        "hold": 0.45,
                    },
                ],
            },
        }
    },
    "scene_summit_fire": {
        "mc": {
            "title": {
                "main": "§f山顶篝火",
                "sub": "你与阿无在火光中对视。",
                "fade_in": 12,
                "stay": 90,
                "fade_out": 30,
            },
            "sound": {
                "type": "MUSIC_DISC_PIGSTEP",
                "volume": 0.8,
                "pitch": 0.95,
            },
            "particle": {
                "type": "ASH",
                "count": 160,
                "radius": 2.8,
                "speed": 0.02,
            },
            "_cinematic": {
                "slow_motion": 0.6,
                "sequence": [
                    {"action": "fade_out", "duration": 1.2},
                    {"action": "camera", "offset": {"pitch": -25.0}, "hold": 0.7},
                    {
                        "action": "sound",
                        "sound": "ENTITY_LIGHTNING_BOLT_THUNDER",
                        "volume": 0.6,
                        "pitch": 1.1,
                        "hold": 0.4,
                    },
                    {
                        "action": "particle",
                        "particle": "FIREWORKS_SPARK",
                        "count": 200,
                        "radius": 3.0,
                        "offset": {"y": 1.5},
                        "hold": 0.7,
                    },
                    {"action": "fade_in", "duration": 1.2},
                ],
            },
        }
    },
}


class StoryEngine:
    DEFAULT_EXIT_ALIASES = ["结束剧情", "离开关卡", "退出剧情", "退出", "leave", "exit"]
    DEFAULT_RETURN_SPAWNS: Dict[str, Dict[str, Any]] = {
        "KunmingLakeHub": {
            "world": "KunmingLakeHub",
            "x": 128.5,
            "y": 72.0,
            "z": -16.5,
            "yaw": 180.0,
            "pitch": 0.0,
        }
    }
    DEFAULT_ENTRY_LEVEL = "flagship_tutorial"

    def __init__(self):
        # 每个玩家的剧情状态
        self.players: Dict[str, Dict[str, Any]] = {}

        # 这些冷却参数保留字段，但 v2 不再用于“是否推进”判断
        self.move_cooldown = 3.0
        self.say_cooldown = 0.8

        # 关卡目录（旗舰 → 旧版）
        primary_dir = Path(DATA_DIR)

        # 确保主目录存在，便于后续写入玩家自定义剧情
        primary_dir.mkdir(parents=True, exist_ok=True)

        # 整体剧情图谱 + 小地图 + 场景生成
        self.graph = StoryGraph(str(primary_dir))
        self.minimap = MiniMap(self.graph)
        self.scene_gen = SceneGenerator()

        # 触发器（v2：暂时禁用螺旋触发，避免乱飞）
        self._inject_spiral_triggers()

        # Phase 2 runtime
        self.event_manager = EventManager()
        quest_runtime.set_rule_callback(self._handle_rule_catalyst)
        quest_runtime.set_orphan_callback(self._handle_orphan_rule_event)

        self._custom_story_dir = primary_dir

        print(f"[StoryEngine] loading levels from {primary_dir}")

    def register_generated_level(self, level_id: Optional[str] = None) -> None:
        """Refresh story graph and minimap after new level assets are written."""

        self.graph.reload_levels()
        self.minimap.refresh()
        if level_id:
            print(f"[StoryEngine] registered new level: {level_id}")

    # ============================================================
    # Phase 1.5 scaffolding hooks (stubs)
    # ============================================================
    def enter_level_with_scene(self, player_id: str, level: Level) -> None:
        """Apply deterministic scene metadata when available.

        TODO: integrate with SceneOrchestrator to emit world patches and handle
        cleanup. For now we retain the handle on the player state to avoid
        losing context when future integrations arrive.
        """

        scene_cfg = getattr(level, "scene", None)
        if not scene_cfg:
            return

        player_state = self.players.setdefault(player_id, {})
        player_state["scene_handle"] = {
            "scene": scene_cfg,
            "applied": False,
        }

    def advance_with_beat(self, player_id: str, beat_id: str) -> None:
        """Move the active beat pointer forward.

        TODO: trigger beat-driven world patches and ensure quest/task syncing
        once the runtime supports these hooks.
        """

        player_state = self.players.setdefault(player_id, {})
        player_state["current_beat"] = beat_id

    def register_rule_listeners(self, level: Level) -> None:
        """Register rule listeners with the quest runtime.

        TODO: Bridge into the Minecraft plugin once a transport layer exists.
        """

        rule_cfg = getattr(level, "rules", None)
        if not rule_cfg or not getattr(rule_cfg, "listeners", None):
            return

        for listener in rule_cfg.listeners:
            quest_runtime.register_rule_listener(level.level_id, listener)

    def inject_tasks(self, player_id: str, level: Level) -> None:
        """Inject Phase 1.5 task definitions into QuestRuntime."""

        tasks = getattr(level, "tasks", [])
        if not tasks:
            return

        # TODO: convert TaskConfig dataclasses into legacy dicts and load them
        # into QuestRuntime once serialization is finalized.
        player_state = self.players.setdefault(player_id, {})
        player_state["pending_tasks"] = tasks

    def exit_level_with_cleanup(self, player_id: str, level: Level) -> Dict[str, Any]:
        """Compose a cleanup patch when a player exits the level."""

        player_state = self.players.setdefault(player_id, {})
        exit_profile = player_state.pop("exit_profile", None)
        player_state.pop("scene_handle", None)
        player_state.pop("current_beat", None)
        player_state.pop("beat_state", None)
        player_state.pop("pending_nodes", None)
        player_state.pop("pending_patches", None)
        player_state.pop("emotional_profile", None)
        player_state.pop("autofix_hints", None)
        self.event_manager.unregister(player_id)
        quest_runtime.exit_level(player_id)

        cleanup_meta = {
            "level_id": getattr(level, "level_id", None),
            "scene": getattr(level, "scene", None) is not None,
        }
        cleanup_meta["memory_flags"] = sorted(self._get_memory_set(player_id))
        hub_target = self._resolve_exit_target(exit_profile)

        farewell = None
        if isinstance(exit_profile, dict):
            farewell = exit_profile.get("farewell")
        if not farewell:
            farewell = f"已离开《{getattr(level, 'title', getattr(level, 'level_id', '该关卡'))}》，即将返回主线。"

        mc_payload: Dict[str, Any] = {
            "_scene_cleanup": cleanup_meta,
            "tell": farewell,
            "title": {
                "main": "§6剧情结束",
                "sub": "欢迎回到昆明湖主线",
                "fade_in": 10,
                "stay": 80,
                "fade_out": 20,
            },
        }

        if hub_target:
            mc_payload["teleport"] = {
                "mode": "absolute",
                "world": hub_target.get("world"),
                "x": hub_target.get("x", 0.0),
                "y": hub_target.get("y", 70.0),
                "z": hub_target.get("z", 0.0),
                "yaw": hub_target.get("yaw", 0.0),
                "pitch": hub_target.get("pitch", 0.0),
                "safe_platform": {
                    "material": "LIGHT_GRAY_CONCRETE",
                    "radius": 3,
                },
            }

        self.graph.update_trajectory(
            player_id,
            getattr(level, "level_id", None),
            "exit",
            {
                "hub": hub_target,
                "farewell": farewell,
                "aliases": exit_profile.get("aliases") if isinstance(exit_profile, dict) else None,
            },
        )

        exit_summary: Dict[str, Any] = {
            "hub": hub_target,
            "farewell": farewell,
        }
        if isinstance(exit_profile, dict) and exit_profile.get("aliases"):
            exit_summary["aliases"] = list(exit_profile["aliases"])

        return {"mc": mc_payload, "exit_summary": exit_summary}

    def reset_player_runtime(
        self,
        player_id: str,
        *,
        clear_memory: bool = True,
        clear_history: bool = True,
        clear_persisted_state: bool = True,
        clear_inventory: bool = True,
    ) -> Dict[str, Any]:
        normalized_player = str(player_id or "").strip()
        if not normalized_player:
            return {
                "player_id": "",
                "had_story_state": False,
                "quest_runtime": {
                    "player_id": "",
                    "had_active_state": False,
                    "cleared_runtime": False,
                    "cleared_persisted": 0,
                    "cleared_inventory": 0,
                },
                "cleared_memory": False,
                "cleared_history": 0,
                "level_id": None,
            }

        player_state = self.players.pop(normalized_player, None)
        current_level_id = None
        if isinstance(player_state, dict):
            level = player_state.get("level")
            if level is not None:
                current_level_id = getattr(level, "level_id", None)

        self.event_manager.unregister(normalized_player)
        self.minimap.reset_player(normalized_player)
        trigger_engine.reset_player(normalized_player)

        runtime_reset = quest_runtime.reset_player_state(
            normalized_player,
            clear_persisted=clear_persisted_state,
            clear_inventory=clear_inventory,
        )

        memory_cleared = False
        if clear_memory and normalized_player in self.graph.memory_snapshots:
            self.graph.memory_snapshots.pop(normalized_player, None)
            memory_cleared = True

        history_cleared = 0
        if clear_history:
            history_entries = self.graph.trajectory.pop(normalized_player, [])
            history_cleared = len(history_entries) if isinstance(history_entries, list) else 0

        return {
            "player_id": normalized_player,
            "had_story_state": isinstance(player_state, dict),
            "quest_runtime": runtime_reset,
            "cleared_memory": memory_cleared,
            "cleared_history": int(history_cleared),
            "level_id": current_level_id,
        }

    # ============================================================
    # 状态查询
    # ============================================================
    def get_public_state(self, player_id: Optional[str] = None):
        return {
            "total_levels": len(self.graph.all_levels()),
            "levels": sorted(list(self.graph.all_levels())),
            "players": list(self.players.keys()),
            "player_current_level": (
                self.players.get(player_id, {}).get("level").level_id
                if player_id in self.players and self.players[player_id].get("level")
                else None
            ),
            "exit_profile": self.get_exit_profile(player_id) if player_id else None,
        }

    def get_exit_profile(self, player_id: str) -> Optional[Dict[str, Any]]:
        profile = self.players.get(player_id, {}).get("exit_profile")
        if isinstance(profile, dict):
            return dict(profile)
        return None

    def _ensure_player(self, player_id: str):
        if player_id not in self.players:
            self.players[player_id] = {
                "messages": [],
                "nodes": [],
                "level": None,
                "level_loaded": False,
                "tree_state": None,
                "ended": False,
                "last_time": 0.0,
                "last_say_time": 0.0,
                "memory_flags": set(),
                "emotional_profile": None,
            }

    # ============================================================
    # Memory helpers
    # ============================================================
    def _normalize_flag(self, flag: Any) -> Optional[str]:
        if flag is None:
            return None
        if isinstance(flag, str):
            token = flag.strip()
        else:
            token = str(flag).strip()
        return token or None

    def _get_memory_set(self, player_id: str) -> Set[str]:
        state = self.players[player_id]
        flags = state.setdefault("memory_flags", set())
        if isinstance(flags, list):
            normalized = {
                token
                for token in (self._normalize_flag(item) for item in flags)
                if token
            }
            flags = normalized
            state["memory_flags"] = flags
        return flags

    def _handle_orphan_rule_event(
        self,
        player_id: str,
        orphan_record: Dict[str, Any],
        runtime_state: Dict[str, Any],
    ) -> Optional[Dict[str, Any]]:
        """Provide a confidence-scored auto-heal hint for orphan rule events."""

        player_state = self.players.get(player_id)
        if not player_state:
            return None

        level = player_state.get("level")
        if not level:
            return None

        event = orphan_record.get("event") or {}
        orphan_token = event.get("quest_event") or event.get("target")
        if not isinstance(orphan_token, str):
            return None

        normalized_token = orphan_token.strip().lower()
        if not normalized_token:
            return None

        best: Optional[Dict[str, Any]] = None

        def _consider(candidate: Optional[str], *, reason: str, task_id: Optional[str], task_title: Optional[str], source: str) -> None:
            nonlocal best
            if not candidate:
                return
            token = str(candidate).strip().lower()
            if not token:
                return
            ratio = SequenceMatcher(None, normalized_token, token).ratio()
            if ratio < 0.55:
                return

            proposal = {
                "candidate_event": token,
                "task_id": task_id,
                "task_title": task_title,
                "reason": reason,
                "source": source,
                "level_id": getattr(level, "level_id", None),
                "confidence": round(ratio, 3),
            }
            if not best or ratio > best.get("confidence", 0.0):
                best = proposal

        runtime_tasks = runtime_state.get("tasks") or []
        for session in runtime_tasks:
            task_id = getattr(session, "id", None)
            task_title = getattr(session, "title", None)

            for ref in getattr(session, "rule_refs", []) or []:
                if isinstance(ref, str):
                    _consider(ref, reason="rule_ref", task_id=task_id, task_title=task_title, source="runtime")

            milestone_list = getattr(session, "milestones", []) or []
            for milestone in milestone_list:
                milestone_event = getattr(milestone, "event", None) or getattr(milestone, "milestone_event", None)
                if isinstance(milestone_event, str):
                    _consider(milestone_event, reason="milestone_event", task_id=task_id, task_title=task_title, source="runtime")
                target = getattr(milestone, "target", None)
                if isinstance(target, str):
                    _consider(target, reason="milestone_target", task_id=task_id, task_title=task_title, source="runtime")

            target_value = getattr(session, "target", None)
            if isinstance(target_value, str):
                _consider(target_value, reason="task_target", task_id=task_id, task_title=task_title, source="runtime")

        level_tasks = getattr(level, "tasks", []) or []
        for task in level_tasks:
            if hasattr(task, "__dict__") and not isinstance(task, dict):
                task_map = dict(getattr(task, "__dict__", {}))
            elif isinstance(task, dict):
                task_map = dict(task)
            else:
                task_map = {}
            task_id = task_map.get("id") or task_map.get("task_id")
            task_title = task_map.get("title")

            for field in ("rule_event", "target"):
                field_value = task_map.get(field)
                if isinstance(field_value, str):
                    _consider(field_value, reason=field, task_id=task_id, task_title=task_title, source="level")

            for cond in task_map.get("conditions", []) or []:
                quest_event = cond.get("quest_event") if isinstance(cond, dict) else None
                if isinstance(quest_event, str):
                    _consider(quest_event, reason="condition", task_id=task_id, task_title=task_title, source="level")

            for milestone in task_map.get("milestones", []) or []:
                milestone_event = milestone.get("milestone_event") if isinstance(milestone, dict) else None
                if isinstance(milestone_event, str):
                    _consider(milestone_event, reason="level_milestone", task_id=task_id, task_title=task_title, source="level")

            title_slug = str(task_title or "").strip().lower().replace(" ", "_")
            if title_slug:
                _consider(title_slug, reason="title_slug", task_id=task_id, task_title=task_title, source="level")

            for tag in task_map.get("tags", []) or []:
                if isinstance(tag, str):
                    _consider(tag, reason="tag", task_id=task_id, task_title=task_title, source="level")

        if not best:
            return None

        autofix_bucket = player_state.setdefault("autofix_hints", {})
        autofix_bucket[normalized_token] = dict(best)

        logger.info(
            "StoryEngine auto-heal suggestion",
            extra={
                "player_id": player_id,
                "level_id": getattr(level, "level_id", None),
                "orphan_event": normalized_token,
                "candidate_event": best["candidate_event"],
                "confidence": best["confidence"],
            },
        )

        return dict(best)

    def _is_memory_satisfied(self, player_id: str, requirement: Any) -> bool:
        memory = self._get_memory_set(player_id)
        if isinstance(requirement, MemoryCondition):
            return requirement.is_satisfied(memory)
        if isinstance(requirement, (list, tuple, set)):
            required = [self._normalize_flag(item) for item in requirement]
            return all(flag in memory for flag in required if flag)
        token = self._normalize_flag(requirement)
        if token:
            return token in memory
        return True

    def _apply_memory_mutation(
        self,
        player_id: str,
        mutation: Optional[MemoryMutation],
        *,
        level: Optional[Level] = None,
        source: Optional[str] = None,
        ref: Optional[str] = None,
    ) -> bool:
        if not mutation or mutation.is_noop():
            return False

        memory = self._get_memory_set(player_id)
        changed = False

        for flag in mutation.set_flags:
            token = self._normalize_flag(flag)
            if not token:
                continue
            if token not in memory:
                memory.add(token)
                changed = True

        for flag in mutation.clear_flags:
            token = self._normalize_flag(flag)
            if not token:
                continue
            if token in memory:
                memory.remove(token)
                changed = True

        if changed:
            level_id = None
            if level and getattr(level, "level_id", None):
                level_id = level.level_id
            elif self.players[player_id].get("level") and getattr(
                self.players[player_id]["level"], "level_id", None
            ):
                level_id = self.players[player_id]["level"].level_id
            self.graph.update_memory_flags(
                player_id,
                sorted(memory),
                level_id=level_id,
                source=source,
                ref=ref,
            )
            self._retry_memory_locked_beats(player_id)

        return changed

    def _retry_memory_locked_beats(self, player_id: str) -> None:
        player_state = self.players.get(player_id)
        if not player_state:
            return
        beat_state = player_state.get("beat_state") or {}
        locked: Set[str] = beat_state.get("memory_locked") or set()
        if not locked:
            return
        level = player_state.get("level")
        if not level:
            return
        locked_sources = beat_state.get("memory_locked_sources") or {}
        pending = list(locked)
        for beat_id in pending:
            beat = (beat_state.get("by_id") or {}).get(beat_id)
            if not beat:
                locked.discard(beat_id)
                locked_sources.pop(beat_id, None)
                continue
            requirement = getattr(beat, "memory_required", None)
            if not self._is_memory_satisfied(player_id, requirement):
                continue
            trigger_info = self._parse_trigger(getattr(beat, "trigger", None))
            source = locked_sources.get(beat_id) or "memory_refresh"
            if trigger_info["kind"] in {"auto", "on_enter", "immediate", ""}:
                update = self._activate_beat(
                    player_id,
                    beat_id,
                    level,
                    source=source,
                    context={"memory_unlock": True},
                )
                if update:
                    self._queue_beat_update(player_id, update)
            locked.discard(beat_id)
            locked_sources.pop(beat_id, None)

    def apply_quest_updates(self, player_id: str, updates: Optional[Dict[str, Any]]) -> None:
        if not updates or not isinstance(updates, dict):
            return

        player_state = self.players.get(player_id)
        if not player_state:
            return

        level = player_state.get("level")
        completion_memory: Dict[str, MemoryMutation] = player_state.get("task_completion_memory") or {}
        milestone_memory: Dict[str, MemoryMutation] = player_state.get("milestone_memory") or {}

        changed = False

        for task_id in updates.get("completed_tasks", []) or []:
            normalized = self._normalize_flag(task_id)
            if not normalized:
                continue
            mutation = completion_memory.get(normalized)
            if isinstance(mutation, MemoryMutation) and not mutation.is_noop():
                if self._apply_memory_mutation(
                    player_id,
                    mutation,
                    level=level,
                    source="task_complete",
                    ref=normalized,
                ):
                    changed = True

        for milestone_id in updates.get("milestones", []) or []:
            normalized = self._normalize_flag(milestone_id)
            if not normalized:
                continue
            mutation = milestone_memory.get(normalized)
            if isinstance(mutation, MemoryMutation) and not mutation.is_noop():
                if self._apply_memory_mutation(
                    player_id,
                    mutation,
                    level=level,
                    source="task_milestone",
                    ref=normalized,
                ):
                    changed = True

        if changed:
            updates.setdefault("memory_flags", sorted(self._get_memory_set(player_id)))

    def get_player_memory(self, player_id: str) -> List[str]:
        self._ensure_player(player_id)
        return sorted(self._get_memory_set(player_id))

    # ============================================================
    # 关卡跳转逻辑（下一关）
    # ============================================================
    def get_next_level_id(self, current_level_id: Optional[str], player_id: Optional[str] = None):
        if player_id:
            recommendations = self.graph.recommend_next_levels(player_id, current_level_id, limit=1)
            if recommendations:
                return recommendations[0]["level_id"]

        canonical_current = self.graph.canonicalize_level_id(current_level_id)
        if not canonical_current:
            start_level = self.graph.get_start_level() or self.DEFAULT_ENTRY_LEVEL
            if start_level:
                return start_level
            all_levels = sorted(self.graph.all_levels())
            if all_levels:
                return all_levels[0]
            return self.DEFAULT_ENTRY_LEVEL

        return self.graph.bfs_next(canonical_current)

    def load_next_level_for_player(self, player_id: str) -> Dict[str, Any]:
        self._ensure_player(player_id)
        p = self.players[player_id]
        current_level = getattr(p["level"], "level_id", None)
        next_id = self.get_next_level_id(current_level, player_id=player_id)
        if not next_id:
            p["ended"] = True
            return {"mc": {"tell": "🎉 已经是最后一关了。"}}
        return self.load_level_for_player(player_id, next_id)

    def get_level_recommendations(self, player_id: str, current_level_id: Optional[str] = None, limit: int = 3):
        """Expose StoryGraph recommendations to API callers."""

        return self.graph.recommend_next_levels(player_id, current_level_id, limit=limit)

    # ============================================================
    # ⭐ 剧情舞台渲染器 v2
    # ============================================================
    def _build_stage_patch(self, level: Level) -> Dict[str, Any]:
        """
        根据关卡信息，构建一个“剧情舞台”的 world_patch：
        - 固定在安全坐标附近渲染平台 / 粒子 / 标题 / 天气 / 时间 / 背景音
        - 不包含 teleport（teleport 由上层统一控制）
        """
        meta = level.meta or {}
        mood = level.mood or {}
        base_mood = mood.get("base", "calm")
        chapter = meta.get("chapter")

        # 默认主题
        theme = "dawn"

        # 粗略按章节区间分主题
        if isinstance(chapter, int):
            if chapter <= 5:
                theme = "dawn"
            elif chapter <= 10:
                theme = "noon"
            elif chapter <= 20:
                theme = "dusk"
            else:
                theme = "night"

        # 情绪覆盖：如果 mood 里写得比较“压抑”就强制 night/dusk
        if isinstance(base_mood, str):
            b = base_mood.lower()
            if any(k in b for k in ["sad", "dark", "痛", "压抑", "night"]):
                theme = "night"
            elif any(k in b for k in ["hope", "light", "晨", "morning"]):
                theme = "dawn"

        # 根据 theme 决定舞台参数
        if theme == "dawn":
            time_of_day = "sunrise"
            weather = "clear"
            particle_type = "END_ROD"
            sound_type = "MUSIC_DISC_OTHERSIDE"
            platform_mat = "SMOOTH_QUARTZ"
            accent_color = "§e"
            subtitle_hint = "清晨的风把故事轻轻翻开。"
        elif theme == "noon":
            time_of_day = "day"
            weather = "clear"
            particle_type = "HAPPY_VILLAGER"
            sound_type = "MUSIC_DISC_BLOCKS"
            platform_mat = "OAK_PLANKS"
            accent_color = "§a"
            subtitle_hint = "阳光很亮，世界也变得清晰。"
        elif theme == "dusk":
            time_of_day = "sunset"
            weather = "dream_sky"
            particle_type = "CHERRY_LEAVES"
            sound_type = "MUSIC_DISC_FAR"
            platform_mat = "PINK_STAINED_GLASS"
            accent_color = "§d"
            subtitle_hint = "夕阳像一页慢慢合上的剧本。"
        else:  # night
            time_of_day = "night"
            weather = "dark_sky"
            particle_type = "SOUL"
            sound_type = "MUSIC_DISC_STRAD"
            platform_mat = "BLACK_STAINED_GLASS"
            accent_color = "§9"
            subtitle_hint = "夜色把没说完的话藏了起来。"

        title_main = f"{accent_color}《{level.title}》§r"
        title_sub = subtitle_hint

        stage_mc: Dict[str, Any] = {
            # 舞台平台：统一在安全点附近，由 SafeTeleport 决定精确坐标
            "build": {
                "shape": "platform",
                "material": platform_mat,
                "size": 6,
                # 让平台中心正好在玩家脚下（teleport 会传到平台上方）
                "safe_offset": {"dx": 0, "dy": -1, "dz": 0},
            },
            # 情绪氛围
            "weather": weather,
            "time": time_of_day,
            "particle": {
                "type": particle_type,
                "count": 80,
                "radius": 2.5,
            },
            "sound": {
                "type": sound_type,
                "volume": 0.8,
                "pitch": 1.0,
            },
            "title": {
                "main": title_main,
                "sub": title_sub,
                "fade_in": 10,
                "stay": 60,
                "fade_out": 20,
            },
        }

        return {"mc": stage_mc}

    # ============================================================
    # Scene metadata helpers
    # ============================================================
    def _attach_scene_metadata(self, mc_payload: Dict[str, Any], level: Level) -> None:
        """Enrich world patches with scene metadata consumed by the plugin."""

        if not isinstance(mc_payload, dict):
            return

        existing = mc_payload.get("_scene")
        scene_meta = dict(existing) if isinstance(existing, dict) else {}

        level_id = getattr(level, "level_id", None)
        if level_id and "level_id" not in scene_meta:
            scene_meta["level_id"] = level_id

        if "scene" not in scene_meta:
            scene_meta["scene"] = True

        scene_cfg = getattr(level, "scene", None)
        scene_world = getattr(scene_cfg, "world", None) if scene_cfg else None
        if scene_world and "scene_world" not in scene_meta:
            scene_meta["scene_world"] = scene_world

        if scene_cfg:
            skins = getattr(scene_cfg, "npc_skins", None)
            if skins and "npc_skins" not in scene_meta:
                packed = []
                for entry in skins:
                    if not isinstance(entry, dict):
                        continue
                    skin_id = entry.get("id")
                    skin_key = entry.get("skin")
                    if not skin_key:
                        continue
                    cleaned = {k: v for k, v in entry.items() if v is not None}
                    if skin_id:
                        cleaned["id"] = skin_id
                    packed.append(cleaned)
                if packed:
                    scene_meta["npc_skins"] = packed

        radius = self._estimate_scene_radius(mc_payload)
        if radius is not None and "radius" not in scene_meta:
            scene_meta["radius"] = radius

        scene_meta["ts"] = time.time()

        if scene_meta:
            mc_payload["_scene"] = scene_meta

    def _estimate_scene_radius(self, mc_payload: Dict[str, Any]) -> Optional[float]:
        """Best-effort radius guess so the client can size cleanup triggers."""

        build = mc_payload.get("build")
        if isinstance(build, dict):
            for key in ("radius", "size"):
                value = build.get(key)
                if isinstance(value, (int, float)):
                    return float(value)

        build_multi = mc_payload.get("build_multi")
        if isinstance(build_multi, list):
            for entry in build_multi:
                if not isinstance(entry, dict):
                    continue
                for key in ("radius", "size"):
                    value = entry.get(key)
                    if isinstance(value, (int, float)):
                        return float(value)
        return None

    # ============================================================
    # 加载指定关卡（带剧情舞台 + 安全传送）
    # ============================================================
    def load_level_for_player(self, player_id: str, level_id: str) -> Dict[str, Any]:
        """
        加载指定关卡：
        - 绑定到玩家状态
        - 注入 minimap / tree / messages
        - 生成「剧情舞台 patch」+ 场景 patch + 原始 bootstrap_patch
        - 强制附带一个全局 SafeTeleport 到安全坐标（永不掉海里）
        """
        self._ensure_player(player_id)
        level: Level = load_level(level_id)
        ensure_level_extensions(level, getattr(level, "_raw_payload", None))
        p = self.players[player_id]

        # 绑定关卡状态
        p["level"] = level
        p["level_loaded"] = False
        p["tree_state"] = level.tree
        p["ended"] = False
        p["messages"].clear()
        p["nodes"].clear()
        p.pop("emotional_profile", None)

        exit_profile = self._build_exit_profile(level)
        if exit_profile:
            p["exit_profile"] = exit_profile
        else:
            p.pop("exit_profile", None)

        self.graph.update_trajectory(
            player_id,
            level.level_id,
            "enter",
            {"title": level.title},
        )

        # minimap：进度记录 + 点亮节点
        self.minimap.enter_level(player_id, level.level_id)
        self.minimap.mark_unlocked(player_id, level.level_id)

        # ---------------------------------------------
        # 🎭 剧情舞台渲染器
        # ---------------------------------------------
        stage_patch = self._build_stage_patch(level)  # 只负责 build/天气/时间/粒子/音效/标题

        # ---------------------------------------------
        # 场景生成（SceneGenerator）
        # 依然允许布置 NPC / 装置等，但禁止改 teleport
        # ---------------------------------------------
        scene_patch = self.scene_gen.generate_for_level(level_id, level.__dict__) or {}
        scene_mc = dict(scene_patch.get("mc") or {})
        if "teleport" in scene_mc:
            # 不允许 SceneGenerator 再改玩家传送位置，避免掉进奇怪地方
            del scene_mc["teleport"]

        # ---------------------------------------------
        # 原始 bootstrap_patch（现在是 world_patch，来自 level.json）
        # ---------------------------------------------
        base_patch = dict(level.bootstrap_patch or {})
        base_mc = dict(base_patch.get("mc") or {})

        # 合并：场景 → 舞台 → world_patch
        # world_patch优先级最高（最后合并，覆盖前面的配置）
        def merge_mc(dst: Dict[str, Any], src: Dict[str, Any]):
            for k, v in (src or {}).items():
                if k in dst and isinstance(dst[k], dict) and isinstance(v, dict):
                    # 深度合并字典
                    dst[k] = {**dst[k], **v}
                else:
                    dst[k] = v

        # 临时存储world_patch的配置
        world_patch_mc = dict(base_mc)
        temp_mc = {}

        # 先合并场景和舞台
        merge_mc(temp_mc, scene_mc)
        merge_mc(temp_mc, stage_patch.get("mc", {}))

        # 最后用world_patch覆盖（保留world_patch中的所有配置）
        merge_mc(temp_mc, world_patch_mc)
        base_mc = temp_mc

        # ---------------------------------------------
        # 🌈 全局安全传送（固定出生点 + 平台）
        # ---------------------------------------------
        SAFE_X, SAFE_Y, SAFE_Z = 0, 120, 0
        safe_tp_mc = {
            "teleport": {
                "mode": "absolute",
                "x": SAFE_X,
                "y": SAFE_Y,
                "z": SAFE_Z,
                "safe_platform": {
                    "material": "GLASS",
                    "radius": 6,
                },
            },
            "tell": f"进入剧情：《{level.title}》",
        }
        merge_mc(base_mc, safe_tp_mc)
        self._attach_scene_metadata(base_mc, level)

        base_patch["mc"] = base_mc

        # ---------------------------------------------
        # 🤖 注册NPC行为到引擎
        # ---------------------------------------------
        spawn_data = base_mc.get("spawn")
        if spawn_data and "behaviors" in spawn_data:
            npc_engine.register_npc(level_id, spawn_data)

        # ============================================================
        # Phase 1.5 stubs
        # ============================================================
        if getattr(level, "scene", None):
            self.enter_level_with_scene(player_id, level)

        self.register_rule_listeners(level)
        self.inject_tasks(player_id, level)

        beats = getattr(level, "beats", [])
        if beats:
            first = beats[0]
            beat_id = getattr(first, "id", None) or "beat_0"
            self.advance_with_beat(player_id, beat_id)

        self._prepare_phase2_state(player_id, level)

        return base_patch

    # ============================================================
    # prompt 注入（第一次进入关卡时插入 system 提示词）
    # ============================================================
    def _inject_level_prompt_if_needed(self, player_id: str):
        p = self.players[player_id]
        level = p["level"]
        if not level or p["level_loaded"]:
            return
        
        # 构建关卡基础提示词
        base_prompt = build_level_prompt(level)
        
        # 添加NPC行为上下文
        npc_context = npc_engine.get_behavior_context_for_ai(level.level_id)
        if npc_context:
            base_prompt += f"\n\n{npc_context}"
        
        p["messages"].insert(
            0, {"role": "system", "content": base_prompt}
        )
        p["level_loaded"] = True

    def _build_exit_profile(self, level: Level) -> Optional[Dict[str, Any]]:
        exit_cfg = getattr(level, "exit", None)
        if not exit_cfg:
            return None

        aliases: List[str] = []
        alias_source = getattr(exit_cfg, "phrase_aliases", None)
        if isinstance(alias_source, (list, tuple)):
            aliases = [alias.strip() for alias in alias_source if isinstance(alias, str) and alias.strip()]
        elif isinstance(alias_source, str) and alias_source.strip():
            aliases = [token.strip() for token in alias_source.split("|") if token.strip()]

        if not aliases:
            aliases = list(self.DEFAULT_EXIT_ALIASES)
        else:
            lower_aliases = {alias.lower() for alias in aliases}
            for default_alias in self.DEFAULT_EXIT_ALIASES:
                if default_alias.lower() not in lower_aliases:
                    aliases.append(default_alias)

        profile: Dict[str, Any] = {
            "level_id": getattr(level, "level_id", None),
            "aliases": aliases,
            "return_spawn": getattr(exit_cfg, "return_spawn", None),
        }

        farewell = getattr(exit_cfg, "farewell", None)
        if isinstance(farewell, str) and farewell.strip():
            profile["farewell"] = farewell.strip()

        teleport_cfg = getattr(exit_cfg, "teleport", None)
        target: Optional[Dict[str, Any]] = None

        if teleport_cfg:
            x = getattr(teleport_cfg, "x", None)
            y = getattr(teleport_cfg, "y", None)
            z = getattr(teleport_cfg, "z", None)
            if None not in (x, y, z):
                target = {
                    "world": getattr(teleport_cfg, "world", None)
                    or getattr(getattr(level, "scene", None), "world", None),
                    "x": float(x),
                    "y": float(y),
                    "z": float(z),
                    "yaw": float(getattr(teleport_cfg, "yaw", 0.0) or 0.0),
                    "pitch": float(getattr(teleport_cfg, "pitch", 0.0) or 0.0),
                }

        if not target:
            spawn_name = getattr(exit_cfg, "return_spawn", None)
            if spawn_name and spawn_name in self.DEFAULT_RETURN_SPAWNS:
                target = dict(self.DEFAULT_RETURN_SPAWNS[spawn_name])

        if not target:
            default_target = self.DEFAULT_RETURN_SPAWNS.get("KunmingLakeHub")
            if default_target:
                target = dict(default_target)

        if target:
            profile["teleport"] = target

        return profile

    def _resolve_exit_target(self, exit_profile: Optional[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
        if not exit_profile:
            return self.DEFAULT_RETURN_SPAWNS.get("KunmingLakeHub")

        if isinstance(exit_profile, dict):
            teleport = exit_profile.get("teleport")
            if isinstance(teleport, dict) and teleport:
                return teleport

            spawn_name = exit_profile.get("return_spawn")
            if isinstance(spawn_name, str):
                resolved = self.DEFAULT_RETURN_SPAWNS.get(spawn_name)
                if resolved:
                    return resolved

        return self.DEFAULT_RETURN_SPAWNS.get("KunmingLakeHub")

    # ============================================================
    # 触发区（v2：暂时禁用螺旋触发器，避免随机传送）
    # ============================================================
    def _inject_spiral_triggers(self):
        trigger_engine.triggers.clear()
        # 如果将来想重新启用，可以在这里重新 append TriggerPoint
        print("[Trigger] spiral triggers disabled (StoryEngine v2.stage)")

    # ============================================================
    # 冷却判断（/world/apply 用）
    # ============================================================
    def should_advance(
        self,
        player_id: str,
        world_state: Dict[str, Any],
        action: Dict[str, Any],
    ) -> bool:
        """
        v2：永远允许推进剧情。
        冷却节奏交给 deepseek_agent.MIN_INTERVAL 控制。
        world_api.py 如果调用了 should_advance，现在总是 True。
        """
        self._ensure_player(player_id)
        # 仍然更新时间戳，方便以后需要统计
        now = time.time()
        p = self.players[player_id]
        say = action.get("say")
        if isinstance(say, str) and say.strip():
            p["last_say_time"] = now
        else:
            p["last_time"] = now
        return True

    # ============================================================
    # 主推进逻辑
    # ============================================================
    def advance(
        self, player_id: str, world_state: Dict[str, Any], action: Dict[str, Any]
    ) -> Tuple[Any, Dict[str, Any], Dict[str, Any]]:
        self._ensure_player(player_id)
        p = self.players[player_id]

        # 默认 free 模式
        self._ensure_free_mode_level(player_id)
        self._inject_level_prompt_if_needed(player_id)

        if p["ended"]:
            return None, None, {"mc": {"tell": "本关已结束。"}}

        beat_result = self._process_beat_progress(player_id, world_state, action)

        # 记录玩家发言
        say = action.get("say")
        if isinstance(say, str) and say.strip():
            p["messages"].append({"role": "user", "content": say})

        # 更新 minimap 上的位置
        vars_ = world_state.get("variables") or {}
        x, y, z = vars_.get("x", 0.0), vars_.get("y", 0.0), vars_.get("z", 0.0)
        self.minimap.update_player_pos(player_id, (x, y, z))

        # 触发器（目前为空，保留结构）
        trg = trigger_engine.check(player_id, x, y, z)
        if trg and trg.action == "load_level" and trg.level_id:
            patch = self.load_level_for_player(player_id, trg.level_id)
            node = {
                "title": "世界触发点",
                "text": f"你抵达了关键地点，关卡 {trg.level_id} 被唤醒。",
            }
            return None, node, patch

        # AI 决策
        ai_input = {
            "player_id": player_id,
            "player_action": action,
            "world_state": world_state,
            "recent_nodes": p["nodes"][-5:],
            "tree_state": p["tree_state"],
            "level_id": p["level"].level_id,
        }

        ai_result = deepseek_decide(ai_input, p["messages"])

        option = ai_result.get("option")
        node = ai_result.get("node")
        patch = ai_result.get("world_patch", {}) or {}
        mc_patch = patch.get("mc", {}) or {}

        # 更新 tree_state
        if option is not None:
            p["tree_state"] = {"last_option": option, "ts": time.time()}

        # 记录 AI 节点
        pending_nodes = p.setdefault("pending_nodes", [])

        primary_node = beat_result.get("node")

        if primary_node and node:
            pending_nodes.append(node)
        elif not primary_node:
            primary_node = node

        if primary_node:
            node = primary_node
            try:
                pending_nodes.remove(primary_node)
            except ValueError:
                pass
            p["nodes"].append(primary_node)
            p["messages"].append(
                {
                    "role": "assistant",
                    "content": f"{primary_node.get('title', '')}\n{primary_node.get('text', '')}".strip(),
                }
            )
            cur_level = p["level"].level_id
            self.minimap.mark_unlocked(player_id, cur_level)
        elif pending_nodes:
            node = pending_nodes.pop(0)
            p["nodes"].append(node)
            p["messages"].append(
                {
                    "role": "assistant",
                    "content": f"{node.get('title', '')}\n{node.get('text', '')}".strip(),
                }
            )
            cur_level = p["level"].level_id
            self.minimap.mark_unlocked(player_id, cur_level)

        patch = self._merge_patch(beat_result.get("world_patch"), patch)
        for pending in p.get("pending_patches", []):
            patch = self._merge_patch(pending, patch)
        p["pending_patches"] = []

        # 结束标记
        if mc_patch.get("ending"):
            p["ended"] = True

        # 时间戳（仅统计，不再作为 gating）
        now = time.time()
        if say and say.strip():
            p["last_say_time"] = now
        else:
            p["last_time"] = now

        quest_updates = quest_runtime.check_completion(p["level"], player_id)
        if quest_updates:
            self.apply_quest_updates(player_id, quest_updates)
            patch = self._merge_patch(quest_updates.get("world_patch"), patch)
            additional_nodes = quest_updates.get("nodes") or []
            if additional_nodes:
                p.setdefault("pending_nodes", []).extend(additional_nodes)
            completed = quest_updates.get("summary")
            if completed:
                p.setdefault("pending_nodes", []).append(completed)

        emotional_patch, emotional_summary = self._compose_emotional_patch(player_id)
        if emotional_summary:
            previous = p.get("emotional_profile") or {}
            changed = not previous or (
                previous.get("profile_id") != emotional_summary.get("profile_id")
                or previous.get("memory_digest") != emotional_summary.get("memory_digest")
            )
            if changed and emotional_patch:
                patch = self._merge_patch(emotional_patch, patch)
                emotional_summary["last_patch"] = deepcopy(emotional_patch)
            elif previous.get("last_patch"):
                emotional_summary["last_patch"] = deepcopy(previous["last_patch"])
            p["emotional_profile"] = emotional_summary
        else:
            p.pop("emotional_profile", None)

        return option, node, patch

    # ============================================================
    # Phase 2 helpers (private)
    # ============================================================
    def _prepare_phase2_state(self, player_id: str, level: Level) -> None:
        player_state = self.players[player_id]
        player_state.pop("pending_nodes", None)
        player_state.pop("pending_patches", None)

        beats = list(getattr(level, "beats", []) or [])
        beat_ids: List[str] = []
        beats_by_id: Dict[str, Any] = {}
        for idx, beat in enumerate(beats):
            beat_id = getattr(beat, "id", None) or f"beat_{idx:02d}"
            beat_ids.append(beat_id)
            beats_by_id[beat_id] = beat
        player_state["beat_state"] = {
            "order": beat_ids,
            "index": 0,
            "by_id": beats_by_id,
            "completed": set(),
            "event_map": {},
            "memory_locked": set(),
            "memory_locked_sources": {},
        }

        self.event_manager.unregister(player_id)

        quest_runtime.load_level_tasks(level, player_id)

        task_map: Dict[str, Any] = {}
        completion_memory: Dict[str, MemoryMutation] = {}
        milestone_memory: Dict[str, MemoryMutation] = {}
        for task in getattr(level, "tasks", []) or []:
            raw_task_id = getattr(task, "id", None) or ""
            task_id = self._normalize_flag(raw_task_id)
            if task_id:
                task_map[task_id] = task
                task_mutation = getattr(task, "completion_memory", None)
                if isinstance(task_mutation, MemoryMutation) and not task_mutation.is_noop():
                    completion_memory[task_id] = task_mutation
            for milestone_id, mutation in (getattr(task, "milestone_memory", {}) or {}).items():
                if not isinstance(mutation, MemoryMutation) or mutation.is_noop():
                    continue
                key = self._normalize_flag(milestone_id)
                if key:
                    milestone_memory[key] = mutation

        player_state["task_memory_map"] = task_map
        player_state["task_completion_memory"] = completion_memory
        player_state["milestone_memory"] = milestone_memory

        for beat_id in beat_ids:
            beat = beats_by_id.get(beat_id)
            if beat:
                self._register_trigger(player_id, level, beat_id, beat)

        initial_updates = self._auto_trigger_beats(player_id, level)
        for update in initial_updates:
            self._queue_beat_update(player_id, update)

    def _register_trigger(self, player_id: str, level: Level, beat_id: str, beat: Any) -> None:
        trigger_spec = self._parse_trigger(getattr(beat, "trigger", None))

        if trigger_spec["kind"] in {"near", "interact", "item_use"}:
            definition = {"type": trigger_spec["kind"]}
            if trigger_spec["value"]:
                key, value = self._parse_key_value(trigger_spec["value"])
                if key:
                    definition[key] = value
                else:
                    if trigger_spec["kind"] == "near":
                        definition["entity"] = trigger_spec["value"]
                    elif trigger_spec["kind"] == "interact":
                        definition["targets"] = [trigger_spec["value"]]
                    elif trigger_spec["kind"] == "item_use":
                        definition["items"] = [trigger_spec["value"]]

            event_id = f"{player_id}:{beat_id}"

            def _callback(payload: Dict[str, Any], pid: str = player_id, bid: str = beat_id) -> None:
                normalized = {
                    "event_type": payload.get("type"),
                    "target": payload.get("config", {}).get("target")
                    or payload.get("config", {}).get("entity")
                    or payload.get("config", {}).get("items"),
                    "meta": payload.get("config", {}),
                }
                quest_runtime.record_event(pid, normalized)
                update = self._activate_beat(pid, bid, level, source="event_manager", context={"payload": payload})
                if update:
                    self._queue_beat_update(pid, update)

            self.event_manager.register(player_id, event_id, definition, _callback)
            state = self.players[player_id].setdefault("beat_state", {})
            state.setdefault("event_map", {})[event_id] = beat_id

    def _auto_trigger_beats(self, player_id: str, level: Level) -> List[Dict[str, Any]]:
        updates: List[Dict[str, Any]] = []
        while True:
            beat = self._current_pending_beat(player_id)
            if not beat:
                break
            parsed = self._parse_trigger(getattr(beat, "trigger", None))
            requirement = getattr(beat, "memory_required", None)
            if not self._is_memory_satisfied(player_id, requirement):
                beat_state = self.players[player_id].setdefault("beat_state", {})
                beat_id = next(
                    (
                        identifier
                        for identifier, candidate in (beat_state.get("by_id") or {}).items()
                        if candidate is beat
                    ),
                    None,
                )
                if beat_id is not None:
                    beat_state.setdefault("memory_locked", set()).add(beat_id)
                    beat_state.setdefault("memory_locked_sources", {})[beat_id] = parsed.get("kind") or "auto"
                break
            if parsed["kind"] in {"auto", "on_enter", "immediate", ""}:
                beat_state = self.players[player_id].setdefault("beat_state", {})
                beat_id = next((identifier for identifier, candidate in (beat_state.get("by_id") or {}).items() if candidate is beat), None)
                if beat_id is None:
                    beat_id = getattr(beat, "id", None) or ""
                update = self._activate_beat(player_id, beat_id, level, source="auto", chain=False)
                if update:
                    updates.append(update)
            else:
                break
        return updates

    def _current_pending_beat(self, player_id: str) -> Optional[Any]:
        player_state = self.players.get(player_id, {})
        beat_state = player_state.get("beat_state") or {}
        order = beat_state.get("order") or []
        completed = beat_state.get("completed") or set()
        locked = beat_state.setdefault("memory_locked", set())
        locked_sources = beat_state.setdefault("memory_locked_sources", {})
        for beat_id in order:
            if beat_id not in completed:
                beat = beat_state.get("by_id", {}).get(beat_id)
                if not beat:
                    continue
                requirement = getattr(beat, "memory_required", None)
                if not self._is_memory_satisfied(player_id, requirement):
                    locked.add(beat_id)
                    locked_sources.setdefault(
                        beat_id,
                        self._parse_trigger(getattr(beat, "trigger", None)).get("kind") or "pending",
                    )
                    continue
                return beat
        return None

    def _process_beat_progress(
        self, player_id: str, world_state: Dict[str, Any], action: Dict[str, Any]
    ) -> Dict[str, Any]:
        player_state = self.players[player_id]
        beat_state = player_state.get("beat_state") or {}
        if not beat_state.get("order"):
            return {}

        updates: List[Dict[str, Any]] = []

        triggered_ids = self.event_manager.evaluate(player_id, action, world_state)
        for event_id in triggered_ids:
            beat_id = beat_state.get("event_map", {}).get(event_id)
            if beat_id:
                beat = beat_state.get("by_id", {}).get(beat_id)
                if beat:
                    updates.append(self._activate_beat(player_id, beat_id, self.players[player_id]["level"], source="event_manager"))

        say = action.get("say")
        if isinstance(say, str) and say.strip():
            updates.extend(self._check_keyword_triggers(player_id, say))

        result_patch: Dict[str, Any] = {}
        node: Optional[Dict[str, Any]] = None
        extra_nodes: List[Dict[str, Any]] = []

        for update in updates:
            if not update:
                continue
            result_patch = self._merge_patch(result_patch, update.get("world_patch"))
            primary = update.get("node")
            if primary and not node:
                node = primary
            elif primary:
                extra_nodes.append(primary)
            extra_nodes.extend(update.get("extra_nodes", []))
            self._queue_beat_update(player_id, update, include_primary=False, include_patch=False)

        return {
            "world_patch": result_patch,
            "node": node,
            "extra_nodes": extra_nodes,
        }

    def _check_keyword_triggers(self, player_id: str, say_text: str) -> List[Dict[str, Any]]:
        player_state = self.players[player_id]
        beat_state = player_state.get("beat_state") or {}
        if not beat_state:
            return []

        lowered = say_text.lower()
        updates: List[Dict[str, Any]] = []
        for beat_id in beat_state.get("order", []):
            if beat_id in beat_state.get("completed", set()):
                continue
            beat = beat_state.get("by_id", {}).get(beat_id)
            if not beat:
                continue
            parsed = self._parse_trigger(getattr(beat, "trigger", None))
            if parsed["kind"] in {"keyword", "say", "command"}:
                values = [value.strip() for value in (parsed["value"].split("|") if parsed["value"] else []) if value.strip()]
                if not values:
                    continue
                if any(value.lower() in lowered for value in values):
                    updates.append(self._activate_beat(player_id, beat_id, self.players[player_id]["level"], source="keyword"))

        return updates

    def _activate_beat(
        self,
        player_id: str,
        beat_id: str,
        level: Level,
        *,
        source: str,
        context: Optional[Dict[str, Any]] = None,
        chain: bool = True,
    ) -> Optional[Dict[str, Any]]:
        _ = context  # context reserved for future bridge metadata
        player_state = self.players[player_id]
        beat_state = player_state.get("beat_state") or {}
        if not beat_state:
            return None

        beats_by_id = beat_state.get("by_id", {})
        beat = beats_by_id.get(beat_id)
        if not beat:
            return None

        requirement = getattr(beat, "memory_required", None)
        if not self._is_memory_satisfied(player_id, requirement):
            beat_state.setdefault("memory_locked", set()).add(beat_id)
            beat_state.setdefault("memory_locked_sources", {})[beat_id] = source
            return None

        completed = beat_state.setdefault("completed", set())
        if beat_id in completed:
            return None

        completed.add(beat_id)
        beat_state.setdefault("memory_locked", set()).discard(beat_id)
        beat_state.setdefault("memory_locked_sources", {}).pop(beat_id, None)
        self.advance_with_beat(player_id, beat_id)

        event_id = f"{player_id}:{beat_id}"
        self.event_manager.unregister(player_id, event_id)

        beat_patch = self._resolve_scene_patch(level, beat)
        quest_update = quest_runtime.issue_tasks_on_beat(level, player_id, {"id": beat_id})
        rule_refs = list(getattr(beat, "rule_refs", []) or [])
        if rule_refs:
            quest_runtime.activate_rule_refs(level, player_id, rule_refs)

        extra_nodes = []
        if quest_update and quest_update.get("nodes"):
            extra_nodes.extend(quest_update["nodes"])

        base_node = {
            "title": f"剧情推进 · {beat_id}",
            "text": f"触发来源：{source}",
            "type": "beat",
            "beat_id": beat_id,
        }

        choice_node = self._prepare_choice_node(player_id, level, beat_id, beat)
        if choice_node:
            node = choice_node
            extra_nodes.append(base_node)
        else:
            node = base_node

        mc_patch = beat_patch.setdefault("mc", {})
        scene_meta: Dict[str, Any] = {
            "beat_id": beat_id,
            "source": source,
            "ts": time.time(),
            "level_id": getattr(level, "level_id", None),
        }
        if rule_refs:
            scene_meta["rule_refs"] = list(rule_refs)
        mc_patch.setdefault("_scene", scene_meta)

        if chain:
            chained_updates = self._auto_trigger_beats(player_id, level)
            for chained in chained_updates:
                beat_patch = self._merge_patch(chained.get("world_patch"), beat_patch)
                chained_node = chained.get("node")
                if chained_node:
                    extra_nodes.append(chained_node)
                extra_nodes.extend(chained.get("extra_nodes", []))

        mutation = getattr(beat, "memory_mutation", None)
        applied = False
        if isinstance(mutation, MemoryMutation) and not mutation.is_noop():
            applied = self._apply_memory_mutation(
                player_id,
                mutation,
                level=level,
                source="beat",
                ref=beat_id,
            )
        if not applied:
            fallback_mutation = MemoryMutation.from_parts(
                getattr(beat, "memory_set", None),
                getattr(beat, "memory_clear", None),
            )
            if not fallback_mutation.is_noop():
                self._apply_memory_mutation(
                    player_id,
                    fallback_mutation,
                    level=level,
                    source="beat",
                    ref=beat_id,
                )

        return {
            "world_patch": beat_patch,
            "node": node,
            "extra_nodes": extra_nodes,
        }

    def _prepare_choice_node(
        self,
        player_id: str,
        level: Level,
        beat_id: str,
        beat: Any,
    ) -> Optional[Dict[str, Any]]:
        raw_choices = getattr(beat, "choices", None)
        if not raw_choices:
            return None

        prepared: List[Dict[str, Any]] = []
        registry: Dict[str, Dict[str, Any]] = {}
        by_choice: Dict[str, Dict[str, Any]] = {}

        for index, choice in enumerate(raw_choices, start=1):
            cid = getattr(choice, "id", None)
            if not cid and isinstance(choice, dict):
                cid = choice.get("id") or choice.get("value")
            cid = (cid or f"choice_{beat_id}_{index}").strip()

            label = getattr(choice, "text", None)
            if not label and isinstance(choice, dict):
                label = choice.get("text") or choice.get("label")
            label = label or f"选项 {index}"

            rule_event = getattr(choice, "rule_event", None)
            if not rule_event and isinstance(choice, dict):
                rule_event = choice.get("rule_event") or choice.get("event")

            next_level = getattr(choice, "next_level", None)
            if not next_level and isinstance(choice, dict):
                next_level = choice.get("next") or choice.get("next_level")

            tags = list(getattr(choice, "tags", []) or [])
            if not tags and isinstance(choice, dict):
                raw_tags = choice.get("tags") or choice.get("affinity_tags") or []
                if isinstance(raw_tags, str):
                    tags = [token.strip() for token in raw_tags.split(",") if token.strip()]
                elif isinstance(raw_tags, list):
                    tags = [str(token).strip() for token in raw_tags if str(token).strip()]

            entry = {
                "id": cid,
                "label": label,
                "index": index,
                "rule_event": rule_event,
                "next_level": next_level,
                "tags": tags,
            }
            prepared.append(entry)

            snapshot = {
                "choice_id": cid,
                "label": label,
                "rule_event": rule_event,
                "index": index,
                "beat_id": beat_id,
                "level_id": getattr(level, "level_id", None),
                "next_level": next_level,
                "tags": tags,
                "ts": time.time(),
            }
            if rule_event:
                registry[rule_event.strip().lower()] = snapshot
            by_choice[cid] = snapshot

        if not prepared:
            return None

        state = self.players[player_id]
        choice_registry = state.setdefault("choice_registry", {})
        choice_registry.update(registry)
        state.setdefault("choice_registry_by_id", {}).update(by_choice)
        state.setdefault("choice_sessions", {})[beat_id] = {
            "beat_id": beat_id,
            "level_id": getattr(level, "level_id", None),
            "choices": prepared,
        }

        prompt = getattr(beat, "choice_prompt", None) or "你决定怎么做？"
        return {
            "type": "story_choice",
            "title": prompt,
            "prompt": prompt,
            "beat_id": beat_id,
            "level_id": getattr(level, "level_id", None),
            "choices": prepared,
        }

    def _queue_beat_update(
        self,
        player_id: str,
        update: Optional[Dict[str, Any]],
        *,
        include_primary: bool = True,
        include_patch: bool = True,
    ) -> None:
        if not update:
            return

        player_state = self.players[player_id]
        if include_patch and update.get("world_patch"):
            player_state.setdefault("pending_patches", []).append(update["world_patch"])

        nodes_to_store: List[Dict[str, Any]] = []
        if include_primary and update.get("node"):
            nodes_to_store.append(update["node"])
        nodes_to_store.extend(update.get("extra_nodes", []) or [])

        if nodes_to_store:
            player_state.setdefault("pending_nodes", []).extend(nodes_to_store)

    def _record_story_choice(self, player_id: str, event_type: str, payload: Dict[str, Any]) -> None:
        player_state = self.players.get(player_id)
        if not player_state:
            return

        normalized = (event_type or "").strip().lower()
        registry = player_state.setdefault("choice_registry", {})
        by_id = player_state.setdefault("choice_registry_by_id", {})

        snapshot = registry.pop(normalized, None)
        choice_id = None

        if not snapshot:
            choice_id = (payload.get("choice_id") or payload.get("id") or "").strip()
            if choice_id:
                snapshot = by_id.pop(choice_id, None)
        else:
            choice_id = snapshot.get("choice_id")
            if choice_id:
                by_id.pop(choice_id, None)

        if not snapshot:
            snapshot = {
                "choice_id": (payload.get("choice_id") or payload.get("id") or "").strip(),
                "label": payload.get("choice_label") or payload.get("label"),
                "rule_event": normalized or event_type,
                "beat_id": payload.get("beat_id"),
                "level_id": payload.get("level_id"),
                "next_level": payload.get("next_level"),
                "tags": payload.get("tags") or [],
            }
        else:
            snapshot = dict(snapshot)
            if payload.get("choice_label"):
                snapshot["label"] = payload.get("choice_label")
            if payload.get("choice_id"):
                snapshot["choice_id"] = payload.get("choice_id")
            if payload.get("next_level") and not snapshot.get("next_level"):
                snapshot["next_level"] = payload.get("next_level")
            if payload.get("tags") and not snapshot.get("tags"):
                snapshot["tags"] = payload.get("tags")
            snapshot["rule_event"] = normalized or event_type

        if not snapshot.get("choice_id") and choice_id:
            snapshot["choice_id"] = choice_id

        level = player_state.get("level")
        if level and not snapshot.get("level_id"):
            snapshot["level_id"] = getattr(level, "level_id", None)

        snapshot["ts"] = time.time()
        snapshot.setdefault("source", "player_choice")

        sessions = player_state.get("choice_sessions") or {}
        beat_id = snapshot.get("beat_id")
        if beat_id and beat_id in sessions:
            sessions.pop(beat_id, None)

        history = player_state.setdefault("choice_history", [])
        history.append(snapshot)
        player_state["last_choice"] = dict(snapshot)

        level_id = snapshot.get("level_id")
        self.graph.update_trajectory(player_id, level_id, "choice", snapshot)

    def _resolve_scene_patch(self, level: Level, beat: Any) -> Dict[str, Any]:
        scene_key = getattr(beat, "scene_patch", None)
        patches = getattr(level, "scene_patches", None)
        if isinstance(patches, dict) and scene_key in patches:
            candidate = patches.get(scene_key)
            if isinstance(candidate, dict):
                return dict(candidate)
        if scene_key and scene_key in CINEMATIC_LIBRARY:
            return deepcopy(CINEMATIC_LIBRARY[scene_key])
        if scene_key:
            return {"mc": {"tell": f"{level.title} · 场景变化：{scene_key}"}}
        return {}

    @staticmethod
    def _merge_patch(primary: Optional[Dict[str, Any]], secondary: Optional[Dict[str, Any]]) -> Dict[str, Any]:
        if not primary and not secondary:
            return {}
        if not secondary:
            return dict(primary or {})
        if not primary:
            return dict(secondary or {})

        merged = dict(secondary or {})
        for key, value in (primary or {}).items():
            if key == "mc" and isinstance(value, dict):
                existing = merged.get("mc")
                if isinstance(existing, dict):
                    merged["mc"] = {**existing, **value}
                else:
                    merged["mc"] = dict(value)
            else:
                merged[key] = value
        return merged

    def _compose_emotional_patch(self, player_id: str) -> Tuple[Dict[str, Any], Optional[Dict[str, Any]]]:
        player_state = self.players[player_id]
        level = player_state.get("level")
        if not level:
            return {}, None

        config: Optional[EmotionalWorldPatchConfig] = getattr(level, "emotional_world_patch", None)
        if not isinstance(config, EmotionalWorldPatchConfig) or config.is_empty():
            return {}, None

        flags = self._get_memory_set(player_id)
        patch = config.compose_patch(flags)
        descriptor = config.describe(flags)

        summary = {
            "profile_id": descriptor.get("profile_id") or "default",
            "label": descriptor.get("label") or descriptor.get("profile_id") or "default",
            "tone": descriptor.get("tone"),
            "level_id": getattr(level, "level_id", None),
            "level_title": getattr(level, "title", None),
            "memory_flags": sorted(flags),
            "memory_digest": "|".join(sorted(flags)),
            "timestamp": time.time(),
        }

        mc_payload = patch.get("mc") if isinstance(patch, dict) else None
        if isinstance(mc_payload, dict):
            summary["patch_keys"] = sorted(mc_payload.keys())
        else:
            summary["patch_keys"] = []

        return patch, summary

    def get_emotional_profile(self, player_id: str) -> Dict[str, Any]:
        self._ensure_player(player_id)
        profile = self.players[player_id].get("emotional_profile")
        if not profile:
            patch, summary = self._compose_emotional_patch(player_id)
            if summary:
                if patch:
                    summary["last_patch"] = deepcopy(patch)
                self.players[player_id]["emotional_profile"] = summary
                profile = summary
        if not profile:
            return {}
        snapshot = dict(profile)
        last_patch = snapshot.get("last_patch")
        if isinstance(last_patch, dict):
            snapshot["last_patch"] = deepcopy(last_patch)
        return snapshot

    @staticmethod
    def _parse_trigger(raw: Optional[str]) -> Dict[str, str]:
        if not raw:
            return {"kind": "", "value": ""}
        token = raw.strip().lower()
        if ":" in token:
            kind, value = token.split(":", 1)
            return {"kind": kind.strip(), "value": value.strip()}
        return {"kind": token, "value": ""}

    @staticmethod
    def _parse_key_value(raw: str) -> Tuple[Optional[str], Optional[str]]:
        if "=" not in raw:
            return None, None
        key, value = raw.split("=", 1)
        return key.strip(), value.strip()

    def _handle_rule_catalyst(self, player_id: str, payload: Dict[str, Any]) -> None:
        beat_state = self.players.get(player_id, {}).get("beat_state") or {}
        matches: List[str] = []
        event_type = str(payload.get("event_type") or "").lower()
        quest_event = str(payload.get("payload", {}).get("quest_event") or "").lower()

        if event_type.startswith("choice") or payload.get("choice_id") or payload.get("payload", {}).get("choice_id"):
            choice_payload = dict(payload.get("payload") or {})
            choice_payload.setdefault("choice_id", payload.get("choice_id"))
            choice_payload.setdefault("choice_label", payload.get("choice_label"))
            choice_payload.setdefault("beat_id", payload.get("beat_id"))
            choice_payload.setdefault("level_id", payload.get("level_id"))
            choice_payload.setdefault("rule_event", event_type)
            self._record_story_choice(player_id, event_type, choice_payload)

        for beat_id, beat in (beat_state.get("by_id") or {}).items():
            if beat_id in (beat_state.get("completed") or set()):
                continue
            refs = [ref.lower() for ref in getattr(beat, "rule_refs", []) or []]
            if not refs:
                continue
            if event_type and event_type in refs:
                matches.append(beat_id)
                continue
            if quest_event and quest_event in refs:
                matches.append(beat_id)

        level = self.players.get(player_id, {}).get("level")
        if not level:
            return
        for bid in matches:
            update = self._activate_beat(player_id, bid, level, source="rule_event", context=payload)
            if update:
                self._queue_beat_update(player_id, update)

    # ============================================================
    # 自由模式关卡（无正式 level 时的 fallback）
    # ============================================================
    def _ensure_free_mode_level(self, player_id: str):
        p = self.players[player_id]
        if p["level"] is None:

            class FreeLevel:
                level_id = "flagship_free"
                tree = None
                bootstrap_patch = {"mc": {"tell": "🌌 进入心悦自由宇宙模式。"}}

            p["level"] = FreeLevel()
            p["level_loaded"] = True


story_engine = StoryEngine()