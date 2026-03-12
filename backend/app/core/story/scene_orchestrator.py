"""Scene orchestration utilities for level schema v2."""

from __future__ import annotations

import time
from copy import deepcopy
from typing import Any, Dict, Optional, List, Tuple

from app.core.story.story_loader import Level


class SceneOrchestrator:
    """Manages the lifecycle of cinematic scenes described by level v2."""

    def __init__(self) -> None:
        self._active: Dict[str, Dict[str, Any]] = {}

    def load_scene(self, level: Level, player_id: str) -> Dict[str, Any]:
        """Prepare and return the initial world patch for the given level scene.

        This method should cache any per-player scene metadata, merge static
        `scene.world_on_enter` instructions, and emit the patch that needs to be
        applied by `WorldPatchExecutor` before the player starts interacting with
        the narrative. The returned dict must be safe to pass directly to
        `world_engine.apply_patch`.
        """

        scene = level.scene or {}
        mc_patch: Dict[str, Any] = {}
        active = self._ensure_active_state(player_id)

        schema_patch, cleanup_patch = self._build_scene_schema(scene)
        if schema_patch:
            self._merge_mc(mc_patch, schema_patch.get("mc"))
        else:
            active.pop("scene_cleanup", None)

        if cleanup_patch:
            active["scene_cleanup"] = cleanup_patch
        else:
            active.pop("scene_cleanup", None)

        world_on_enter = scene.get("world_on_enter")
        if isinstance(world_on_enter, dict):
            self._merge_mc(mc_patch, self._coerce_mc_payload(world_on_enter))

        # 支持 scene.build / scene.spawn 顶层字段
        for key in ("build", "build_multi", "spawn"):
            if key in scene:
                self._merge_mc(mc_patch, {key: scene[key]})

        layout = scene.get("world_layout") or {}
        if isinstance(layout, dict):
            for key in ("build", "build_multi", "spawn", "spawn_multi"):
                value = layout.get(key)
                if value:
                    self._merge_mc(mc_patch, {key: value})

        active.update({
            "level_id": level.level_id,
            "scene": scene,
        })

        world_on_exit = scene.get("world_on_exit")
        if isinstance(world_on_exit, dict):
            active["scene_exit"] = {"mc": self._coerce_mc_payload(world_on_exit)}
        else:
            active.pop("scene_exit", None)

        if scene.get("signature_event"):
            active["signature_consumed"] = False

        return self._wrap_patch(mc_patch)

    def register_level(self, player_id: str, level: Level, beats: List[Dict[str, Any]]) -> None:
        """Record beat lifecycle summaries for diagnostic and orchestration use."""

        state = self._ensure_active_state(player_id)
        state["level_id"] = level.level_id
        beat_map: Dict[str, Dict[str, Any]] = {}
        for index, beat in enumerate(beats):
            beat_id = beat.get("id") or f"beat_{index:02d}"
            beat_map[beat_id] = {
                "index": index,
                "status": "locked",
                "definition": beat,
                "history": [],
            }
        state["beats"] = beat_map
        state["beats_completed"] = False
        state["last_active_beat"] = None

    def unload_scene(self, player_id: str) -> Optional[Dict[str, Any]]:
        """Generate teardown actions when a player leaves the current scene.

        Implementations can revert builds, despawn temporary entities, or return
        a teleport patch back to the main world. Returning ``None`` means no
        additional cleanup is required on the backend side.
        """

        state = self._active.get(player_id)
        if not state:
            return None

        state["unloaded_at"] = time.time()

        cleanup_patch = state.pop("scene_cleanup", None)
        exit_patch = state.get("scene_exit")

        combined: Dict[str, Any] = {}
        if isinstance(cleanup_patch, dict):
            self._merge_mc(combined, cleanup_patch.get("mc"))
        if isinstance(exit_patch, dict):
            self._merge_mc(combined, exit_patch.get("mc"))

        return self._wrap_patch(combined)

    def preview_unload_scene(self, player_id: str) -> Optional[Dict[str, Any]]:
        """Return a non-destructive snapshot of the teardown patch for a scene."""

        state = self._active.get(player_id)
        if not state:
            return None

        cleanup_patch = state.get("scene_cleanup")
        exit_patch = state.get("scene_exit")

        combined: Dict[str, Any] = {}
        if isinstance(cleanup_patch, dict):
            self._merge_mc(combined, cleanup_patch.get("mc"))
        if isinstance(exit_patch, dict):
            self._merge_mc(combined, exit_patch.get("mc"))

        return self._wrap_patch(combined)

    def apply_beat_effect(self, beat: Dict[str, Any], player_id: str) -> Optional[Dict[str, Any]]:
        """Translate a narrative beat into a world patch.

        The ``beat`` argument follows ``narrative.beats`` entries. Implementations
        should inspect its world effect hints, update internal state so repeated
        beats are not replayed, and optionally return an incremental patch to
        visualize the beat (weather change, particles, etc.).
        """

        if not isinstance(beat, dict):
            return None

        self._mark_beat_started(player_id, beat)

        world_reaction = beat.get("world_reaction")
        if not isinstance(world_reaction, dict):
            return None

        mc_patch = self._convert_world_reaction(world_reaction)
        if not mc_patch:
            return None

        return self._wrap_patch(mc_patch)

    def on_beat_completed(self, player_id: str, beat: Dict[str, Any]) -> None:
        """Mark a beat as completed for tracking purposes."""

        state = self._ensure_active_state(player_id)
        beats = state.get("beats") or {}
        beat_id = beat.get("id")
        entry = beats.get(beat_id)
        if entry is None:
            return

        entry["status"] = "completed"
        entry["history"].append({"event": "completed", "ts": time.time()})
        entry["last_completed_at"] = time.time()
        state["last_active_beat"] = None

    def on_all_beats_completed(self, player_id: str) -> None:
        """Mark all beats as completed for the active level."""

        state = self._ensure_active_state(player_id)
        state["beats_completed"] = True
        state["beats_completed_at"] = time.time()

    def apply_signature_event(self, level: Level, player_id: str) -> Optional[Dict[str, Any]]:
        """Activate the level's signature event once its trigger conditions are met.

        Implementations receive the full ``Level`` instance so they can read
        both the structured ``scene.signature_event`` definition and any other
        contextual data required to stage the cinematic. Returning ``None``
        means no additional patch is necessary at this moment.
        """

        state = self._ensure_active_state(player_id)
        if state.get("signature_consumed"):
            return None

        scene = (level.scene or {})
        event = scene.get("signature_event")
        if not isinstance(event, dict):
            return None

        mc_patch: Dict[str, Any] = {}

        world_effect = event.get("world_effect")
        if isinstance(world_effect, dict):
            self._merge_mc(mc_patch, self._convert_world_reaction(world_effect))

        for step in event.get("mc_sequence", []) or []:
            if not isinstance(step, dict):
                continue
            converted = self._convert_sequence_step(step)
            if converted:
                self._merge_mc(mc_patch, converted)

        description = event.get("description")
        if description:
            self._merge_mc(mc_patch, {"tell": description})

        state["signature_consumed"] = True
        return self._wrap_patch(mc_patch)

    def teleport_to_entry(self, level: Level, player_id: str) -> Optional[Dict[str, Any]]:
        """Return a safe teleport patch moving the player to ``scene.entry_point``.

        Implementations can embed safeguards such as temporary platforms or
        fallback coordinates if the target chunk is not loaded. Returning ``None``
        indicates the caller should rely on existing stage teleport logic.
        """

        scene = level.scene or {}
        entry = scene.get("entry_point")
        if not isinstance(entry, dict):
            return None

        x = entry.get("x")
        y = entry.get("y")
        z = entry.get("z")
        if x is None or y is None or z is None:
            return None

        teleport_patch = {
            "teleport": {
                "mode": "absolute",
                "x": x,
                "y": y,
                "z": z,
            }
        }

        world = entry.get("world")
        if isinstance(world, str):
            teleport_patch["teleport"]["world"] = world

        return self._wrap_patch(teleport_patch)

    def exit_to_mainline(self, player_id: str) -> Dict[str, Any]:
        """Provide the full patch required to exit the scene and resume mainline play.

        This method must produce everything needed to restore the player's state
        to the central hub (昆明湖), including teleport instructions and optional
        feedback messages. It should also clear any cached scene metadata so that
        a subsequent re-entry starts from a clean slate.
        """

        state = self._active.get(player_id) or {}
        scene = state.get("scene") if isinstance(state, dict) else {}
        return_to = (scene or {}).get("return_to")

        # 默认回到昆明湖中心
        patch = {
            "teleport": {
                "mode": "absolute",
                "x": 0,
                "y": 120,
                "z": 0,
            },
            "tell": "你已回到昆明湖。",
        }

        if isinstance(return_to, dict):
            target = return_to
            coords = {k: target.get(k) for k in ("x", "y", "z")}
            if all(v is not None for v in coords.values()):
                patch["teleport"].update(coords)  # type: ignore[arg-type]
            if isinstance(target.get("world"), str):
                patch["teleport"]["world"] = target["world"]
            if isinstance(target.get("tell"), str):
                patch["tell"] = target["tell"]
        elif isinstance(return_to, str) and return_to.strip():
            patch["teleport"]["world"] = return_to.strip()

        self._active.pop(player_id, None)

        return self._wrap_patch(patch)

    def get_active_scene(self, player_id: str) -> Optional[Dict[str, Any]]:
        """Expose cached scene metadata for diagnostics or AI prompts.

        Implementations may return a summary dictionary describing the currently
        loaded scene, active beats, or pending events. When no scene is active,
        ``None`` should be returned.
        """

        state = self._active.get(player_id)
        if not state:
            return None

        beats = state.get("beats")
        if beats:
            summary: Dict[str, Any] = {
                "level_id": state.get("level_id"),
                "beats_completed": state.get("beats_completed", False),
                "beats": {
                    beat_id: {
                        "status": info.get("status"),
                        "index": info.get("index"),
                        "last_started_at": info.get("last_started_at"),
                        "last_completed_at": info.get("last_completed_at"),
                    }
                    for beat_id, info in beats.items()
                },
            }
            return summary

        return {k: v for k, v in state.items() if k in {"level_id", "scene"}}

    # ------------------------------------------------------------------
    # Internal utilities
    # ------------------------------------------------------------------

    def _build_scene_schema(self, scene: Dict[str, Any]) -> Tuple[Dict[str, Any], Dict[str, Any]]:
        if not isinstance(scene, dict) or not scene:
            return {}, {}

        mc_patch: Dict[str, Any] = {}
        cleanup_mc: Dict[str, Any] = {}

        spawn = self._normalize_spawn(scene.get("spawn"))
        if spawn:
            mc_patch["teleport"] = spawn

        weather = scene.get("weather")
        if isinstance(weather, str) and weather:
            mc_patch["weather"] = weather
            cleanup_mc.setdefault("weather", "clear")

        time_of_day = scene.get("time")
        if isinstance(time_of_day, str) and time_of_day:
            mc_patch["time"] = time_of_day
            cleanup_mc.setdefault("time", "day")

        biome_cfg = self._normalize_biome(scene.get("biome"))
        if biome_cfg:
            mc_patch["biome"] = biome_cfg
            reset_name = biome_cfg.get("reset_to") or "PLAINS"
            cleanup_mc["biome"] = {
                "name": reset_name,
                "radius": biome_cfg.get("radius", 24),
            }

        prefabs = scene.get("prefabs")
        build_list, cleanup_list = self._compile_prefabs(prefabs)
        if build_list:
            mc_patch["build_multi"] = build_list
        if cleanup_list:
            cleanup_mc.setdefault("build_multi", []).extend(cleanup_list)

        effects = scene.get("effects")
        if isinstance(effects, dict):
            particle_cfg = effects.get("particle") or effects.get("particles")
            if particle_cfg:
                mc_patch["particle"] = particle_cfg

            sound_cfg = effects.get("sound")
            if sound_cfg:
                mc_patch["sound"] = sound_cfg
                cleanup_mc.setdefault("sound", {"type": "STOP_ALL"})

            light_cfg = effects.get("light")
            if light_cfg:
                mc_patch["light"] = light_cfg

            fog_cfg = effects.get("fog")
            if fog_cfg:
                mc_patch["fog"] = fog_cfg
                cleanup_mc["fog"] = "clear"

            title_cfg = effects.get("title")
            if title_cfg:
                mc_patch["title"] = title_cfg

            actionbar_cfg = effects.get("actionbar")
            if actionbar_cfg:
                mc_patch["actionbar"] = actionbar_cfg

            tell_cfg = effects.get("tell")
            if tell_cfg:
                mc_patch["tell"] = tell_cfg

        cleanup_patch = {"mc": cleanup_mc} if cleanup_mc else {}
        scene_patch = {"mc": mc_patch} if mc_patch else {}
        return scene_patch, cleanup_patch

    def _normalize_spawn(self, spawn: Any) -> Optional[Dict[str, Any]]:
        if isinstance(spawn, (list, tuple)) and len(spawn) >= 3:
            x, y, z = spawn[:3]
            return {
                "mode": "absolute",
                "x": float(x),
                "y": float(y),
                "z": float(z),
            }

        if isinstance(spawn, dict):
            teleport: Dict[str, Any] = {
                "mode": spawn.get("mode", "absolute"),
            }
            for key in ("x", "y", "z", "yaw", "pitch", "world"):
                if key in spawn and spawn[key] is not None:
                    teleport[key] = spawn[key]

            safe_platform = spawn.get("safe_platform")
            if isinstance(safe_platform, dict):
                teleport["safe_platform"] = deepcopy(safe_platform)

            return teleport

        return None

    def _normalize_biome(self, biome: Any) -> Optional[Dict[str, Any]]:
        if isinstance(biome, str) and biome.strip():
            return {
                "name": biome.strip(),
                "radius": 24,
            }

        if isinstance(biome, dict):
            name = biome.get("name") or biome.get("id")
            if not isinstance(name, str) or not name.strip():
                return None
            result: Dict[str, Any] = {"name": name.strip()}
            if "radius" in biome:
                result["radius"] = biome["radius"]
            if "blend" in biome:
                result["blend"] = biome["blend"]
            if "reset_to" in biome and isinstance(biome["reset_to"], str):
                result["reset_to"] = biome["reset_to"].strip()
            return result

        return None

    def _compile_prefabs(self, prefabs: Any) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
        if not isinstance(prefabs, list):
            return [], []

        build_multi: List[Dict[str, Any]] = []
        cleanup_multi: List[Dict[str, Any]] = []
        for entry in prefabs:
            if not isinstance(entry, dict):
                continue

            base = entry.get("build") if isinstance(entry.get("build"), dict) else entry
            build_entry = deepcopy({k: v for k, v in base.items() if k in {
                "shape",
                "material",
                "size",
                "offset",
                "safe_offset",
                "center",
                "start",
                "end",
                "radius",
                "radius_x",
                "radius_z",
                "height",
                "length",
                "direction",
                "spacing",
            }})

            if not build_entry.get("shape"):
                build_entry["shape"] = entry.get("shape", "platform")
            if not build_entry.get("material"):
                build_entry["material"] = entry.get("material", "SMOOTH_QUARTZ")

            if not build_entry:
                continue

            build_multi.append(build_entry)
            cleanup_entry = self._build_prefab_cleanup(build_entry)
            if cleanup_entry:
                cleanup_multi.append(cleanup_entry)

        return build_multi, cleanup_multi

    def _build_prefab_cleanup(self, build_entry: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        shape = str(build_entry.get("shape") or "").lower()
        if not shape:
            return None

        removable_shapes = {
            "platform",
            "line",
            "cylinder",
            "grid",
            "heart_pad",
            "wall",
            "floating_platform",
            "sphere",
            "hollow_sphere",
            "hollow_cube",
            "fence_ring",
            "race_track",
            "tunnel",
            "light_line",
        }

        if shape not in removable_shapes:
            return None

        cleanup = deepcopy(build_entry)
        cleanup["material"] = "AIR"
        return cleanup

    def _ensure_active_state(self, player_id: str) -> Dict[str, Any]:
        state = self._active.setdefault(player_id, {})
        state.setdefault("signature_consumed", False)
        return state

    def _mark_beat_started(self, player_id: str, beat: Dict[str, Any]) -> None:
        state = self._ensure_active_state(player_id)
        beats = state.get("beats") or {}
        beat_id = beat.get("id")
        entry = beats.get(beat_id)
        if entry is None:
            return

        if entry.get("status") != "active":
            entry["status"] = "active"
            entry["history"].append({"event": "started", "ts": time.time()})
            entry["last_started_at"] = time.time()
            state["last_active_beat"] = beat_id

    @staticmethod
    def _wrap_patch(mc_patch: Dict[str, Any]) -> Dict[str, Any]:
        return {"mc": mc_patch} if mc_patch else {}

    @staticmethod
    def _coerce_mc_payload(payload: Dict[str, Any]) -> Dict[str, Any]:
        mc_payload: Dict[str, Any] = {}
        for key, value in payload.items():
            mc_payload[key] = value
        return mc_payload

    @staticmethod
    def _merge_mc(target: Dict[str, Any], addition: Optional[Dict[str, Any]]) -> None:
        if not addition:
            return

        list_keys = {"build", "build_multi", "spawn", "spawn_multi", "tell"}

        for key, value in addition.items():
            if value is None:
                continue

            if key in list_keys:
                existing = target.get(key)
                if isinstance(existing, list):
                    if isinstance(value, list):
                        existing.extend(value)
                    else:
                        existing.append(value)
                elif existing is not None:
                    target[key] = [existing] + (value if isinstance(value, list) else [value])
                else:
                    target[key] = list(value) if isinstance(value, list) else [value]
            elif isinstance(value, dict) and isinstance(target.get(key), dict):
                target[key] = {**target[key], **value}
            else:
                target[key] = value

    @staticmethod
    def _convert_world_reaction(data: Dict[str, Any]) -> Dict[str, Any]:
        mc_patch: Dict[str, Any] = {}

        weather = data.get("weather")
        if isinstance(weather, str):
            mc_patch["weather"] = weather

        time_val = data.get("time")
        if isinstance(time_val, str):
            mc_patch["time"] = time_val

        particle = data.get("particle")
        if particle:
            if isinstance(particle, dict):
                mc_patch["particle"] = particle
            elif isinstance(particle, str):
                mc_patch["particle"] = {"type": particle}

        sound = data.get("sound")
        if sound:
            if isinstance(sound, dict):
                mc_patch["sound"] = sound
            elif isinstance(sound, str):
                mc_patch["sound"] = {"type": sound}

        light = data.get("light")
        if light:
            mc_patch["light"] = light

        actionbar = data.get("actionbar")
        if isinstance(actionbar, str):
            mc_patch["actionbar"] = actionbar

        tell = data.get("tell")
        if tell:
            mc_patch["tell"] = tell

        build = data.get("build")
        if build:
            mc_patch["build"] = build

        spawn = data.get("spawn")
        if spawn:
            mc_patch["spawn"] = spawn

        return mc_patch

    def _convert_sequence_step(self, step: Dict[str, Any]) -> Dict[str, Any]:
        step_type = step.get("type")
        if not isinstance(step_type, str):
            return {}

        mc_patch: Dict[str, Any] = {}
        if step_type == "sound":
            sound = {
                "type": step.get("sound"),
                "volume": step.get("volume"),
                "pitch": step.get("pitch"),
            }
            sound = {k: v for k, v in sound.items() if v is not None}
            if sound.get("type"):
                mc_patch["sound"] = sound
        elif step_type == "particle":
            particle = {
                "type": step.get("particle"),
                "count": step.get("count"),
                "radius": step.get("radius"),
            }
            particle = {k: v for k, v in particle.items() if v is not None}
            if particle.get("type"):
                mc_patch["particle"] = particle
        elif step_type in {"build", "build_multi", "spawn", "spawn_multi"}:
            payload = step.get(step_type) or step.get("steps")
            if payload:
                mc_patch[step_type] = payload
        elif step_type == "light":
            light_patch = {
                "mode": step.get("mode"),
                "color": step.get("color"),
                "duration": step.get("duration"),
            }
            light_patch = {k: v for k, v in light_patch.items() if v is not None}
            if light_patch:
                mc_patch["light"] = light_patch

        return mc_patch

