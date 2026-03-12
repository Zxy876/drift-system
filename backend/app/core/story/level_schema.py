"""Phase 1.5 level schema scaffolding.

This module is intentionally lightweight and backward compatible. It exposes
dataclasses that model the planned extensions without forcing the existing
`story_loader` implementation to change immediately. Callers can opt-in by
attaching these structures to legacy level instances.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, Iterable, List, Optional
from copy import deepcopy


# ---------------------------------------------------------------------------
# Scene configuration
# ---------------------------------------------------------------------------


@dataclass
class SceneTeleport:
    """Absolute teleport target for a scene."""

    x: Optional[float] = None
    y: Optional[float] = None
    z: Optional[float] = None
    yaw: Optional[float] = None
    pitch: Optional[float] = None

    @staticmethod
    def from_dict(data: Optional[Dict[str, Any]]) -> "SceneTeleport":
        if not isinstance(data, dict):
            return SceneTeleport()
        return SceneTeleport(
            x=_coerce_float(data.get("x")),
            y=_coerce_float(data.get("y")),
            z=_coerce_float(data.get("z")),
            yaw=_coerce_float(data.get("yaw")),
            pitch=_coerce_float(data.get("pitch")),
        )


@dataclass
class SceneEnvironment:
    """Minimal environment descriptor for deterministic scenes."""

    weather: Optional[str] = None
    time: Optional[str] = None
    lighting: Optional[str] = None

    @staticmethod
    def from_dict(data: Optional[Dict[str, Any]]) -> "SceneEnvironment":
        if not isinstance(data, dict):
            return SceneEnvironment()
        return SceneEnvironment(
            weather=_coerce_str(data.get("weather")),
            time=_coerce_str(data.get("time")),
            lighting=_coerce_str(data.get("lighting")),
        )


@dataclass
class SceneConfig:
    """Aggregate scene definition for Phase 1.5."""

    world: Optional[str] = None
    teleport: Optional[SceneTeleport] = None
    environment: Optional[SceneEnvironment] = None
    structures: List[str] = field(default_factory=list)
    npc_skins: List[Dict[str, Any]] = field(default_factory=list)

    @staticmethod
    def from_dict(data: Optional[Dict[str, Any]]) -> "SceneConfig":
        if not isinstance(data, dict):
            return SceneConfig()

        teleport = SceneTeleport.from_dict(data.get("teleport"))
        environment = SceneEnvironment.from_dict(data.get("environment"))

        return SceneConfig(
            world=_coerce_str(data.get("world")),
            teleport=teleport,
            environment=environment,
            structures=_coerce_str_list(data.get("structures")),
            npc_skins=_coerce_dict_list(data.get("npc_skins")),
        )


# ---------------------------------------------------------------------------
# Narrative beats and rules
# ---------------------------------------------------------------------------


@dataclass
class MemoryFlag:
    """Represents a narrative memory bit stored per player."""

    key: str = ""
    value: bool = True

    @staticmethod
    def from_value(raw: Any) -> "MemoryFlag":
        if isinstance(raw, MemoryFlag):
            return raw
        if isinstance(raw, dict):
            key = _coerce_str(raw.get("key") or raw.get("id") or raw.get("flag")) or ""
            value = raw.get("value")
            if isinstance(value, str):
                value = value.strip().lower() not in {"false", "0", "no"}
            elif not isinstance(value, bool):
                value = True
            return MemoryFlag(key=key, value=value)
        key = _coerce_str(raw)
        return MemoryFlag(key=key or "", value=True if raw is not None else False)


@dataclass
class MemoryCondition:
    """Conditions that must be satisfied before content can trigger."""

    require_all: List[str] = field(default_factory=list)
    require_any: List[str] = field(default_factory=list)

    def is_satisfied(self, flags: Iterable[str]) -> bool:
        universe = {flag for flag in flags if isinstance(flag, str)}
        if self.require_all and not all(flag in universe for flag in self.require_all):
            return False
        if self.require_any:
            return any(flag in universe for flag in self.require_any)
        return True

    @staticmethod
    def from_value(raw: Any) -> "MemoryCondition":
        if isinstance(raw, MemoryCondition):
            return raw
        if isinstance(raw, dict):
            require_all = _coerce_str_list(
                raw.get("all")
                or raw.get("require")
                or raw.get("all_of")
                or raw.get("memory")
            )
            require_any = _coerce_str_list(raw.get("any") or raw.get("any_of"))
            return MemoryCondition(require_all=require_all, require_any=require_any)
        return MemoryCondition(require_all=_coerce_str_list(raw))


@dataclass
class MemoryMutation:
    """Defines how a beat or task mutates the memory state."""

    set_flags: List[str] = field(default_factory=list)
    clear_flags: List[str] = field(default_factory=list)

    @staticmethod
    def from_parts(set_raw: Any, clear_raw: Any) -> "MemoryMutation":
        return MemoryMutation(
            set_flags=_coerce_str_list(set_raw),
            clear_flags=_coerce_str_list(clear_raw),
        )

    @staticmethod
    def from_value(raw: Any) -> "MemoryMutation":
        if isinstance(raw, MemoryMutation):
            return raw
        if isinstance(raw, dict):
            return MemoryMutation.from_parts(
                raw.get("set") or raw.get("memory_set") or raw.get("add"),
                raw.get("clear") or raw.get("memory_clear") or raw.get("remove"),
            )
        if raw is None:
            return MemoryMutation()
        return MemoryMutation(set_flags=_coerce_str_list(raw))

    def is_noop(self) -> bool:
        return not self.set_flags and not self.clear_flags


@dataclass
class BeatChoice:
    """Player-facing branching option."""

    id: str = ""
    text: Optional[str] = None
    rule_event: Optional[str] = None
    next_level: Optional[str] = None
    tags: List[str] = field(default_factory=list)

    @staticmethod
    def from_dict(data: Optional[Dict[str, Any]]) -> "BeatChoice":
        if not isinstance(data, dict):
            return BeatChoice()
        return BeatChoice(
            id=_coerce_str(data.get("id")) or "",
            text=_coerce_str(data.get("text")) or _coerce_str(data.get("label")),
            rule_event=_coerce_str(data.get("rule_event")) or _coerce_str(data.get("event")),
            next_level=_coerce_str(data.get("next")) or _coerce_str(data.get("next_level")),
            tags=_coerce_str_list(data.get("tags")) or _coerce_str_list(data.get("affinity_tags")),
        )


@dataclass
class BeatConfig:
    """Narrative beat metadata."""

    id: str = ""
    trigger: Optional[str] = None
    scene_patch: Optional[str] = None
    rule_refs: List[str] = field(default_factory=list)
    choices: List[BeatChoice] = field(default_factory=list)
    choice_prompt: Optional[str] = None
    memory_required: MemoryCondition = field(default_factory=MemoryCondition)
    memory_mutation: MemoryMutation = field(default_factory=MemoryMutation)

    @staticmethod
    def from_dict(data: Optional[Dict[str, Any]]) -> "BeatConfig":
        if not isinstance(data, dict):
            return BeatConfig()
        raw_choices = data.get("choices")
        choices = [BeatChoice.from_dict(item) for item in _coerce_list(raw_choices)]
        memory_required = MemoryCondition.from_value(data.get("memory_required"))
        memory_mutation = MemoryMutation.from_parts(
            data.get("memory_set"),
            data.get("memory_clear"),
        )
        if memory_mutation.is_noop():
            memory_mutation = MemoryMutation.from_value(data.get("memory"))
        return BeatConfig(
            id=_coerce_str(data.get("id")) or "",
            trigger=_coerce_str(data.get("trigger")),
            scene_patch=_coerce_str(data.get("scene_patch")),
            rule_refs=_coerce_str_list(data.get("rule_refs")),
            choices=choices,
            choice_prompt=_coerce_str(data.get("choice_prompt")) or _coerce_str(data.get("prompt")),
            memory_required=memory_required,
            memory_mutation=memory_mutation,
        )


@dataclass
class RuleListener:
    """Listener descriptor for rule graph events."""

    type: Optional[str] = None
    targets: List[str] = field(default_factory=list)
    quest_event: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)

    @staticmethod
    def from_dict(data: Optional[Dict[str, Any]]) -> "RuleListener":
        if not isinstance(data, dict):
            return RuleListener()
        listener = RuleListener(
            type=_coerce_str(data.get("type")),
            targets=_coerce_str_list(data.get("targets")),
            quest_event=_coerce_str(data.get("quest_event")),
            metadata=dict(data.get("metadata") or {}),
        )
        return listener


@dataclass
class RuleGraphConfig:
    """Wrapper for rule listeners."""

    listeners: List[RuleListener] = field(default_factory=list)

    @staticmethod
    def from_dict(data: Optional[Dict[str, Any]]) -> "RuleGraphConfig":
        if not isinstance(data, dict):
            return RuleGraphConfig()
        raw_listeners = data.get("listeners") or []
        listeners = [RuleListener.from_dict(item) for item in _coerce_list(raw_listeners)]
        return RuleGraphConfig(listeners=listeners)


# ---------------------------------------------------------------------------
# Tasks and rewards
# ---------------------------------------------------------------------------


@dataclass
class TaskCondition:
    """Basic task requirement placeholder."""

    item: Optional[str] = None
    entity: Optional[str] = None
    location: Optional[str] = None
    count: Optional[int] = None
    quest_event: Optional[str] = None
    rule_event: Optional[str] = None

    @staticmethod
    def from_dict(data: Optional[Dict[str, Any]]) -> "TaskCondition":
        if not isinstance(data, dict):
            return TaskCondition()
        return TaskCondition(
            item=_coerce_str(data.get("item")),
            entity=_coerce_str(data.get("entity")),
            location=_coerce_str(data.get("location")),
            count=_coerce_int(data.get("count")),
            quest_event=_coerce_str(data.get("quest_event")),
            rule_event=_coerce_str(data.get("rule_event")),
        )


@dataclass
class TaskReward:
    """High-level task reward descriptor."""

    type: Optional[str] = None
    amount: Optional[int] = None
    data: Dict[str, Any] = field(default_factory=dict)

    @staticmethod
    def from_dict(data: Optional[Dict[str, Any]]) -> "TaskReward":
        if not isinstance(data, dict):
            return TaskReward()
        return TaskReward(
            type=_coerce_str(data.get("type")),
            amount=_coerce_int(data.get("amount")),
            data=dict(data.get("data") or {}),
        )


@dataclass
class TaskConfig:
    """Minimal quest/task metadata."""

    id: str = ""
    type: Optional[str] = None
    rule_event: Optional[str] = None
    quest_event: Optional[str] = None
    conditions: List[TaskCondition] = field(default_factory=list)
    memory_set: List[str] = field(default_factory=list)
    milestones: List[str] = field(default_factory=list)
    rewards: List[TaskReward] = field(default_factory=list)
    milestone_memory: Dict[str, MemoryMutation] = field(default_factory=dict)
    completion_memory: MemoryMutation = field(default_factory=MemoryMutation)

    @staticmethod
    def from_dict(data: Optional[Dict[str, Any]]) -> "TaskConfig":
        if not isinstance(data, dict):
            return TaskConfig()
        conditions = [
            TaskCondition.from_dict(item) for item in _coerce_list(data.get("conditions"))
        ]
        rule_event = _coerce_str(data.get("rule_event"))
        quest_event = _coerce_str(data.get("quest_event"))
        memory_set = _coerce_str_list(data.get("memory_set"))
        rewards = [TaskReward.from_dict(item) for item in _coerce_list(data.get("rewards"))]
        milestone_memory = _parse_milestone_memory(data.get("milestone_memory"))
        completion_memory = MemoryMutation.from_parts(
            data.get("memory_set_on_complete") or data.get("memory_set"),
            data.get("memory_clear_on_complete") or data.get("memory_clear"),
        )
        if completion_memory.is_noop():
            completion_memory = MemoryMutation.from_value(data.get("memory_on_complete"))
        return TaskConfig(
            id=_coerce_str(data.get("id")) or "",
            type=_coerce_str(data.get("type")),
            rule_event=rule_event,
            quest_event=quest_event,
            conditions=conditions,
            memory_set=memory_set,
            milestones=_coerce_str_list(data.get("milestones")),
            rewards=rewards,
            milestone_memory=milestone_memory,
            completion_memory=completion_memory,
        )


@dataclass
class ExitConfig:
    """Exit speech configuration."""

    phrase_aliases: List[str] = field(default_factory=list)
    return_spawn: Optional[str] = None
    teleport: Optional[SceneTeleport] = None

    @staticmethod
    def from_dict(data: Optional[Dict[str, Any]]) -> "ExitConfig":
        if not isinstance(data, dict):
            return ExitConfig()
        return ExitConfig(
            phrase_aliases=_coerce_str_list(data.get("phrase_aliases")),
            return_spawn=_coerce_str(data.get("return_spawn")),
            teleport=SceneTeleport.from_dict(data.get("teleport")),
        )


@dataclass
class EmotionalWorldPatchProfile:
    """Emotional world patch override bound to memory flags."""

    profile_id: Optional[str] = None
    label: Optional[str] = None
    tone: Optional[str] = None
    priority: int = 0
    requires_all: List[str] = field(default_factory=list)
    requires_any: List[str] = field(default_factory=list)
    patch: Dict[str, Any] = field(default_factory=dict)

    def matches(self, flags: Iterable[str]) -> bool:
        universe = {flag for flag in flags if isinstance(flag, str)}
        if self.requires_all and not all(flag in universe for flag in self.requires_all):
            return False
        if self.requires_any:
            return any(flag in universe for flag in self.requires_any)
        return bool(self.requires_all)

    @staticmethod
    def from_dict(data: Optional[Dict[str, Any]]) -> "EmotionalWorldPatchProfile":
        if not isinstance(data, dict):
            return EmotionalWorldPatchProfile()
        profile_id = _coerce_str(
            data.get("id")
            or data.get("profile")
            or data.get("key")
            or data.get("tag")
        )
        requires_all = _coerce_str_list(
            data.get("requires")
            or data.get("all")
            or data.get("requires_all")
        )
        requires_any = _coerce_str_list(data.get("any") or data.get("requires_any"))
        priority = _coerce_int(data.get("priority")) or 0
        tone = _coerce_str(data.get("tone"))
        label = _coerce_str(data.get("label"))

        raw_patch = data.get("patch")
        if isinstance(raw_patch, dict):
            patch = deepcopy(raw_patch)
        else:
            patch = {
                key: value
                for key, value in data.items()
                if key not in {
                    "id",
                    "profile",
                    "key",
                    "tag",
                    "requires",
                    "all",
                    "requires_all",
                    "any",
                    "requires_any",
                    "priority",
                    "tone",
                    "label",
                    "patch",
                }
            }

        return EmotionalWorldPatchProfile(
            profile_id=profile_id,
            label=label,
            tone=tone,
            priority=priority,
            requires_all=requires_all,
            requires_any=requires_any,
            patch=patch,
        )


@dataclass
class EmotionalWorldPatchConfig:
    """Aggregates emotional patch defaults and overrides."""

    default_patch: Dict[str, Any] = field(default_factory=dict)
    default_label: Optional[str] = None
    default_tone: Optional[str] = None
    profiles: List[EmotionalWorldPatchProfile] = field(default_factory=list)

    def is_empty(self) -> bool:
        return not self.default_patch and not self.profiles

    def select_profile(self, flags: Iterable[str]) -> Optional[EmotionalWorldPatchProfile]:
        ordered = sorted(self.profiles, key=lambda item: item.priority, reverse=True)
        for profile in ordered:
            if profile.matches(flags):
                return profile
        return None

    def compose_patch(self, flags: Iterable[str]) -> Dict[str, Any]:
        patch = deepcopy(self.default_patch)
        profile = self.select_profile(flags)
        if profile and profile.patch:
            patch = _deep_merge(patch, profile.patch)
        return patch

    def describe(self, flags: Iterable[str]) -> Dict[str, Optional[str]]:
        profile = self.select_profile(flags)
        if profile:
            return {
                "profile_id": profile.profile_id or "profile",
                "label": profile.label or profile.profile_id,
                "tone": profile.tone,
            }
        return {
            "profile_id": "default",
            "label": self.default_label or "steady",
            "tone": self.default_tone,
        }

    @staticmethod
    def from_dict(data: Optional[Dict[str, Any]]) -> "EmotionalWorldPatchConfig":
        if not isinstance(data, dict):
            return EmotionalWorldPatchConfig()

        default_payload = data.get("default") or data.get("baseline")
        default_patch: Dict[str, Any] = {}
        default_label: Optional[str] = None
        default_tone: Optional[str] = None
        if isinstance(default_payload, dict):
            default_label = _coerce_str(default_payload.get("label"))
            default_tone = _coerce_str(default_payload.get("tone"))
            raw_default_patch = default_payload.get("patch")
            if isinstance(raw_default_patch, dict):
                default_patch = deepcopy(raw_default_patch)
            else:
                default_patch = {
                    key: value
                    for key, value in default_payload.items()
                    if key not in {"label", "tone"}
                }
        elif default_payload is not None:
            default_patch = deepcopy(default_payload)

        raw_profiles = (
            data.get("profiles")
            or data.get("states")
            or data.get("rules")
            or []
        )
        profiles = [EmotionalWorldPatchProfile.from_dict(item) for item in _coerce_list(raw_profiles)]

        return EmotionalWorldPatchConfig(
            default_patch=default_patch,
            default_label=default_label,
            default_tone=default_tone,
            profiles=profiles,
        )


@dataclass
class LevelExtensions:
    """Phase 1.5 extension fields to be attached to legacy level objects."""

    beats: List[BeatConfig] = field(default_factory=list)
    scene: Optional[SceneConfig] = None
    rules: Optional[RuleGraphConfig] = None
    tasks: List[TaskConfig] = field(default_factory=list)
    exit: Optional[ExitConfig] = None
    emotional_world_patch: EmotionalWorldPatchConfig = field(default_factory=EmotionalWorldPatchConfig)

    @staticmethod
    def from_payload(payload: Optional[Dict[str, Any]]) -> "LevelExtensions":
        """Parse extension payload into structured dataclasses.

        `payload` should mirror the additional Phase 1.5 keys. Missing entries are
        ignored so that callers can opt-in gradually.
        """

        payload = payload or {}
        narrative = payload.get("narrative") or {}
        raw_beats = narrative.get("beats") or payload.get("beats") or []
        scene = SceneConfig.from_dict(payload.get("scene"))
        rules = RuleGraphConfig.from_dict(payload.get("rules"))
        tasks = [TaskConfig.from_dict(item) for item in _coerce_list(payload.get("tasks"))]
        exit_cfg = ExitConfig.from_dict(payload.get("exit"))

        beats = [BeatConfig.from_dict(item) for item in _coerce_list(raw_beats)]

        emotional_cfg = EmotionalWorldPatchConfig.from_dict(payload.get("emotional_world_patch"))

        return LevelExtensions(
            beats=beats,
            scene=scene,
            rules=rules,
            tasks=tasks,
            exit=exit_cfg,
            emotional_world_patch=emotional_cfg,
        )


# ---------------------------------------------------------------------------
# Utilities
# ---------------------------------------------------------------------------


def _parse_milestone_memory(raw: Any) -> Dict[str, MemoryMutation]:
    result: Dict[str, MemoryMutation] = {}
    if raw is None:
        return result
    if isinstance(raw, dict):
        items = raw.items()
    else:
        items = []
        for entry in _coerce_list(raw):
            if isinstance(entry, dict):
                key = _coerce_str(entry.get("id") or entry.get("milestone_id"))
                if not key:
                    continue
                items.append((key, entry))
    for key, value in items:
        milestone_id = _coerce_str(key)
        if not milestone_id:
            continue
        mutation = MemoryMutation.from_value(value)
        if mutation.is_noop() and isinstance(value, dict):
            mutation = MemoryMutation.from_parts(value.get("set"), value.get("clear"))
        if mutation.is_noop():
            continue
        result[milestone_id] = mutation
    return result


def ensure_level_extensions(level: Any, payload: Optional[Dict[str, Any]] = None) -> LevelExtensions:
    """Attach Phase 1.5 fields to a legacy level object if missing.

    This helper is safe to call repeatedly. It uses ``setattr`` so the legacy
    ``Level`` dataclass from ``story_loader`` gains the new attributes without
    altering its constructor.
    """

    existing = LevelExtensions.from_payload(payload)

    for attr, value in (
        ("beats", existing.beats),
        ("scene", existing.scene),
        ("rules", existing.rules),
        ("tasks", existing.tasks),
        ("exit", existing.exit),
        ("emotional_world_patch", existing.emotional_world_patch),
    ):
        if not hasattr(level, attr):
            setattr(level, attr, value)
    return existing


def _coerce_list(value: Any) -> List[Any]:
    if value is None:
        return []
    if isinstance(value, list):
        return value
    if isinstance(value, tuple):
        return list(value)
    return [value]


def _coerce_str(value: Any) -> Optional[str]:
    if value is None:
        return None
    return str(value)


def _coerce_str_list(value: Any) -> List[str]:
    return [item for item in (_coerce_str(v) for v in _coerce_list(value)) if item]


def _coerce_dict_list(value: Any) -> List[Dict[str, Any]]:
    results: List[Dict[str, Any]] = []
    for item in _coerce_list(value):
        if isinstance(item, dict):
            results.append(dict(item))
    return results


def _coerce_float(value: Any) -> Optional[float]:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _coerce_int(value: Any) -> Optional[int]:
    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _deep_merge(base: Optional[Dict[str, Any]], override: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    result = deepcopy(base) if isinstance(base, dict) else {}
    if not isinstance(override, dict):
        return result
    for key, value in override.items():
        if key in result and isinstance(result[key], dict) and isinstance(value, dict):
            result[key] = _deep_merge(result[key], value)
        else:
            result[key] = deepcopy(value)
    return result
