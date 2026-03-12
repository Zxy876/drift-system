"""Event manager for narrative beats.

Provides per-player event registration and evaluation for keyword,
proximity, interaction, and item-use triggers. Used by StoryEngine stage 3
(upgraded beat system).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Dict, Iterable, List, Optional

EventCallback = Callable[[Dict[str, Any]], None]


@dataclass
class _RegisteredEvent:
    event_type: str
    config: Dict[str, Any]
    callback: Optional[EventCallback]


class EventManager:
    """Central dispatcher that evaluates player events."""

    SUPPORTED_TYPES = {"keyword", "near", "interact", "item_use"}

    def __init__(self) -> None:
        self._registry: Dict[str, Dict[str, _RegisteredEvent]] = {}

    # ------------------------------------------------------------------
    # Registration lifecycle
    # ------------------------------------------------------------------
    def register(
        self,
        player_id: str,
        event_id: str,
        definition: Dict[str, Any],
        callback: Optional[EventCallback] = None,
    ) -> None:
        """Register an event definition for a player."""

        event_type = str(definition.get("type" or "event" or "kind"))
        if event_type not in self.SUPPORTED_TYPES:
            raise ValueError(f"Unsupported event type: {event_type}")

        normalized = {
            "type": event_type,
            **{k: v for k, v in definition.items() if k != "type"},
        }

        registry = self._registry.setdefault(player_id, {})
        registry[event_id] = _RegisteredEvent(event_type, normalized, callback)

    def unregister(self, player_id: str, event_id: Optional[str] = None) -> None:
        """Remove a specific event or all events for a player."""

        if player_id not in self._registry:
            return

        if event_id is None:
            self._registry.pop(player_id, None)
            return

        events = self._registry.get(player_id)
        if events is None:
            return

        events.pop(event_id, None)
        if not events:
            self._registry.pop(player_id, None)

    # ------------------------------------------------------------------
    # Evaluation
    # ------------------------------------------------------------------
    def evaluate(
        self,
        player_id: str,
        action: Optional[Dict[str, Any]],
        world_state: Optional[Dict[str, Any]],
    ) -> List[str]:
        """Evaluate events for a player and return triggered event ids."""

        triggered: List[str] = []
        events = self._registry.get(player_id)
        if not events:
            return triggered

        action = action or {}
        world_state = world_state or {}

        for event_id, entry in list(events.items()):
            if self._matches(entry, action, world_state):
                triggered.append(event_id)
                if entry.callback:
                    payload = {
                        "id": event_id,
                        "type": entry.event_type,
                        "config": entry.config,
                        "action": action,
                        "world_state": world_state,
                    }
                    entry.callback(payload)

        return triggered

    def evaluate_event_def(
        self,
        event_def: Dict[str, Any],
        say_text: str,
        player_id: Optional[str] = None,
        world: Optional[Dict[str, Any]] = None,
        context: Optional[Dict[str, Any]] = None,
    ) -> Optional[str]:
        """Evaluate a trigger dictionary against current input.

        Parameters mirror StoryEngine expectations. Returns the matched trigger
        key (e.g., "keyword") when one succeeds, otherwise ``None``.
        """

        if not event_def:
            return None

        action_context: Dict[str, Any] = {}
        if isinstance(context, dict):
            action_candidate = context.get("action")
            if isinstance(action_candidate, dict):
                action_context = dict(action_candidate)
        if isinstance(say_text, str) and say_text.strip():
            action_context = {**action_context, "say": say_text}
            lowered = say_text.lower()
        else:
            lowered = ""

        # Backwards compatibility: handle legacy {"type": ..., "config": ...} shape.
        if "type" in event_def and "config" in event_def:
            event_type = str(event_def.get("type"))
            if event_type in self.SUPPORTED_TYPES:
                entry = _RegisteredEvent(event_type, dict(event_def.get("config") or {}), None)
                if self._matches(entry, action_context, world or {}):
                    return event_type

        keywords = self._coerce_list(event_def.get("keyword") or event_def.get("keywords"))
        if lowered and any(word and word.lower() in lowered for word in keywords):
            return "keyword"

        near_config = event_def.get("near")
        if isinstance(near_config, dict):
            if self._match_near(dict(near_config), action_context, world or {}):
                return "near"

        interact_values = event_def.get("interact")
        if interact_values is not None:
            if self._match_interact({"targets": interact_values}, action_context):
                return "interact"

        item_use_values = event_def.get("item_use")
        if item_use_values is not None:
            if self._match_item_use({"items": item_use_values}, action_context):
                return "item_use"

        return None

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------
    def _matches(
        self,
        entry: _RegisteredEvent,
        action: Dict[str, Any],
        world_state: Dict[str, Any],
    ) -> bool:
        match entry.event_type:
            case "keyword":
                return self._match_keyword(entry.config, action)
            case "near":
                return self._match_near(entry.config, action, world_state)
            case "interact":
                return self._match_interact(entry.config, action)
            case "item_use":
                return self._match_item_use(entry.config, action)
            case _:
                return False

    # -- matchers -------------------------------------------------------
    def _match_keyword(self, config: Dict[str, Any], action: Dict[str, Any]) -> bool:
        text = action.get("say") or action.get("text")
        if not isinstance(text, str) or not text.strip():
            return False

        text_lower = text.lower()
        keywords = self._coerce_list(config.get("words") or config.get("keyword"))
        return any(word and word.lower() in text_lower for word in keywords)

    def _match_near(
        self,
        config: Dict[str, Any],
        action: Dict[str, Any],
        world_state: Dict[str, Any],
    ) -> bool:
        variables = world_state.get("variables") or {}
        px = self._coerce_number(variables.get("x"))
        py = self._coerce_number(variables.get("y"))
        pz = self._coerce_number(variables.get("z"))
        if px is None or py is None or pz is None:
            return False

        entity_name = config.get("entity")
        if isinstance(entity_name, str):
            entity_data = self._lookup_entity(world_state, entity_name)
            if entity_data:
                target = entity_data
            else:
                target = None
        else:
            target = None

        if target is None:
            target = {
                "x": self._coerce_number(config.get("x")),
                "y": self._coerce_number(config.get("y")),
                "z": self._coerce_number(config.get("z")),
            }

        if any(v is None for v in target.values()):
            return False

        radius = self._coerce_number(config.get("radius"), default=2.0) or 2.0

        dx = px - float(target["x"])
        dy = py - float(target["y"])
        dz = pz - float(target["z"])
        return (dx * dx + dy * dy + dz * dz) ** 0.5 <= float(radius)

    def _match_interact(self, config: Dict[str, Any], action: Dict[str, Any]) -> bool:
        target = action.get("interact") or action.get("target")
        if isinstance(target, dict):
            target = target.get("id") or target.get("target")
        if target is None:
            return False
        targets = self._coerce_list(config.get("targets") or config.get("target"))
        target_str = str(target).lower()
        return any(str(t).lower() == target_str for t in targets)

    def _match_item_use(self, config: Dict[str, Any], action: Dict[str, Any]) -> bool:
        item = action.get("item_use") or action.get("item")
        if isinstance(item, dict):
            item = item.get("id") or item.get("name")
        if not item:
            return False
        items = self._coerce_list(config.get("items") or config.get("item"))
        item_str = str(item).lower()
        return any(str(i).lower() == item_str for i in items)

    # -- helpers --------------------------------------------------------
    @staticmethod
    def _coerce_list(value: Any) -> List[str]:
        if value is None:
            return []
        if isinstance(value, (list, tuple, set)):
            return [str(v) for v in value if v is not None]
        return [str(value)]

    @staticmethod
    def _coerce_number(value: Any, default: Optional[float] = None) -> Optional[float]:
        try:
            if value is None:
                return default
            return float(value)
        except (TypeError, ValueError):
            return default

    @staticmethod
    def _lookup_entity(world_state: Dict[str, Any], entity_name: str) -> Optional[Dict[str, float]]:
        entities = world_state.get("entities")
        if not isinstance(entities, Iterable):
            return None
        for entity in entities:
            if not isinstance(entity, dict):
                continue
            ident = entity.get("id") or entity.get("name")
            if isinstance(ident, str) and ident.lower() == entity_name.lower():
                x = entity.get("x")
                y = entity.get("y")
                z = entity.get("z")
                if None not in (x, y, z):
                    try:
                        return {"x": float(x), "y": float(y), "z": float(z)}
                    except (TypeError, ValueError):
                        return None
        return None