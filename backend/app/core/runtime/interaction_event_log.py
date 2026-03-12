from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List

from .interaction_event import InteractionEvent, coerce_interaction_event, interaction_event_to_dict


INTERACTION_EVENT_LOG_VERSION = "interaction_event_log_v1"


@dataclass
class InteractionEventLog:
    version: str = INTERACTION_EVENT_LOG_VERSION
    _events: List[InteractionEvent] = field(default_factory=list)
    _event_ids: Dict[str, int] = field(default_factory=dict)

    def append(self, event: InteractionEvent | dict) -> InteractionEvent:
        normalized = coerce_interaction_event(event)
        if normalized.event_id in self._event_ids:
            raise ValueError("DUPLICATE_EVENT_ID")

        self._events.append(normalized)
        self._event_ids[normalized.event_id] = len(self._events) - 1
        return normalized

    def list_events(self) -> List[InteractionEvent]:
        return list(self._events)

    def as_dict_list(self) -> List[dict]:
        return [interaction_event_to_dict(item) for item in self._events]

    def update(self, *args, **kwargs):
        raise RuntimeError("IMMUTABLE_EVENT_LOG")

    def delete(self, *args, **kwargs):
        raise RuntimeError("IMMUTABLE_EVENT_LOG")

    def clear(self, *args, **kwargs):
        raise RuntimeError("IMMUTABLE_EVENT_LOG")
