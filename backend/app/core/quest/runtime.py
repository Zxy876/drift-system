"""Quest runtime for Stage 3 quest and task handling."""

from __future__ import annotations

import copy
import logging
import time
from dataclasses import dataclass, field, is_dataclass
from enum import Enum
from typing import Any, Callable, Dict, Iterable, List, Optional, Set, Tuple, Union

from app.core.story.story_loader import Level, TUTORIAL_CANONICAL_ID
from app.core.runtime.resource_canonical import normalize_inventory_resource_token
from app.core.story.level_schema import RuleListener
from app.core.npc import npc_engine
from .inventory_store import inventory_store
from .quest_state_store import quest_state_store


logger = logging.getLogger(__name__)


TUTORIAL_CANONICAL_EVENTS: Set[str] = {
    "tutorial_intro_started",
    "tutorial_meet_guide",
    "tutorial_complete",
}

TUTORIAL_EVENT_ALIASES: Dict[str, str] = {
    "tutorial_begin": "tutorial_intro_started",
    "tutorial_intro": "tutorial_intro_started",
    "tutorial_start": "tutorial_intro_started",
    "tutorial_question": "tutorial_meet_guide",
    "tutorial_progress": "tutorial_complete",
    "tutorial_checkpoint": "tutorial_complete",
    "tutorial_checkpoint_reach": "tutorial_complete",
    "tutorial_reach_checkpoint": "tutorial_complete",
    "tutorial_task_complete": "tutorial_complete",
    "tutorial_exit": "tutorial_complete",
    "tutorial_finish": "tutorial_complete",
    "tutorial_end": "tutorial_complete",
}


def _canonicalize_tutorial_event(name: Any) -> Optional[str]:
    if name is None:
        return None
    token = str(name).strip().lower()
    if not token:
        return None
    canonical = TUTORIAL_EVENT_ALIASES.get(token, token)
    if canonical in TUTORIAL_CANONICAL_EVENTS:
        return canonical
    return None


@dataclass
class TaskMilestone:
    """Intermediate checkpoints for a task."""

    id: str
    title: Optional[str] = None
    hint: Optional[str] = None
    target: Optional[str] = None
    event: Optional[str] = None
    alternates: List[str] = field(default_factory=list)
    count: int = 1
    progress: int = 0
    status: str = "pending"
    history: List[Dict[str, Any]] = field(default_factory=list)


@dataclass
class TaskSession:
    """Runtime container for a single task and its milestones."""

    id: str
    type: str
    target: Any
    title: str = ""
    hint: Optional[str] = None
    count: int = 1
    reward: Dict[str, Any] = field(default_factory=dict)
    dialogue: Dict[str, Any] = field(default_factory=dict)
    status: str = "pending"
    milestones: List[TaskMilestone] = field(default_factory=list)
    progress: int = 0
    history: List[Dict[str, Any]] = field(default_factory=list)
    rule_refs: List[str] = field(default_factory=list)

    def mark_issued(self, beat_id: Optional[str]) -> Dict[str, Any]:
        self.status = "issued"
        entry = {"event": "issued", "beat": beat_id, "ts": time.time()}
        self.history.append(entry)
        return entry

    def record_event(self, event: Dict[str, Any]) -> Tuple[bool, Optional[Dict[str, Any]]]:
        """Update task progress with an incoming normalized event."""

        if self.status != "issued":
            return False, None

        matched, milestone, matched_token = self._match_event(event)
        if not matched:
            return False, None

        self.progress += 1
        history_entry = {"event": event, "ts": time.time()}
        if matched_token:
            history_entry["matched_event"] = matched_token
        self.history.append(history_entry)

        milestone_payload: Optional[Dict[str, Any]] = None
        if milestone:
            milestone_entry = {"event": event, "ts": time.time()}
            if matched_token:
                milestone_entry["matched_event"] = matched_token
            milestone.history.append(milestone_entry)
            milestone.progress += 1
            if milestone.progress >= milestone.count:
                milestone.status = "completed"
                milestone_payload = {
                    "milestone_completed": True,
                    "milestone_id": milestone.id,
                    "task_id": self.id,
                    "task_title": self.title,
                    "task_hint": self.hint,
                    "milestone_title": milestone.title,
                    "milestone_hint": milestone.hint,
                    "milestone_count": milestone.count,
                    "milestone_progress": milestone.progress,
                }
                if milestone.event:
                    milestone_payload.setdefault("milestone_event", milestone.event)
                if matched_token:
                    milestone_payload.setdefault("matched_event", matched_token)

        if self.progress >= self.count:
            if not self.milestones or all(m.status == "completed" for m in self.milestones):
                self.status = "completed"
                return True, self._completion_payload()

        if milestone_payload is not None:
            milestone_payload.setdefault("task_progress", self.progress)
            milestone_payload.setdefault("task_count", self.count)

        return True, milestone_payload

    def _match_event(self, event: Dict[str, Any]) -> Tuple[bool, Optional[TaskMilestone], Optional[str]]:
        if not event:
            return False, None, None
        if event.get("event_type") != self.type:
            return False, None, None

        target = event.get("target")
        quest_event = event.get("quest_event")
        if target is None and quest_event is not None:
            target = quest_event

        target_token = str(target).lower() if isinstance(target, str) else None
        quest_token = str(quest_event).lower() if isinstance(quest_event, str) else None

        allowed_targets: Set[str] = set()
        if isinstance(self.rule_refs, list):
            for ref in self.rule_refs:
                if isinstance(ref, str) and ref:
                    allowed_targets.add(ref.lower())
        for milestone in self.milestones:
            if milestone.target and isinstance(milestone.target, str):
                allowed_targets.add(milestone.target.lower())
            if milestone.event and isinstance(milestone.event, str):
                allowed_targets.add(milestone.event.lower())
            for alternate in getattr(milestone, "alternates", []) or []:
                if isinstance(alternate, str) and alternate:
                    allowed_targets.add(alternate.lower())
        if isinstance(self.target, dict):
            primary_target = str(self.target.get("name") or self.target.get("type") or "").lower()
            if primary_target:
                allowed_targets.add(primary_target)
        elif isinstance(self.target, str):
            allowed_targets.add(self.target.lower())

        def _matches_expected(expected: Optional[str]) -> bool:
            if not expected:
                return True
            if target_token and target_token == expected:
                return True
            if quest_token and quest_token == expected:
                return True
            return False

        expected_target = None
        if isinstance(self.target, str):
            expected_target = self.target.lower()
        elif isinstance(self.target, dict):
            expected_target = str(self.target.get("name") or self.target.get("type") or "").lower()

        if expected_target and not _matches_expected(expected_target):
            if allowed_targets:
                token_candidates = [token for token in (target_token, quest_token) if token]
                if not any(candidate in allowed_targets for candidate in token_candidates):
                    return False, None, None
            else:
                return False, None, None

        matched_token = next((token for token in (target_token, quest_token) if token), None)
        for milestone in self.milestones:
            if milestone.status == "completed":
                continue
            milestone_expected = str(milestone.target).lower() if milestone.target else None
            alternates = [
                str(alt).lower()
                for alt in (milestone.alternates or [])
                if isinstance(alt, str) and alt
            ]

            candidate_tokens: List[str] = []
            if milestone_expected:
                candidate_tokens.append(milestone_expected)
            if milestone.event and isinstance(milestone.event, str):
                candidate_tokens.append(str(milestone.event).lower())
            candidate_tokens.extend(alternates)

            if candidate_tokens:
                incoming_tokens = [token for token in (target_token, quest_token) if token]
                matched = next((token for token in incoming_tokens if token in candidate_tokens), None)
                if matched:
                    return True, milestone, matched
                continue

            if milestone_expected and not _matches_expected(milestone_expected):
                continue
            return True, milestone, matched_token

        return True, None, matched_token

    def _completion_payload(self) -> Dict[str, Any]:
        return {
            "task_completed": True,
            "task_id": self.id,
            "task_title": self.title,
            "task_hint": self.hint,
            "task_progress": self.progress,
            "task_count": self.count,
            "reward": self.reward,
            "dialogue": self.dialogue,
        }


class QuestRuntime:
    """In-memory quest runtime coordinating per-player task state."""

    LEVEL_STATE_VERSION = "level_state_v1"
    LEVEL_EVOLUTION_VERSION = "level_evolution_v1"
    LEVEL_STAGE_ORDER: Tuple[str, ...] = ("forest", "camp", "camp_npc", "camp_quest")

    def __init__(self) -> None:
        self._players: Dict[str, Dict[str, Any]] = {}
        self._phase3_announced = False
        self._rule_listeners: List[Tuple[str, RuleListener]] = []
        self._rule_callback: Optional[Callable[[str, Dict[str, Any]], None]] = None
        self._orphan_callback: Optional[
            Callable[[str, Dict[str, Any], Dict[str, Any]], Optional[Dict[str, Any]]]
        ] = None
        self._rule_event_history: Dict[str, List[Dict[str, Any]]] = {}
        self._inventory_store = inventory_store
        self._quest_state_store = quest_state_store

    @staticmethod
    def _coerce_positive_int(value: Any, default: int = 1) -> int:
        try:
            parsed = int(float(value))
        except (TypeError, ValueError):
            parsed = int(default)
        return parsed if parsed > 0 else int(default)

    @staticmethod
    def _normalize_collect_resource_token(raw_value: Any) -> str:
        return normalize_inventory_resource_token(raw_value)

    def _extract_collect_resource_from_payload(
        self,
        event_type: str,
        payload: Dict[str, Any],
        normalized: Dict[str, Any],
    ) -> Optional[Tuple[str, int]]:
        event_type_normalized = str(event_type or "").strip().lower()
        if event_type_normalized not in {"collect", "pickup", "pickup_item", "item_pickup", "quest_event"} and not event_type_normalized.startswith("collect_"):
            return None

        payload_body = payload.get("payload") if isinstance(payload.get("payload"), dict) else {}
        payload_meta = payload.get("meta") if isinstance(payload.get("meta"), dict) else {}
        normalized_meta = normalized.get("meta") if isinstance(normalized.get("meta"), dict) else {}

        candidates = [
            payload,
            payload_body,
            payload_meta,
            normalized,
            normalized_meta,
        ]

        resource_name = ""
        for candidate in candidates:
            for key in ("resource", "item", "item_type", "block_type"):
                normalized_token = self._normalize_collect_resource_token(candidate.get(key))
                if normalized_token:
                    resource_name = normalized_token
                    break
            if resource_name:
                break

        if not resource_name:
            quest_token = (
                payload.get("quest_event")
                or payload_body.get("quest_event")
                or payload_meta.get("quest_event")
                or normalized.get("quest_event")
                or normalized_meta.get("quest_event")
            )
            resource_name = self._normalize_collect_resource_token(quest_token)

        if not resource_name and event_type_normalized.startswith("collect_"):
            resource_name = self._normalize_collect_resource_token(event_type_normalized)

        if not resource_name:
            return None

        amount_source: Any = None
        for candidate in candidates:
            amount_source = candidate.get("amount") or candidate.get("count")
            if amount_source is not None:
                break

        amount = self._coerce_positive_int(amount_source, 1)
        return resource_name, amount

    def _persist_collect_inventory(self, player_id: str, payload: Dict[str, Any], normalized: Dict[str, Any]) -> None:
        store = getattr(self, "_inventory_store", None)
        if store is None:
            return

        raw_type = payload.get("event_type") or payload.get("type") or normalized.get("event_type")
        event_type = str(raw_type or "").strip().lower()
        extracted = self._extract_collect_resource_from_payload(event_type, payload, normalized)
        if not extracted:
            return

        resource_name, amount = extracted
        try:
            store.add_resource(player_id, resource_name, amount)
        except Exception:
            logger.exception("QuestRuntime persist collect inventory failed")

    def get_inventory_resources(self, player_id: str) -> Dict[str, int]:
        store = getattr(self, "_inventory_store", None)
        if store is None:
            return {}
        try:
            raw_resources = store.get_resources(player_id)
        except Exception:
            logger.exception("QuestRuntime read inventory resources failed")
            return {}

        normalized: Dict[str, int] = {}
        if isinstance(raw_resources, dict):
            for key, value in raw_resources.items():
                token = self._normalize_collect_resource_token(key)
                if not token:
                    continue
                try:
                    amount = int(value)
                except (TypeError, ValueError):
                    continue
                if amount > 0:
                    normalized[token] = int(normalized.get(token, 0)) + amount
        return normalized

    def _append_rule_event_history(self, player_id: str, event_row: Dict[str, Any]) -> None:
        if not isinstance(event_row, dict):
            return

        history = self._rule_event_history.setdefault(player_id, [])
        history.append(dict(event_row))
        if len(history) > 30:
            del history[:-30]

    def get_recent_rule_events(self, player_id: str, limit: int = 20) -> List[Dict[str, Any]]:
        state = self._players.get(player_id)
        rows: List[Dict[str, Any]] = []

        if isinstance(state, dict):
            recent_state_events = state.get("recent_rule_events")
            if isinstance(recent_state_events, list):
                rows.extend([dict(item) for item in recent_state_events if isinstance(item, dict)])

            state_last = state.get("last_rule_event")
            if isinstance(state_last, dict):
                rows.append(dict(state_last))

        history = self._rule_event_history.get(player_id)
        if isinstance(history, list):
            rows.extend([dict(item) for item in history if isinstance(item, dict)])

        normalized_limit = int(limit) if isinstance(limit, int) and limit > 0 else 20
        if normalized_limit > 0 and len(rows) > normalized_limit:
            rows = rows[-normalized_limit:]

        return rows

    @classmethod
    def _normalize_level_stage(cls, value: Any) -> str:
        token = str(value or "").strip().lower()
        if token in cls.LEVEL_STAGE_ORDER:
            return token
        return cls.LEVEL_STAGE_ORDER[0]

    @classmethod
    def _level_stage_index(cls, stage: Any) -> int:
        normalized = cls._normalize_level_stage(stage)
        return cls.LEVEL_STAGE_ORDER.index(normalized)

    def _default_level_state_payload(self) -> Dict[str, Any]:
        stage = self.LEVEL_STAGE_ORDER[0]
        return {
            "version": self.LEVEL_STATE_VERSION,
            "current_stage": stage,
            "stage_index": 0,
            "stage_path": [stage],
            "history": [],
            "updated_at": time.time(),
        }

    def _default_level_evolution_payload(self) -> Dict[str, Any]:
        stage = self.LEVEL_STAGE_ORDER[0]
        return {
            "version": self.LEVEL_EVOLUTION_VERSION,
            "current_stage": stage,
            "next_stage": self.LEVEL_STAGE_ORDER[1],
            "transition_ready": False,
            "signals": {
                "collect_total": 0,
                "inventory_resources": {},
                "npc_event_count": 0,
                "npc_trigger_count": 0,
                "quest_event_count": 0,
            },
            "blocked_by": ["collect:wood", "collect:pork_or_torch"],
            "updated_at": time.time(),
        }

    @staticmethod
    def _event_type_from_rule_row(row: Dict[str, Any]) -> str:
        if not isinstance(row, dict):
            return ""

        event_payload = row.get("event") if isinstance(row.get("event"), dict) else {}
        raw_payload = row.get("raw_payload") if isinstance(row.get("raw_payload"), dict) else {}

        for candidate in (
            raw_payload.get("event_type"),
            event_payload.get("event_type"),
            row.get("event_type"),
            event_payload.get("type"),
            row.get("type"),
        ):
            token = str(candidate or "").strip().lower()
            if token:
                return token
        return ""

    def _refresh_level_evolution_state(self, player_id: str, state: Dict[str, Any]) -> None:
        if not isinstance(state, dict):
            return

        now_ts = time.time()
        inventory_resources = self.get_inventory_resources(player_id)
        collect_total = sum(max(0, int(amount)) for amount in inventory_resources.values())

        recent_rows = state.get("recent_rule_events") if isinstance(state.get("recent_rule_events"), list) else []
        event_types = [
            self._event_type_from_rule_row(row)
            for row in recent_rows
            if isinstance(row, dict)
        ]
        event_types = [event_type for event_type in event_types if event_type]

        npc_event_count = sum(
            1
            for event_type in event_types
            if event_type in {"npc_talk", "npc_trade", "npc_attack", "npc_trigger"}
        )
        npc_trigger_count = sum(1 for event_type in event_types if event_type == "npc_trigger")
        quest_event_count = sum(1 for event_type in event_types if event_type == "quest_event")

        has_camp_resources = int(inventory_resources.get("wood", 0)) > 0 and (
            int(inventory_resources.get("pork", 0)) > 0
            or int(inventory_resources.get("torch", 0)) > 0
        )
        has_npc_contact = npc_event_count > 0
        has_quest_signal = npc_trigger_count > 0

        inferred_stage = self.LEVEL_STAGE_ORDER[0]
        transition_reason = "bootstrap"
        if has_camp_resources or collect_total >= 3:
            inferred_stage = "camp"
            transition_reason = "resources"
        if has_npc_contact:
            inferred_stage = "camp_npc"
            transition_reason = "npc_interaction"
        if has_quest_signal:
            inferred_stage = "camp_quest"
            transition_reason = "npc_trigger"

        previous_state = state.get("level_state") if isinstance(state.get("level_state"), dict) else {}
        previous_stage = self._normalize_level_stage(previous_state.get("current_stage"))
        previous_index = self._level_stage_index(previous_stage)
        inferred_index = self._level_stage_index(inferred_stage)
        resolved_index = max(previous_index, inferred_index)
        current_stage = self.LEVEL_STAGE_ORDER[resolved_index]

        history = self._safe_dict_list(previous_state.get("history"), max_items=20)
        if current_stage != previous_stage:
            history.append(
                {
                    "from": previous_stage,
                    "to": current_stage,
                    "reason": transition_reason,
                    "timestamp": now_ts,
                }
            )
            if len(history) > 20:
                del history[:-20]

        stage_path = list(self.LEVEL_STAGE_ORDER[: resolved_index + 1])
        level_state = {
            "version": self.LEVEL_STATE_VERSION,
            "current_stage": current_stage,
            "stage_index": resolved_index,
            "stage_path": stage_path,
            "history": history,
            "updated_at": now_ts,
        }

        next_stage = self.LEVEL_STAGE_ORDER[resolved_index + 1] if resolved_index + 1 < len(self.LEVEL_STAGE_ORDER) else None
        transition_ready = False
        blocked_by: List[str] = []
        if next_stage == "camp":
            transition_ready = has_camp_resources or collect_total >= 3
            if not transition_ready:
                blocked_by = ["collect:wood", "collect:pork_or_torch"]
        elif next_stage == "camp_npc":
            transition_ready = has_npc_contact
            if not transition_ready:
                blocked_by = ["npc_interaction"]
        elif next_stage == "camp_quest":
            transition_ready = has_quest_signal
            if not transition_ready:
                blocked_by = ["npc_trigger"]

        level_evolution = {
            "version": self.LEVEL_EVOLUTION_VERSION,
            "current_stage": current_stage,
            "next_stage": next_stage,
            "transition_ready": bool(transition_ready),
            "signals": {
                "collect_total": int(collect_total),
                "inventory_resources": dict(inventory_resources),
                "npc_event_count": int(npc_event_count),
                "npc_trigger_count": int(npc_trigger_count),
                "quest_event_count": int(quest_event_count),
            },
            "blocked_by": blocked_by,
            "updated_at": now_ts,
        }

        state["level_state"] = level_state
        state["level_evolution"] = level_evolution

    @staticmethod
    def _coerce_non_negative_int(value: Any, default: int = 0) -> int:
        try:
            parsed = int(float(value))
        except (TypeError, ValueError):
            parsed = int(default)
        return parsed if parsed >= 0 else int(default)

    @staticmethod
    def _coerce_bool(value: Any, default: bool = False) -> bool:
        if isinstance(value, bool):
            return value
        if isinstance(value, (int, float)):
            return bool(value)
        if isinstance(value, str):
            token = value.strip().lower()
            if token in {"1", "true", "yes", "y", "on"}:
                return True
            if token in {"0", "false", "no", "n", "off", ""}:
                return False
        return bool(default)

    @staticmethod
    def _safe_dict(value: Any) -> Dict[str, Any]:
        return copy.deepcopy(value) if isinstance(value, dict) else {}

    @staticmethod
    def _safe_dict_list(value: Any, max_items: int = 0) -> List[Dict[str, Any]]:
        if not isinstance(value, list):
            return []

        rows = [copy.deepcopy(row) for row in value if isinstance(row, dict)]
        if max_items > 0 and len(rows) > max_items:
            rows = rows[-max_items:]
        return rows

    @staticmethod
    def _normalize_rule_ref_list(raw_values: Any) -> List[str]:
        if not isinstance(raw_values, list):
            return []
        normalized: List[str] = []
        for value in raw_values:
            if not isinstance(value, str):
                continue
            token = value.strip()
            if token and token not in normalized:
                normalized.append(token)
        return normalized

    def _serialize_milestone(self, milestone: TaskMilestone) -> Dict[str, Any]:
        return {
            "id": milestone.id,
            "title": milestone.title,
            "hint": milestone.hint,
            "target": milestone.target,
            "event": milestone.event,
            "alternates": list(milestone.alternates or []),
            "count": int(milestone.count),
            "progress": int(milestone.progress),
            "status": milestone.status,
            "history": self._safe_dict_list(milestone.history),
        }

    def _deserialize_milestone(self, data: Dict[str, Any], fallback_id: str) -> TaskMilestone:
        milestone_id = str(data.get("id") or fallback_id)
        milestone = TaskMilestone(
            id=milestone_id,
            title=data.get("title") if isinstance(data.get("title"), str) else None,
            hint=data.get("hint") if isinstance(data.get("hint"), str) else None,
            target=data.get("target") if isinstance(data.get("target"), str) else None,
            event=data.get("event") if isinstance(data.get("event"), str) else None,
            alternates=self._normalize_rule_ref_list(data.get("alternates") or []),
            count=self._coerce_positive_int(data.get("count"), 1),
        )
        milestone.progress = self._coerce_non_negative_int(data.get("progress"), 0)
        milestone.status = str(data.get("status") or "pending")
        milestone.history = self._safe_dict_list(data.get("history"))
        if milestone.status == "completed" and milestone.progress < milestone.count:
            milestone.progress = milestone.count
        return milestone

    def _serialize_session(self, session: TaskSession) -> Dict[str, Any]:
        payload: Dict[str, Any] = {
            "id": session.id,
            "type": session.type,
            "target": copy.deepcopy(session.target),
            "title": session.title,
            "hint": session.hint,
            "count": int(session.count),
            "reward": self._safe_dict(session.reward),
            "dialogue": self._safe_dict(session.dialogue),
            "status": session.status,
            "progress": int(session.progress),
            "history": self._safe_dict_list(session.history),
            "rule_refs": self._normalize_rule_ref_list(session.rule_refs),
            "milestones": [self._serialize_milestone(milestone) for milestone in (session.milestones or [])],
        }

        if getattr(session, "rewarded", False):
            payload["rewarded"] = True

        issue_node = getattr(session, "issue_node", None)
        if isinstance(issue_node, dict) and issue_node:
            payload["issue_node"] = copy.deepcopy(issue_node)

        return payload

    def _deserialize_session(self, data: Dict[str, Any], index: int) -> TaskSession:
        session_id = str(data.get("id") or f"task_{index:02d}")
        session = TaskSession(
            id=session_id,
            type=str(data.get("type") or "custom"),
            target=copy.deepcopy(data.get("target")),
            title=str(data.get("title") or ""),
            hint=data.get("hint") if isinstance(data.get("hint"), str) else None,
            count=self._coerce_positive_int(data.get("count"), 1),
            reward=self._safe_dict(data.get("reward")),
            dialogue=self._safe_dict(data.get("dialogue")),
            status=str(data.get("status") or "pending"),
            milestones=[],
            rule_refs=self._normalize_rule_ref_list(data.get("rule_refs") or []),
        )

        session.progress = self._coerce_non_negative_int(data.get("progress"), 0)
        session.history = self._safe_dict_list(data.get("history"))

        if session.status not in {"pending", "issued", "completed"}:
            session.status = "pending"
        if session.status == "completed" and session.progress < session.count:
            session.progress = session.count

        milestones_raw = data.get("milestones") if isinstance(data.get("milestones"), list) else []
        session.milestones = [
            self._deserialize_milestone(row, f"{session.id}_milestone_{idx:02d}")
            for idx, row in enumerate(milestones_raw)
            if isinstance(row, dict)
        ]

        if self._coerce_bool(data.get("rewarded"), False):
            setattr(session, "rewarded", True)

        issue_node = data.get("issue_node")
        if isinstance(issue_node, dict) and issue_node:
            setattr(session, "issue_node", copy.deepcopy(issue_node))

        return session

    def _merge_persisted_sessions(
        self,
        fresh_sessions: List[TaskSession],
        persisted_sessions: List[TaskSession],
    ) -> List[TaskSession]:
        if not persisted_sessions:
            return fresh_sessions

        persisted_by_id: Dict[str, TaskSession] = {
            session.id: session for session in persisted_sessions if session.id
        }
        fresh_ids: Set[str] = {session.id for session in fresh_sessions if session.id}

        merged: List[TaskSession] = []
        for fresh in fresh_sessions:
            persisted = persisted_by_id.get(fresh.id)
            if not persisted:
                merged.append(fresh)
                continue

            if not persisted.title:
                persisted.title = fresh.title
            if not persisted.hint:
                persisted.hint = fresh.hint
            if not persisted.reward and fresh.reward:
                persisted.reward = copy.deepcopy(fresh.reward)
            if not persisted.dialogue and fresh.dialogue:
                persisted.dialogue = copy.deepcopy(fresh.dialogue)
            if not persisted.rule_refs and fresh.rule_refs:
                persisted.rule_refs = list(fresh.rule_refs)
            if not persisted.milestones and fresh.milestones:
                persisted.milestones = copy.deepcopy(fresh.milestones)

            persisted_issue_node = getattr(persisted, "issue_node", None)
            fresh_issue_node = getattr(fresh, "issue_node", None)
            if not isinstance(persisted_issue_node, dict) and isinstance(fresh_issue_node, dict):
                setattr(persisted, "issue_node", copy.deepcopy(fresh_issue_node))

            merged.append(persisted)

        for persisted in persisted_sessions:
            if persisted.id and persisted.id not in fresh_ids:
                merged.append(persisted)

        return merged

    def _build_base_state(self, level: Level, player_id: str, tasks: List[TaskSession]) -> Dict[str, Any]:
        level_state = self._default_level_state_payload()
        level_evolution = self._default_level_evolution_payload()
        state: Dict[str, Any] = {
            "player_id": player_id,
            "level_id": level.level_id,
            "level_title": level.title,
            "level": level,
            "tasks": tasks,
            "issued_index": -1,
            "completed_count": 0,
            "summary_emitted": False,
            "last_completed_type": None,
            "active_rule_refs": set(),
            "last_rule_event": None,
            "recent_rule_events": [],
            "level_state": level_state,
            "level_evolution": level_evolution,
        }

        if level.level_id == TUTORIAL_CANONICAL_ID:
            raw_payload = getattr(level, "_raw_payload", {}) or {}
            state["tutorial_tracker"] = {
                "intro_started": False,
                "meet_guide": False,
                "complete": False,
                "completed": False,
            }
            exit_patch = raw_payload.get("tutorial_exit_patch")
            if isinstance(exit_patch, dict) and exit_patch:
                state["tutorial_exit_patch"] = copy.deepcopy(exit_patch)

        return state

    def _serialize_state_payload(self, state: Dict[str, Any]) -> Dict[str, Any]:
        issued_index_raw = state.get("issued_index")
        if isinstance(issued_index_raw, (int, float)):
            issued_index = int(issued_index_raw)
            if issued_index < -1:
                issued_index = -1
        else:
            issued_index = -1

        payload: Dict[str, Any] = {
            "issued_index": issued_index,
            "completed_count": self._coerce_non_negative_int(state.get("completed_count"), 0),
            "summary_emitted": self._coerce_bool(state.get("summary_emitted"), False),
            "last_completed_type": state.get("last_completed_type") if isinstance(state.get("last_completed_type"), str) else None,
            "active_rule_refs": self._normalize_rule_ref_list(sorted(list(state.get("active_rule_refs", set())))),
            "tasks": [self._serialize_session(session) for session in self._iter_sessions(state)],
            "last_rule_event": self._safe_dict(state.get("last_rule_event")),
            "recent_rule_events": self._safe_dict_list(state.get("recent_rule_events"), max_items=10),
            "rule_events": self._safe_dict_list(state.get("rule_events"), max_items=20),
            "orphan_events": self._safe_dict_list(state.get("orphan_events"), max_items=10),
            "auto_heal_suggestions": self._safe_dict_list(state.get("auto_heal_suggestions"), max_items=10),
            "level_state": self._safe_dict(state.get("level_state")),
            "level_evolution": self._safe_dict(state.get("level_evolution")),
        }

        if isinstance(state.get("tutorial_tracker"), dict):
            payload["tutorial_tracker"] = self._safe_dict(state.get("tutorial_tracker"))
        if isinstance(state.get("tutorial_exit_patch"), dict):
            payload["tutorial_exit_patch"] = self._safe_dict(state.get("tutorial_exit_patch"))

        for key in ("tutorial_complete_emitted", "tutorial_completed"):
            if key in state:
                payload[key] = self._coerce_bool(state.get(key), False)

        next_level = state.get("next_level_id")
        if isinstance(next_level, str) and next_level.strip():
            payload["next_level_id"] = next_level.strip()

        return payload

    def _restore_state_from_payload(
        self,
        level: Level,
        player_id: str,
        fresh_tasks: List[TaskSession],
        payload: Dict[str, Any],
    ) -> Dict[str, Any]:
        state = self._build_base_state(level, player_id, fresh_tasks)
        if not isinstance(payload, dict):
            return state

        persisted_task_rows = payload.get("tasks") if isinstance(payload.get("tasks"), list) else []
        persisted_tasks = [
            self._deserialize_session(row, index)
            for index, row in enumerate(persisted_task_rows)
            if isinstance(row, dict)
        ]
        state["tasks"] = self._merge_persisted_sessions(fresh_tasks, persisted_tasks)

        issued_index_raw = payload.get("issued_index", -1)
        try:
            issued_index = int(issued_index_raw)
        except (TypeError, ValueError):
            issued_index = -1
        if issued_index < -1:
            issued_index = -1
        if issued_index >= len(state["tasks"]):
            issued_index = len(state["tasks"]) - 1
        state["issued_index"] = issued_index

        rewarded_count = sum(
            1 for session in state["tasks"] if self._coerce_bool(getattr(session, "rewarded", False), False)
        )
        state["completed_count"] = max(
            self._coerce_non_negative_int(payload.get("completed_count"), 0),
            rewarded_count,
        )
        state["summary_emitted"] = self._coerce_bool(payload.get("summary_emitted"), False)

        last_completed_type = payload.get("last_completed_type")
        state["last_completed_type"] = last_completed_type if isinstance(last_completed_type, str) else None

        active_refs = self._normalize_rule_ref_list(payload.get("active_rule_refs") or [])
        state["active_rule_refs"] = set(active_refs)

        last_rule_event = payload.get("last_rule_event")
        state["last_rule_event"] = copy.deepcopy(last_rule_event) if isinstance(last_rule_event, dict) else None

        for key, size in (("recent_rule_events", 10), ("rule_events", 20), ("orphan_events", 10), ("auto_heal_suggestions", 10)):
            state[key] = self._safe_dict_list(payload.get(key), max_items=size)

        level_state_payload = payload.get("level_state")
        state["level_state"] = copy.deepcopy(level_state_payload) if isinstance(level_state_payload, dict) else self._default_level_state_payload()

        level_evolution_payload = payload.get("level_evolution")
        state["level_evolution"] = copy.deepcopy(level_evolution_payload) if isinstance(level_evolution_payload, dict) else self._default_level_evolution_payload()

        tutorial_tracker = payload.get("tutorial_tracker")
        if isinstance(state.get("tutorial_tracker"), dict) and isinstance(tutorial_tracker, dict):
            tracker = state["tutorial_tracker"]
            for key in ("intro_started", "meet_guide", "complete", "completed"):
                tracker[key] = self._coerce_bool(tutorial_tracker.get(key), tracker.get(key, False))

        tutorial_exit_patch = payload.get("tutorial_exit_patch")
        if isinstance(tutorial_exit_patch, dict) and tutorial_exit_patch:
            state["tutorial_exit_patch"] = copy.deepcopy(tutorial_exit_patch)

        for key in ("tutorial_complete_emitted", "tutorial_completed"):
            if key in payload:
                state[key] = self._coerce_bool(payload.get(key), False)

        next_level_id = payload.get("next_level_id")
        if isinstance(next_level_id, str) and next_level_id.strip():
            state["next_level_id"] = next_level_id.strip()

        self._refresh_level_evolution_state(player_id, state)

        return state

    def _load_quest_state_payload(self, player_id: str, level_id: str) -> Optional[Dict[str, Any]]:
        store = getattr(self, "_quest_state_store", None)
        if store is None:
            return None

        try:
            payload = store.load_state(player_id, level_id)
        except Exception:
            logger.exception("QuestRuntime load quest state failed")
            return None

        return payload if isinstance(payload, dict) else None

    def _persist_quest_state(self, player_id: str, state: Optional[Dict[str, Any]] = None) -> None:
        store = getattr(self, "_quest_state_store", None)
        if store is None:
            return

        active_state = state or self._players.get(player_id)
        if not isinstance(active_state, dict):
            return

        level_id = str(active_state.get("level_id") or "").strip()
        if not level_id:
            return

        try:
            payload = self._serialize_state_payload(active_state)
            store.save_state(player_id, level_id, payload)
        except Exception:
            logger.exception("QuestRuntime persist quest state failed")

    # ------------------------------------------------------------------
    # Phase 1.5 scaffolding
    # ------------------------------------------------------------------
    def register_rule_listener(self, level_id: str, listener: Optional[RuleListener]) -> None:
        """Register a rule listener for future bridge wiring."""

        if listener is None or not getattr(listener, "type", None):
            return

        self._rule_listeners.append((level_id, listener))
        npc_engine.register_rule_binding(level_id, listener)

    def set_rule_callback(self, callback: Optional[Callable[[str, Dict[str, Any]], None]]) -> None:
        """Allow StoryEngine to observe rule triggers."""

        self._rule_callback = callback

    def set_orphan_callback(
        self,
        callback: Optional[Callable[[str, Dict[str, Any], Dict[str, Any]], Optional[Dict[str, Any]]]],
    ) -> None:
        """Register a handler invoked when rule events fail to match any task."""

        self._orphan_callback = callback

    def handle_rule_trigger(self, player_id: str, payload: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Handle an incoming rule trigger and advance relevant tasks."""

        payload_dict = payload if isinstance(payload, dict) else {}
        state = self._players.get(player_id)
        normalized = self._normalize_event(payload_dict)
        if not normalized:
            return None

        self._persist_collect_inventory(player_id, payload_dict, normalized)

        if not state:
            detached_event = {
                "timestamp": time.time(),
                "event": normalized,
                "matched": False,
                "matched_tasks": [],
                "raw_payload": dict(payload_dict),
            }
            self._append_rule_event_history(player_id, detached_event)
            return None

        events_history = state.setdefault("rule_events", [])
        events_history.append(normalized)
        if len(events_history) > 20:
            del events_history[:-20]

        responses: List[Dict[str, Any]] = []
        matched_any = False
        matched_details: List[Dict[str, Any]] = []
        for session in self._iter_active_sessions(state):
            matched, result = session.record_event(normalized)
            if not matched:
                continue
            matched_any = True

            detail: Dict[str, Any] = {
                "task_id": session.id,
                "task_title": session.title,
                "status": session.status,
                "progress": session.progress,
                "count": session.count,
            }

            if result:
                detail.update({
                    key: result[key]
                    for key in (
                        "milestone_completed",
                        "milestone_id",
                        "milestone_title",
                        "task_completed",
                    )
                    if key in result
                })
                responses.append(result)

            remaining = max(0, session.count - session.progress)
            if remaining and session.status == "issued":
                remaining_payload = {
                    "matched": True,
                    "remaining": remaining,
                    "task_id": session.id,
                    "task_title": session.title,
                    "task_hint": session.hint,
                    "task_progress": session.progress,
                    "task_count": session.count,
                }
                responses.append(remaining_payload)
                detail["remaining"] = remaining

            rule_refs = getattr(session, "rule_refs", None)
            if rule_refs:
                detail["rule_refs"] = list(rule_refs)

            matched_details.append(detail)

        tutorial_completion = self._handle_tutorial_completion(state, normalized)
        if tutorial_completion:
            responses.append(tutorial_completion)

        suggestion: Optional[Dict[str, Any]] = None
        if not matched_any:
            suggestion = self._register_orphan_event(player_id, state, normalized, payload)

        last_rule_event = {
            "timestamp": time.time(),
            "event": normalized,
            "matched": matched_any,
            "matched_tasks": matched_details,
            "raw_payload": payload,
        }
        if suggestion:
            last_rule_event["auto_heal_suggestion"] = suggestion
        state["last_rule_event"] = last_rule_event
        self._append_rule_event_history(player_id, last_rule_event)
        recent_events = state.setdefault("recent_rule_events", [])
        recent_events.append(last_rule_event)
        if len(recent_events) > 10:
            del recent_events[:-10]

        self._refresh_level_evolution_state(player_id, state)

        npc_payload = None
        level_id = state.get("level_id")
        if level_id:
            npc_payload = npc_engine.apply_rule_trigger(
                level_id,
                normalized,
                state.get("active_rule_refs", set()),
            )

        combined = self._aggregate_rule_responses(state, responses)
        combined = self._merge_response_payload(combined, npc_payload)

        active_snapshot = self._build_active_tasks_snapshot(state)
        if active_snapshot:
            if combined is None:
                combined = {}
            combined["active_tasks"] = active_snapshot
            self._inject_snapshot_summary(combined, active_snapshot)

        if combined is None:
            combined = {}
        combined["level_state"] = self._safe_dict(state.get("level_state"))
        combined["level_evolution"] = self._safe_dict(state.get("level_evolution"))

        self._persist_quest_state(player_id, state)

        if combined is not None and self._rule_callback:
            try:
                self._rule_callback(player_id, payload_dict)
            except Exception:
                pass

        return combined

    def _register_orphan_event(
        self,
        player_id: str,
        state: Dict[str, Any],
        normalized: Dict[str, Any],
        raw_payload: Dict[str, Any],
    ) -> Optional[Dict[str, Any]]:
        """Record unmatched rule events and delegate auto-heal suggestions."""

        level = state.get("level")
        if not level:
            return None

        # Require an active scene to reduce noise from lobby/world chatter.
        has_scene = bool(getattr(level, "scene", None))
        if not has_scene:
            return None

        active_sessions = list(self._iter_active_sessions(state))
        if not active_sessions:
            return None

        orphan_record: Dict[str, Any] = {
            "timestamp": time.time(),
            "player_id": player_id,
            "level_id": getattr(level, "level_id", None),
            "event": dict(normalized),
            "raw_payload": dict(raw_payload),
            "scene_active": True,
        }

        orphans = state.setdefault("orphan_events", [])
        orphans.append(orphan_record)
        if len(orphans) > 10:
            del orphans[:-10]

        logger.warning(
            "QuestRuntime orphan rule_event",
            extra={
                "player_id": player_id,
                "level_id": orphan_record["level_id"],
                "event": orphan_record["event"],
            },
        )

        suggestion: Optional[Dict[str, Any]] = None
        if self._orphan_callback:
            try:
                suggestion = self._orphan_callback(player_id, dict(orphan_record), state)
            except Exception:  # pragma: no cover - diagnostics only
                logger.exception("QuestRuntime orphan callback failed")

        if suggestion:
            # Ensure numeric confidence when present.
            confidence = suggestion.get("confidence")
            if confidence is not None:
                try:
                    suggestion["confidence"] = float(confidence)
                except (TypeError, ValueError):
                    suggestion.pop("confidence", None)

            orphan_record["auto_heal"] = dict(suggestion)
            history = state.setdefault("auto_heal_suggestions", [])
            history.append({
                "timestamp": orphan_record["timestamp"],
                "event": orphan_record["event"],
                "suggestion": dict(suggestion),
            })
            if len(history) > 10:
                del history[:-10]

        return suggestion

    def get_exit_readiness(self, player_id: str) -> Optional[Dict[str, Any]]:
        """Return exit readiness snapshot for the player (stub)."""

        state = self._players.get(player_id)
        if not state:
            return None

        if self._all_tasks_completed(state):
            return {"exit_ready": True}

        # TODO: incorporate exit phrases and milestones from ExitConfig.
        return None

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------
    def load_level_tasks(self, level: Level, player_id: str) -> None:
        tasks = [self._create_session(raw, index) for index, raw in enumerate(level.tasks or [])]
        state = self._build_base_state(level, player_id, tasks)

        persisted = self._load_quest_state_payload(player_id, level.level_id)
        if isinstance(persisted, dict):
            state = self._restore_state_from_payload(level, player_id, tasks, persisted)

        self._refresh_level_evolution_state(player_id, state)

        self._players[player_id] = state

        active_refs = sorted(list(state.get("active_rule_refs") or []))
        if active_refs:
            npc_engine.activate_rule_refs(level.level_id, active_refs)

        self._persist_quest_state(player_id, state)

    def exit_level(self, player_id: str) -> None:
        state = self._players.get(player_id)
        if isinstance(state, dict):
            self._persist_quest_state(player_id, state)
        self._players.pop(player_id, None)

    def reset_player_state(
        self,
        player_id: str,
        *,
        clear_persisted: bool = True,
        clear_inventory: bool = True,
    ) -> Dict[str, Any]:
        normalized_player = str(player_id or "").strip()
        if not normalized_player:
            return {
                "player_id": "",
                "had_active_state": False,
                "cleared_runtime": False,
                "cleared_persisted": 0,
                "cleared_inventory": 0,
            }

        removed_state = self._players.pop(normalized_player, None)
        self._rule_event_history.pop(normalized_player, None)

        cleared_persisted = 0
        if clear_persisted:
            store = getattr(self, "_quest_state_store", None)
            if store is not None:
                delete_player_states = getattr(store, "delete_player_states", None)
                if callable(delete_player_states):
                    try:
                        cleared_persisted = int(delete_player_states(normalized_player) or 0)
                    except Exception:
                        logger.exception("QuestRuntime clear persisted quest state failed")
                else:
                    level_ids: Set[str] = set()
                    if isinstance(removed_state, dict):
                        level_id = str(removed_state.get("level_id") or "").strip()
                        if level_id:
                            level_ids.add(level_id)
                        level = removed_state.get("level")
                        runtime_level_id = getattr(level, "level_id", None)
                        if isinstance(runtime_level_id, str) and runtime_level_id.strip():
                            level_ids.add(runtime_level_id.strip())

                    delete_state = getattr(store, "delete_state", None)
                    if callable(delete_state):
                        for level_id in level_ids:
                            try:
                                delete_state(normalized_player, level_id)
                                cleared_persisted += 1
                            except Exception:
                                logger.exception("QuestRuntime fallback clear level state failed")

        cleared_inventory = 0
        if clear_inventory:
            store = getattr(self, "_inventory_store", None)
            if store is not None:
                clear_player_resources = getattr(store, "clear_player_resources", None)
                if callable(clear_player_resources):
                    try:
                        cleared_inventory = int(clear_player_resources(normalized_player) or 0)
                    except Exception:
                        logger.exception("QuestRuntime clear inventory resources failed")

        return {
            "player_id": normalized_player,
            "had_active_state": isinstance(removed_state, dict),
            "cleared_runtime": True,
            "cleared_persisted": int(cleared_persisted),
            "cleared_inventory": int(cleared_inventory),
        }

    # ------------------------------------------------------------------
    # Event ingestion and beat coordination
    # ------------------------------------------------------------------
    def record_event(self, player_id: str, event: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        state = self._players.get(player_id)
        if not state:
            return None

        normalized_event = self._normalize_event(event)
        if not normalized_event:
            return None

        state["last_event"] = normalized_event
        responses: List[Dict[str, Any]] = []
        for session in self._iter_active_sessions(state):
            matched, result = session.record_event(normalized_event)
            if matched:
                if result:
                    responses.append(result)
                remaining = max(0, session.count - session.progress)
                if remaining and session.status == "issued":
                    responses.append({
                        "matched": True,
                        "remaining": remaining,
                        "task_id": session.id,
                        "task_title": session.title,
                        "task_hint": session.hint,
                        "task_progress": session.progress,
                        "task_count": session.count,
                    })

        merged_response = self._aggregate_rule_responses(state, responses)
        self._persist_quest_state(player_id, state)
        return merged_response

    def issue_tasks_on_beat(
        self,
        level_or_id: Union[Level, str],
        player_id: str,
        beat: Optional[Dict[str, Any]] = None,
    ) -> Optional[Dict[str, Any]]:
        level = self._extract_level(level_or_id, player_id)
        if not level:
            return None

        state = self._ensure_state(player_id, level)
        if not state:
            return None

        issued = self._issue_next_task(state, level, beat or {})
        if not issued:
            return None

        self._persist_quest_state(player_id, state)

        return {
            "nodes": [issued],
        }

    def activate_rule_refs(
        self,
        level_or_id: Union[Level, str],
        player_id: str,
        rule_refs: Optional[List[str]] = None,
    ) -> None:
        if not rule_refs:
            return

        level = self._extract_level(level_or_id, player_id)
        if not level:
            return

        state = self._ensure_state(player_id, level)
        if not state:
            return

        active = state.setdefault("active_rule_refs", set())
        active.update(rule_refs)

        for session in self._iter_sessions(state):
            if not session.rule_refs:
                continue
            if any(ref in rule_refs for ref in session.rule_refs):
                session.history.append({
                    "event": "rule_ref_activated",
                    "refs": list(rule_refs),
                    "ts": time.time(),
                })

        npc_engine.activate_rule_refs(level.level_id, rule_refs)
        self._persist_quest_state(player_id, state)

    def check_completion(self, level_or_id: Union[Level, str], player_id: str) -> Optional[Dict[str, Any]]:
        level = self._extract_level(level_or_id, player_id)
        if not level:
            return None

        state = self._ensure_state(player_id, level)
        if not state:
            return None

        updates: Dict[str, Any] = {
            "nodes": [],
            "world_patch": {},
            "completed_tasks": [],
        }
        state_changed = False

        rewards = self._collect_rewards(state, level)
        if rewards:
            state_changed = True
            updates["world_patch"] = self._merge_patch(updates["world_patch"], rewards.get("world_patch"))
            updates["nodes"].extend(rewards.get("nodes", []))
            updates["completed_tasks"].extend(rewards.get("completed_tasks", []))

        if self._all_tasks_completed(state) and not state.get("summary_emitted"):
            state_changed = True
            summary = self._build_summary_node(level, state)
            updates["nodes"].append(summary)
            updates["summary"] = summary
            state["summary_emitted"] = True
            updates["exit_ready"] = True

            if not self._phase3_announced and state.get("last_completed_type") == "kill":
                print("Phase 3 complete, proceed to Phase 4")
                self._phase3_announced = True

        if (
            not updates["nodes"]
            and not updates["world_patch"]
            and not updates.get("completed_tasks")
            and not updates.get("exit_ready")
        ):
            return None

        if state_changed:
            self._persist_quest_state(player_id, state)

        return updates

    # ------------------------------------------------------------------
    # Task coordination helpers
    # ------------------------------------------------------------------
    def assign_dynamic_task(self, player_id: str, task_def: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        state = self._players.get(player_id)
        if not state:
            return None
        session = self._create_session(task_def, len(state["tasks"]))
        state["tasks"].append(session)
        self._persist_quest_state(player_id, state)
        return {
            "id": session.id,
            "type": session.type,
            "status": session.status,
            "count": session.count,
        }

    def get_runtime_snapshot(self, player_id: str) -> Dict[str, Any]:
        state = self._players.get(player_id, {})
        if isinstance(state, dict) and state:
            self._refresh_level_evolution_state(player_id, state)
        return {
            "level_id": state.get("level_id"),
            "exit_ready": bool(state.get("summary_emitted")),
            "level_state": self._safe_dict(state.get("level_state")),
            "level_evolution": self._safe_dict(state.get("level_evolution")),
            "tasks": [
                {
                    "id": session.id,
                    "title": session.title,
                    "hint": session.hint,
                    "status": session.status,
                    "progress": session.progress,
                    "count": session.count,
                }
                for session in state.get("tasks", [])
            ],
            "active_rule_refs": sorted(list(state.get("active_rule_refs", []))),
        }

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------
    def _extract_level(self, level_or_id: Union[Level, str], player_id: str) -> Optional[Level]:
        if isinstance(level_or_id, Level):
            return level_or_id

        if isinstance(level_or_id, str):
            state = self._players.get(player_id)
            level = state.get("level") if state else None
            if isinstance(level, Level) and level.level_id == level_or_id:
                return level

        state = self._players.get(player_id)
        level = state.get("level") if state else None
        if isinstance(level, Level):
            return level

        return None

    def _ensure_state(self, player_id: str, level: Optional[Level] = None) -> Optional[Dict[str, Any]]:
        state = self._players.get(player_id)
        if level is None:
            return state

        if not state or state.get("level_id") != level.level_id:
            self.load_level_tasks(level, player_id)
            state = self._players.get(player_id)

        return state

    def _normalize_event(self, event: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        if not isinstance(event, dict):
            return None

        raw_type = event.get("event_type") or event.get("type")
        event_type = str(raw_type).strip().lower() if isinstance(raw_type, str) else ""
        payload_meta = event.get("meta") if isinstance(event.get("meta"), dict) else {}
        payload_body = event.get("payload") if isinstance(event.get("payload"), dict) else {}

        quest_event_payload = (
            event.get("quest_event")
            or payload_body.get("quest_event")
            or payload_meta.get("quest_event")
        )

        canonical_event = _canonicalize_tutorial_event(quest_event_payload)
        alias_from_type = _canonicalize_tutorial_event(event_type)
        fallback_event = None
        if isinstance(quest_event_payload, str):
            token = quest_event_payload.strip().lower()
            if token:
                fallback_event = token

        if alias_from_type:
            canonical_event = alias_from_type
            event_type = "quest_event"
            payload_body["quest_event"] = canonical_event
        elif event_type == "quest_event":
            if canonical_event:
                payload_body["quest_event"] = canonical_event
            elif fallback_event:
                canonical_event = fallback_event
                payload_body["quest_event"] = canonical_event
        elif not event_type:
            return None

        if not canonical_event:
            canonical_event = _canonicalize_tutorial_event(payload_body.get("quest_event")) or fallback_event

        if canonical_event:
            payload_body["quest_event"] = canonical_event
            event_type = "quest_event"

        target = (
            event.get("target")
            or event.get("target_id")
            or payload_body.get("target")
            or payload_body.get("entity_name")
            or payload_body.get("entity_type")
            or payload_body.get("block_type")
        )

        if canonical_event:
            target = canonical_event

        meta = payload_meta or payload_body

        if not event_type:
            return None

        normalized = {
            "event_type": event_type,
            "target": target,
            "meta": meta,
        }

        if event.get("count") is not None:
            normalized["count"] = event.get("count")

        if canonical_event:
            normalized["quest_event"] = canonical_event

        return normalized

    def _handle_tutorial_completion(
        self,
        state: Dict[str, Any],
        normalized_event: Dict[str, Any],
    ) -> Optional[Dict[str, Any]]:
        if not state or state.get("level_id") != TUTORIAL_CANONICAL_ID:
            return None

        tracker = state.get("tutorial_tracker")
        if not isinstance(tracker, dict) or tracker.get("completed"):
            return None

        canonical = normalized_event.get("quest_event")
        event_type = normalized_event.get("event_type")

        if canonical == "tutorial_intro_started":
            tracker["intro_started"] = True
        elif canonical == "tutorial_meet_guide":
            tracker["meet_guide"] = True
        elif canonical == "tutorial_complete":
            tracker["complete"] = True

        if canonical == "tutorial_complete":
            tracker["completed"] = True
            state["tutorial_complete_emitted"] = True
            state["tutorial_completed"] = True
            state["next_level_id"] = "flagship_03"

            completion_payload: Dict[str, Any] = {
                "milestones": ["tutorial_complete"],
                "exit_ready": True,
                "tutorial_completed": True,
                "next_level": "flagship_03",
            }

            exit_patch = state.get("tutorial_exit_patch")
            if isinstance(exit_patch, dict) and exit_patch:
                completion_payload["world_patch"] = copy.deepcopy(exit_patch)
            else:
                completion_payload.setdefault("world_patch", {})

            level_exit_signal = {
                "level_id": TUTORIAL_CANONICAL_ID,
                "next_level": "flagship_03",
                "auto": True,
            }
            completion_payload.setdefault("level_exit", level_exit_signal)

            completion_payload["nodes"] = [
                {
                    "type": "task_milestone",
                    "task_id": "tutorial_complete",
                    "milestone_id": "tutorial_complete",
                    "title": "教程完成",
                    "text": "教程完成，已进入正式剧情。",
                    "status": "milestone",
                    "milestone_event": "tutorial_complete",
                }
            ]

            return completion_payload

        return None

    def _aggregate_rule_responses(
        self,
        state: Dict[str, Any],
        responses: List[Dict[str, Any]],
    ) -> Optional[Dict[str, Any]]:
        if not responses:
            return None

        world_patch: Dict[str, Any] = {}
        nodes: List[Dict[str, Any]] = []
        completed: List[str] = []
        milestones: List[str] = []
        seen_completed: Set[str] = set()
        seen_milestones: Set[str] = set()

        session_lookup: Dict[str, TaskSession] = {
            session.id: session for session in self._iter_sessions(state)
        }
        milestone_lookup: Dict[str, TaskMilestone] = {}
        for session in session_lookup.values():
            for milestone in session.milestones:
                milestone_lookup[milestone.id] = milestone

        extra_payload: Optional[Dict[str, Any]] = None
        for resp in responses:
            if not isinstance(resp, dict):
                continue

            extra_payload = self._merge_response_payload(extra_payload, resp)

            if resp.get("task_completed"):
                task_id = resp.get("task_id")
                if task_id and task_id not in seen_completed:
                    seen_completed.add(task_id)
                    completed.append(task_id)

                    session = session_lookup.get(task_id)
                    if session:
                        state["last_completed_type"] = session.type

                    reward = resp.get("reward") or {}
                    world_patch = self._merge_patch(world_patch, reward.get("world_patch"))
                    if reward.get("npc_dialogue"):
                        world_patch = self._merge_patch(world_patch, {"npc_dialogue": reward["npc_dialogue"]})

                    dialogue = resp.get("dialogue") or {}
                    text = dialogue.get("on_complete")
                    if not text and session and session.dialogue:
                        text = session.dialogue.get("on_complete")

                    task_title = resp.get("task_title") or (
                        session.title if session and session.title else f"任务 {task_id}"
                    )
                    task_hint = resp.get("task_hint") or (
                        session.hint if session and session.hint else None
                    )
                    node_payload: Dict[str, Any] = {
                        "type": "task_complete",
                        "task_id": task_id,
                        "title": task_title,
                        "task_title": task_title,
                        "status": "complete",
                    }
                    if task_hint:
                        node_payload["hint"] = task_hint
                        node_payload["task_hint"] = task_hint
                    if text:
                        node_payload["text"] = text

                    progress_val = resp.get("task_progress")
                    if progress_val is None and session:
                        progress_val = session.progress
                    if progress_val is not None:
                        node_payload["progress"] = progress_val

                    count_val = resp.get("task_count")
                    if count_val is None and session:
                        count_val = session.count
                    if count_val is not None:
                        node_payload["count"] = count_val

                    nodes.append(node_payload)

            if resp.get("milestone_completed"):
                milestone_id = resp.get("milestone_id")
                if milestone_id and milestone_id not in seen_milestones:
                    seen_milestones.add(milestone_id)
                    milestones.append(milestone_id)

                    session = session_lookup.get(resp.get("task_id"))
                    milestone = milestone_lookup.get(milestone_id)

                    milestone_title = resp.get("milestone_title")
                    if not milestone_title:
                        if milestone and milestone.title:
                            milestone_title = milestone.title
                        elif session and session.title:
                            milestone_title = f"{session.title} · 阶段"
                        else:
                            milestone_title = f"阶段完成：{milestone_id}"

                    milestone_hint = resp.get("milestone_hint")
                    if not milestone_hint and milestone and milestone.hint:
                        milestone_hint = milestone.hint
                    if not milestone_hint and session and session.hint:
                        milestone_hint = session.hint

                    milestone_text = resp.get("milestone_text")
                    if not milestone_text and milestone and milestone.title and milestone_title != milestone.title:
                        milestone_text = milestone.title
                    if not milestone_text:
                        milestone_text = "继续保持，加油完成剩余目标！"

                    node_payload: Dict[str, Any] = {
                        "type": "task_milestone",
                        "task_id": resp.get("task_id"),
                        "milestone_id": milestone_id,
                        "title": milestone_title,
                        "text": milestone_text,
                        "status": "milestone",
                    }
                    if session and session.title:
                        node_payload["task_title"] = session.title
                    milestone_event = resp.get("milestone_event")
                    if not milestone_event and milestone and milestone.event:
                        milestone_event = milestone.event
                    if milestone_event:
                        node_payload["milestone_event"] = milestone_event
                    matched_event = resp.get("matched_event")
                    if matched_event:
                        node_payload["matched_event"] = matched_event
                    if milestone_hint:
                        node_payload["hint"] = milestone_hint
                        if session and not node_payload.get("task_hint"):
                            node_payload["task_hint"] = session.hint or milestone_hint
                    elif session and session.hint:
                        node_payload["hint"] = session.hint
                        node_payload.setdefault("task_hint", session.hint)

                    progress_val = resp.get("task_progress")
                    if progress_val is None and session:
                        progress_val = session.progress
                    if progress_val is not None:
                        node_payload["progress"] = progress_val

                    count_val = resp.get("task_count")
                    if count_val is None:
                        count_val = milestone.count if milestone else None
                    if count_val is not None:
                        node_payload["count"] = count_val

                    milestone_count = resp.get("milestone_count")
                    if milestone_count is not None:
                        node_payload["milestone_count"] = milestone_count
                    if milestone and milestone.count and "milestone_count" not in node_payload:
                        node_payload["milestone_count"] = milestone.count

                    nodes.append(node_payload)

            if resp.get("matched") and not resp.get("task_completed"):
                task_id = resp.get("task_id")
                if not task_id:
                    continue

                session = session_lookup.get(task_id)
                remaining_raw = resp.get("remaining")
                try:
                    remaining_val = max(0, int(remaining_raw))
                except (TypeError, ValueError):
                    remaining_val = 0
                if remaining_val <= 0:
                    continue

                task_title = resp.get("task_title") or (
                    session.title if session and session.title else f"任务：{task_id}"
                )
                task_hint = resp.get("task_hint") or (
                    session.hint if session and session.hint else None
                )

                node_payload = {
                    "type": "task_progress",
                    "task_id": task_id,
                    "title": task_title,
                    "task_title": task_title,
                    "status": "progress",
                    "remaining": remaining_val,
                    "text": f"剩余 {remaining_val} 项。",
                }

                if task_hint:
                    node_payload["hint"] = task_hint
                    node_payload["task_hint"] = task_hint

                matched_event = resp.get("matched_event")
                if matched_event:
                    node_payload["matched_event"] = matched_event

                progress_val = resp.get("task_progress")
                if progress_val is None and session:
                    progress_val = session.progress
                if progress_val is not None:
                    node_payload["progress"] = progress_val

                count_val = resp.get("task_count")
                if count_val is None and session:
                    count_val = session.count
                if count_val is not None:
                    node_payload["count"] = count_val

                nodes.append(node_payload)

        if not nodes and not world_patch and not completed and not milestones:
            if extra_payload:
                summary_payload: Dict[str, Any] = {}
                summary_payload = self._merge_response_payload(summary_payload, extra_payload) or summary_payload
                active_snapshot = self._build_active_tasks_snapshot(state)
                if active_snapshot:
                    summary_payload["active_tasks"] = active_snapshot
                    self._inject_snapshot_summary(summary_payload, active_snapshot)
                return summary_payload or None
            snapshot_only = self._build_active_tasks_snapshot(state)
            if snapshot_only:
                payload: Dict[str, Any] = {"active_tasks": snapshot_only}
                self._inject_snapshot_summary(payload, snapshot_only)
                return payload
            return None

        summary: Dict[str, Any] = {"nodes": nodes}
        if world_patch:
            summary["world_patch"] = world_patch
        if completed:
            summary["completed_tasks"] = completed
        if milestones:
            summary["milestones"] = milestones
        active_snapshot = self._build_active_tasks_snapshot(state)
        if active_snapshot:
            summary["active_tasks"] = active_snapshot
            self._inject_snapshot_summary(summary, active_snapshot)
        if extra_payload:
            summary = self._merge_response_payload(summary, extra_payload) or summary
        return summary

    def _inject_snapshot_summary(self, target: Dict[str, Any], snapshot: Dict[str, Any]) -> None:
        if not isinstance(target, dict) or not isinstance(snapshot, dict):
            return
        for key in ("task_titles", "milestone_names"):
            value = snapshot.get(key)
            if value:
                target[key] = value
        for key in ("remaining_total", "active_count", "milestone_count"):
            value = snapshot.get(key)
            if value is not None:
                target[key] = value

    def _build_active_tasks_snapshot(self, state: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        tasks_data: List[Dict[str, Any]] = []
        milestone_names: List[str] = []

        for session in self._iter_sessions(state):
            status = getattr(session, "status", None)
            if status == "completed":
                continue

            remaining = max(0, getattr(session, "count", 0) - getattr(session, "progress", 0))

            task_entry: Dict[str, Any] = {
                "task_id": session.id,
                "title": session.title,
                "hint": session.hint,
                "status": status,
                "progress": getattr(session, "progress", 0),
                "count": getattr(session, "count", 0),
                "remaining": remaining,
                "type": session.type,
            }

            reward = getattr(session, "reward", None)
            if isinstance(reward, dict) and reward:
                task_entry["reward"] = dict(reward)

            rule_refs = getattr(session, "rule_refs", None)
            if rule_refs:
                task_entry["rule_refs"] = list(rule_refs)

            target = getattr(session, "target", None)
            if target:
                task_entry["target"] = target

            milestone_entries: List[Dict[str, Any]] = []
            for milestone in getattr(session, "milestones", []) or []:
                milestone_remaining = max(0, milestone.count - milestone.progress)
                milestone_entry = {
                    "milestone_id": milestone.id,
                    "title": milestone.title,
                    "hint": milestone.hint,
                    "status": milestone.status,
                    "progress": milestone.progress,
                    "count": milestone.count,
                    "remaining": milestone_remaining,
                }
                if milestone.event:
                    milestone_entry["milestone_event"] = milestone.event
                if getattr(milestone, "alternates", None):
                    milestone_entry["alternates"] = list(milestone.alternates)
                milestone_entries.append(milestone_entry)

                if milestone.title and milestone.title not in milestone_names:
                    milestone_names.append(milestone.title)

            if milestone_entries:
                task_entry["milestones"] = milestone_entries

            tasks_data.append(task_entry)

        if not tasks_data:
            return None

        def _safe_int(value: Any) -> int:
            try:
                return int(value)
            except (TypeError, ValueError):
                return 0

        remaining_total = sum(max(0, _safe_int(task.get("remaining"))) for task in tasks_data)

        snapshot: Dict[str, Any] = {
            "player_id": state.get("player_id"),
            "level_id": state.get("level_id"),
            "level_title": state.get("level_title"),
            "tasks": tasks_data,
            "task_titles": [task.get("title") for task in tasks_data if task.get("title")],
            "milestone_names": milestone_names,
            "issued_count": sum(1 for task in tasks_data if task.get("status") == "issued"),
            "pending_count": sum(1 for task in tasks_data if task.get("status") == "pending"),
            "active_count": len(tasks_data),
            "milestone_count": len(milestone_names),
            "remaining_total": remaining_total,
            "timestamp": time.time(),
        }

        return snapshot

    def get_active_tasks_snapshot(self, player_id: str) -> Optional[Dict[str, Any]]:
        state = self._players.get(player_id)
        if not state:
            return None
        snapshot = self._build_active_tasks_snapshot(state)
        if not snapshot:
            return None
        result = dict(snapshot)
        result["player_id"] = player_id
        return result

    def get_debug_snapshot(self, player_id: str) -> Optional[Dict[str, Any]]:
        state = self._players.get(player_id)
        if not state:
            return None

        self._refresh_level_evolution_state(player_id, state)

        active = self._build_active_tasks_snapshot(state)
        completed = self._collect_completed_milestones(state)
        pending = self._collect_pending_conditions(state)
        last_event = state.get("last_rule_event")

        snapshot: Dict[str, Any] = {
            "player_id": state.get("player_id", player_id),
            "level_id": state.get("level_id"),
            "level_title": state.get("level_title"),
            "active_tasks": active,
            "completed_milestones": completed,
            "pending_conditions": pending,
            "last_rule_event": last_event,
            "inventory_resources": self.get_inventory_resources(player_id),
            "level_state": self._safe_dict(state.get("level_state")),
            "level_evolution": self._safe_dict(state.get("level_evolution")),
        }

        if state.get("recent_rule_events"):
            snapshot["recent_rule_events"] = list(state["recent_rule_events"])

        if state.get("orphan_events"):
            snapshot["orphan_events"] = list(state["orphan_events"])

        if state.get("auto_heal_suggestions"):
            snapshot["auto_heal_suggestions"] = list(state["auto_heal_suggestions"])

        return snapshot

    def _collect_completed_milestones(self, state: Dict[str, Any]) -> List[Dict[str, Any]]:
        completed: List[Dict[str, Any]] = []
        for session in self._iter_sessions(state):
            for milestone in getattr(session, "milestones", []) or []:
                if getattr(milestone, "status", None) != "completed":
                    continue
                entry: Dict[str, Any] = {
                    "task_id": session.id,
                    "task_title": session.title,
                    "milestone_id": milestone.id,
                    "milestone_title": milestone.title,
                    "count": milestone.count,
                    "progress": milestone.progress,
                }
                if milestone.hint:
                    entry["milestone_hint"] = milestone.hint
                if milestone.event:
                    entry["milestone_event"] = milestone.event
                if milestone.history:
                    ts = milestone.history[-1].get("ts")
                    if ts is not None:
                        entry["completed_at"] = ts
                completed.append(entry)
        return completed

    def _collect_pending_conditions(self, state: Dict[str, Any]) -> List[Dict[str, Any]]:
        pending: List[Dict[str, Any]] = []
        for session in self._iter_sessions(state):
            if getattr(session, "status", None) == "completed":
                continue

            milestones = getattr(session, "milestones", []) or []
            if not milestones:
                entry = {
                    "task_id": session.id,
                    "task_title": session.title,
                    "status": session.status,
                    "remaining": max(0, session.count - session.progress),
                }
                if session.rule_refs:
                    entry["expected_events"] = list(session.rule_refs)
                pending.append(entry)
                continue

            for milestone in milestones:
                if getattr(milestone, "status", None) == "completed":
                    continue
                entry = {
                    "task_id": session.id,
                    "task_title": session.title,
                    "milestone_id": milestone.id,
                    "milestone_title": milestone.title,
                    "status": milestone.status,
                    "remaining": max(0, milestone.count - milestone.progress),
                }
                if milestone.hint:
                    entry["hint"] = milestone.hint
                if milestone.event:
                    entry["expected_event"] = milestone.event
                elif milestone.target:
                    entry["expected_event"] = milestone.target
                if milestone.alternates:
                    entry["alternates"] = list(milestone.alternates)
                pending.append(entry)

        return pending

    def _create_session(self, task: Dict[str, Any], index: int) -> TaskSession:
        if not isinstance(task, dict):
            if is_dataclass(task):
                task = {key: getattr(task, key) for key in getattr(task, "__dataclass_fields__", {})}
            else:
                task = dict(getattr(task, "__dict__", {}))
        if not isinstance(task, dict):
            task = {}
        def _clean_str(value: Any) -> Optional[str]:
            if value is None:
                return None
            text = str(value).strip()
            return text or None

        def _safe_count(value: Any) -> int:
            try:
                return max(1, int(value or 1))
            except (TypeError, ValueError):
                return 1

        conditions_raw = task.get("conditions") or []
        normalized_conditions: List[Dict[str, Any]] = []
        for cond in conditions_raw:
            cond_map: Optional[Dict[str, Any]] = None
            if isinstance(cond, dict):
                cond_map = dict(cond)
            elif is_dataclass(cond):
                cond_map = {key: getattr(cond, key) for key in getattr(cond, "__dataclass_fields__", {})}
            else:
                attrs = getattr(cond, "__dict__", None)
                if isinstance(attrs, dict):
                    cond_map = dict(attrs)
            if cond_map:
                normalized_conditions.append(cond_map)
        task["conditions"] = normalized_conditions

        def _resolve_condition(condition: Dict[str, Any]) -> Tuple[Optional[str], Optional[str], int, Optional[str]]:
            if not isinstance(condition, dict):
                return None, None, 0, None
            quest_event = condition.get("quest_event") or condition.get("rule_event")
            if quest_event:
                canonical = _canonicalize_tutorial_event(quest_event) or (_clean_str(quest_event) or "")
                if not canonical:
                    return None, None, 0, None
                return "quest_event", canonical, _safe_count(condition.get("count")), condition.get("hint")
            location = _clean_str(condition.get("location"))
            if location:
                return "location", location, _safe_count(condition.get("count")), condition.get("hint")
            item = _clean_str(condition.get("item"))
            if item:
                return "item", item, _safe_count(condition.get("count")), condition.get("hint")
            entity = _clean_str(condition.get("entity"))
            if entity:
                return "entity", entity, _safe_count(condition.get("count")), condition.get("hint")
            return None, None, _safe_count(condition.get("count")), condition.get("hint")

        task_id = str(task.get("id") or f"task_{index:02d}")
        raw_type = _clean_str(task.get("type")) or "custom"
        task_type = raw_type.lower()
        base_target = task.get("target")
        count = _safe_count(task.get("count"))

        condition_milestones: List[Dict[str, Any]] = []
        derived_type: Optional[str] = None
        derived_target: Optional[str] = None
        derived_total = 0

        for idx, condition in enumerate(normalized_conditions):
            cond_type, cond_target, cond_count, cond_hint = _resolve_condition(condition)
            if not cond_type or not cond_target:
                continue
            if derived_type is None:
                derived_type = cond_type
                derived_target = cond_target
            cond_id = (
                _clean_str(condition.get("id"))
                or _clean_str(condition.get("name"))
                or f"{task_id}_condition_{idx:02d}"
            )
            cond_title = (
                _clean_str(condition.get("title"))
                or _clean_str(condition.get("label"))
                or cond_target
            )
            cond_hint_clean = _clean_str(cond_hint) or _clean_str(condition.get("hint"))
            condition_milestones.append({
                "id": cond_id,
                "title": cond_title,
                "hint": cond_hint_clean,
                "target": cond_target,
                "milestone_event": cond_target,
                "count": cond_count,
            })
            derived_total += cond_count

        if derived_type and task_type in {"custom", "story", ""}:
            task_type = derived_type

        if derived_target and (base_target is None or task_type == "quest_event"):
            base_target = derived_target

        if derived_total:
            count = max(count, derived_total)

        target = base_target if base_target is not None else derived_target
        if isinstance(target, str):
            target = _clean_str(target)
        if task_type == "quest_event" and isinstance(target, str) and target:
            target = _canonicalize_tutorial_event(target) or target.lower()
        if target is None:
            target = {}
        reward_raw = task.get("reward") or task.get("rewards")
        if isinstance(reward_raw, list):
            reward = next((item for item in reward_raw if isinstance(item, dict)), {})
        elif isinstance(reward_raw, dict):
            reward = reward_raw
        else:
            reward = {}

        dialogue_raw = task.get("dialogue") or task.get("dialogues")
        if isinstance(dialogue_raw, dict):
            dialogue = dialogue_raw
        elif isinstance(dialogue_raw, str):
            dialogue = {"text": dialogue_raw}
        else:
            dialogue = {}
        rule_refs = list(task.get("rule_refs", []) or [])

        task_rule_event = _clean_str(task.get("rule_event"))
        if task_rule_event:
            canonical_rule_event = _canonicalize_tutorial_event(task_rule_event) or task_rule_event.lower()
            task["rule_event"] = canonical_rule_event
            if canonical_rule_event not in rule_refs:
                rule_refs.append(canonical_rule_event)

        if task_type == "quest_event" and isinstance(target, str) and target and target not in rule_refs:
            rule_refs.append(target)
        for milestone_def in condition_milestones:
            milestone_target = milestone_def.get("target")
            if milestone_target and milestone_target not in rule_refs:
                rule_refs.append(milestone_target)

        task_title = _clean_str(task.get("title")) or _clean_str(task.get("name")) or _clean_str(task.get("label"))
        task_hint = (
            _clean_str(task.get("hint"))
            or _clean_str(task.get("summary"))
            or _clean_str(task.get("description"))
        )

        issue_node_raw = task.get("issue_node")
        issue_node = issue_node_raw if isinstance(issue_node_raw, dict) else None
        if issue_node:
            task_title = task_title or _clean_str(issue_node.get("title"))
            task_hint = task_hint or _clean_str(issue_node.get("hint")) or _clean_str(issue_node.get("text"))

        milestone_configs = list(task.get("milestones") or [])
        if condition_milestones:
            milestone_configs.extend(condition_milestones)
        milestones: List[TaskMilestone] = []
        for idx, raw in enumerate(milestone_configs):
            milestone_data: Optional[Dict[str, Any]] = None
            if isinstance(raw, dict):
                milestone_data = dict(raw)
            elif is_dataclass(raw):
                milestone_data = {key: getattr(raw, key) for key in getattr(raw, "__dataclass_fields__", {})}
            elif isinstance(raw, str):
                milestone_data = {"id": raw, "title": raw}
            else:
                attrs = getattr(raw, "__dict__", None)
                if isinstance(attrs, dict):
                    milestone_data = dict(attrs)
            if not milestone_data:
                continue

            milestone_id = _clean_str(milestone_data.get("id")) or _clean_str(milestone_data.get("name"))
            milestone_id = milestone_id or f"{task_id}_milestone_{idx:02d}"
            milestone_title = _clean_str(milestone_data.get("title")) or _clean_str(milestone_data.get("name"))
            milestone_hint = (
                _clean_str(milestone_data.get("hint"))
                or _clean_str(milestone_data.get("summary"))
                or _clean_str(milestone_data.get("description"))
            )
            milestone_event = (
                _clean_str(milestone_data.get("milestone_event"))
                or _clean_str(milestone_data.get("event"))
                or _clean_str(milestone_data.get("rule_event"))
            )
            milestone_target = (
                _clean_str(milestone_data.get("target"))
                or _clean_str(milestone_data.get("entity"))
                or _clean_str(milestone_data.get("location"))
            )
            if not milestone_target and milestone_event:
                milestone_target = milestone_event

            alternates_raw = milestone_data.get("alternates") or milestone_data.get("alternate_targets")
            milestone_alternates: List[str] = []
            if isinstance(alternates_raw, (list, tuple, set)):
                for alt in alternates_raw:
                    alt_clean = _clean_str(alt)
                    if alt_clean:
                        milestone_alternates.append(alt_clean)

            try:
                milestone_count = max(1, int(milestone_data.get("count") or milestone_data.get("required") or 1))
            except (TypeError, ValueError):
                milestone_count = 1

            milestones.append(TaskMilestone(
                id=milestone_id,
                title=milestone_title,
                hint=milestone_hint,
                target=milestone_target,
                event=milestone_event,
                alternates=milestone_alternates,
                count=milestone_count,
            ))

            if milestone_event and milestone_event not in rule_refs:
                rule_refs.append(milestone_event)
            for alternate in milestone_alternates:
                if alternate and alternate not in rule_refs:
                    rule_refs.append(alternate)

        session = TaskSession(
            id=task_id,
            type=task_type,
            target=target,
            title=task_title or "",
            hint=task_hint,
            count=count,
            reward=reward,
            dialogue=dialogue,
            milestones=milestones,
            rule_refs=rule_refs,
        )

        if not session.title:
            if isinstance(target, dict):
                fallback = _clean_str(target.get("name") or target.get("type"))
            elif isinstance(target, str):
                fallback = _clean_str(target)
            else:
                fallback = None
            session.title = fallback or f"任务：{session.id}"

        if not session.hint:
            session.hint = self._default_issue_text(session)

        if issue_node:
            setattr(session, "issue_node", issue_node)

        return session

    def _merge_response_payload(
        self,
        base: Optional[Dict[str, Any]],
        addition: Optional[Dict[str, Any]],
    ) -> Optional[Dict[str, Any]]:
        if not addition:
            return base

        merged: Dict[str, Any] = {}
        if base:
            merged.update(base)

        nodes = list(merged.get("nodes") or [])
        added_nodes = addition.get("nodes") if isinstance(addition.get("nodes"), list) else []
        if added_nodes:
            nodes.extend(added_nodes)
        if nodes:
            merged["nodes"] = nodes

        world_patch = self._merge_patch(merged.get("world_patch"), addition.get("world_patch"))
        if world_patch:
            merged["world_patch"] = world_patch
        elif "world_patch" in merged and not merged["world_patch"]:
            merged.pop("world_patch")

        for key in ("completed_tasks", "milestones"):
            existing = list(merged.get(key) or [])
            incoming = addition.get(key)
            if isinstance(incoming, list) and incoming:
                existing.extend(incoming)
            if existing:
                merged[key] = existing
            elif key in merged:
                merged.pop(key)

        for key, value in addition.items():
            if key in {"nodes", "world_patch", "completed_tasks", "milestones"}:
                continue
            if value is None:
                continue
            if isinstance(value, list):
                existing_list = merged.get(key)
                if isinstance(existing_list, list):
                    merged[key] = existing_list + value
                else:
                    merged[key] = list(value)
            else:
                merged[key] = value

        return merged or base

    def _issue_next_task(self, state: Dict[str, Any], level: Level, beat: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        sessions = state.get("tasks", [])
        for session in sessions:
            if session.status == "pending":
                session.mark_issued(beat.get("id"))
                state["issued_index"] = sessions.index(session)
                return self._build_issue_node(level, session)
        return None

    def _collect_rewards(self, state: Dict[str, Any], level: Level) -> Optional[Dict[str, Any]]:
        world_patch: Dict[str, Any] = {}
        nodes: List[Dict[str, Any]] = []
        completed: List[str] = []
        for session in self._iter_sessions(state):
            if session.status == "completed" and not getattr(session, "rewarded", False):
                reward = session.reward or {}
                world_patch = self._merge_patch(world_patch, reward.get("world_patch"))
                if "npc_dialogue" in reward:
                    world_patch = self._merge_patch(world_patch, {"npc_dialogue": reward["npc_dialogue"]})
                nodes.append(self._build_reward_node(level, session))
                setattr(session, "rewarded", True)
                state["completed_count"] += 1
                state["last_completed_type"] = session.type
                completed.append(session.id)

        if not nodes and not world_patch:
            return None

        return {
            "world_patch": world_patch,
            "nodes": nodes,
            "completed_tasks": completed,
        }

    def _all_tasks_completed(self, state: Dict[str, Any]) -> bool:
        tasks = list(self._iter_sessions(state))
        return bool(tasks) and all(session.status == "completed" for session in tasks)

    def _build_issue_node(self, level: Level, session: TaskSession) -> Dict[str, Any]:
        node = getattr(session, "issue_node", {}) or {}
        title = node.get("title") or session.title or f"任务：{session.id}"
        hint = node.get("hint") or session.hint
        text = node.get("text") or hint or self._default_issue_text(session)
        payload = {
            "title": title,
            "text": text,
            "type": "task",
            "task_id": session.id,
            "status": "issued",
        }
        if hint:
            payload["hint"] = hint
        return payload

    def _build_reward_node(self, level: Level, session: TaskSession) -> Dict[str, Any]:
        text = session.dialogue.get("on_complete") or "任务完成，奖励已发放。"
        payload = {
            "title": session.title or f"任务：{session.id}",
            "text": text,
            "type": "task_complete",
            "task_id": session.id,
            "status": "complete",
        }
        if session.hint:
            payload["hint"] = session.hint
        return payload

    def _build_summary_node(self, level: Level, state: Dict[str, Any]) -> Dict[str, Any]:
        return {
            "title": f"{level.title} · 任务总结",
            "text": "全部任务已完成，你可以随时返回昆明湖。",
            "hint": "输入 /advance 或使用出口回到中心。",
            "type": "task_summary",
            "status": "summary",
        }

    def _default_issue_text(self, session: TaskSession) -> str:
        task_type = session.type
        target = session.target
        count = session.count
        if isinstance(target, dict):
            name = target.get("name") or target.get("type") or target.get("id")
        else:
            name = str(target) if target not in ({}, None, "") else None
        name = name or "任务目标"
        return f"完成 {task_type} ×{count}（目标：{name}）"
    def _iter_sessions(self, state: Dict[str, Any]) -> Iterable[TaskSession]:
        return state.get("tasks", [])

    def _iter_active_sessions(self, state: Dict[str, Any]) -> Iterable[TaskSession]:
        return [session for session in self._iter_sessions(state) if session.status == "issued"]

    @staticmethod
    def _merge_patch(base: Optional[Dict[str, Any]], addition: Optional[Dict[str, Any]]) -> Dict[str, Any]:
        if not addition:
            return dict(base or {})
        merged = dict(base or {})
        for key, value in addition.items():
            if key == "mc" and isinstance(value, dict):
                existing = merged.get("mc")
                if isinstance(existing, dict):
                    merged["mc"] = {**existing, **value}
                else:
                    merged["mc"] = dict(value)
            else:
                merged[key] = value
        return merged


quest_runtime = QuestRuntime()


class TaskEventType(Enum):
    """Event types emitted by the Minecraft rule bridge."""

    BLOCK_BREAK = "BLOCK_BREAK"
    ENTITY_KILL = "ENTITY_KILL"
    ITEM_COLLECT = "ITEM_COLLECT"
    AREA_REACH = "AREA_REACH"
    DIALOGUE = "DIALOGUE"
