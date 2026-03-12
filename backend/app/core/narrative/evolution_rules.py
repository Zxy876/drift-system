from __future__ import annotations

import json
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any, Dict, List

from app.core.runtime.resource_canonical import normalize_inventory_resource_token


SCENE_CONTENT_DIR = Path(__file__).resolve().parents[2] / "content" / "scenes"
EVOLUTION_RULES_FILE = SCENE_CONTENT_DIR / "evolution_rules.json"
SEMANTIC_TAGS_FILE = SCENE_CONTENT_DIR / "semantic_tags.json"


DEFAULT_EVOLUTION_RULES = {
    "camp": {
        "collect:wood": ["watchtower"],
        "collect:stone": ["road"],
    },
    "village": {
        "collect:food": ["farm"],
        "collect:metal": ["forge"],
    },
}


def _normalize_token(raw_value: Any) -> str:
    token = str(raw_value or "").strip().lower()
    if not token:
        return ""
    return token.replace("-", "_").replace(" ", "_").strip("_")


def _read_json_file(path: Path) -> Any:
    if not path.exists() or not path.is_file():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None


@lru_cache(maxsize=1)
def _semantic_tags() -> Dict[str, List[str]]:
    raw = _read_json_file(SEMANTIC_TAGS_FILE)
    if not isinstance(raw, dict):
        return {}

    normalized: Dict[str, List[str]] = {}
    for key, value in raw.items():
        resource = _normalize_token(key)
        if not resource:
            continue

        tags: List[str] = []
        if isinstance(value, list):
            for item in value:
                token = _normalize_token(item)
                if token and token not in tags:
                    tags.append(token)

        if tags:
            normalized[resource] = tags

    return normalized


def _normalize_rules(raw_rules: Dict[str, Any]) -> Dict[str, Dict[str, List[str]]]:
    normalized: Dict[str, Dict[str, List[str]]] = {}

    for root_key, rule_map in raw_rules.items():
        root = _normalize_token(root_key)
        if not root or not isinstance(rule_map, dict):
            continue

        normalized[root] = {}
        for event_key, targets in rule_map.items():
            event_token = str(event_key or "").strip().lower()
            if not event_token:
                continue

            target_nodes: List[str] = []
            if isinstance(targets, list):
                for target in targets:
                    token = _normalize_token(target)
                    if token and token not in target_nodes:
                        target_nodes.append(token)

            if target_nodes:
                normalized[root][event_token] = target_nodes

    return normalized


@dataclass(frozen=True)
class EvolutionRules:
    rules: Dict[str, Dict[str, List[str]]]

    def targets_for(self, root: str, event_key: str) -> List[str]:
        root_token = _normalize_token(root)
        key_token = str(event_key or "").strip().lower()
        if not root_token or not key_token:
            return []

        root_rules = self.rules.get(root_token) or {}
        targets = root_rules.get(key_token) or []
        return list(targets)


@lru_cache(maxsize=1)
def load_evolution_rules() -> EvolutionRules:
    raw = _read_json_file(EVOLUTION_RULES_FILE)
    if not isinstance(raw, dict):
        normalized = _normalize_rules(DEFAULT_EVOLUTION_RULES)
        return EvolutionRules(rules=normalized)

    merged = dict(DEFAULT_EVOLUTION_RULES)
    for key, value in raw.items():
        merged[key] = value

    normalized = _normalize_rules(merged)
    return EvolutionRules(rules=normalized)


def _payload_from_event(event: Dict[str, Any]) -> Dict[str, Any]:
    if not isinstance(event, dict):
        return {}

    payload = event.get("payload")
    if isinstance(payload, dict):
        return payload

    raw_payload = event.get("raw_payload")
    if isinstance(raw_payload, dict):
        nested = raw_payload.get("payload")
        if isinstance(nested, dict):
            return nested
        return raw_payload

    nested_event = event.get("event")
    if isinstance(nested_event, dict):
        nested_payload = nested_event.get("payload")
        if isinstance(nested_payload, dict):
            return nested_payload

    return {}


def _event_type_from_event(event: Dict[str, Any]) -> str:
    if not isinstance(event, dict):
        return ""

    for candidate in (
        event.get("event_type"),
        (event.get("raw_payload") or {}).get("event_type") if isinstance(event.get("raw_payload"), dict) else None,
        (event.get("event") or {}).get("event_type") if isinstance(event.get("event"), dict) else None,
    ):
        token = str(candidate or "").strip().lower()
        if token:
            return token

    return ""


def _resource_token_from_event(event: Dict[str, Any], payload: Dict[str, Any]) -> str:
    for key in ("resource", "item", "item_type", "block_type"):
        token = normalize_inventory_resource_token(payload.get(key))
        if token:
            return token

    quest_event = str(payload.get("quest_event") or "").strip().lower()
    if quest_event.startswith("collect_"):
        token = normalize_inventory_resource_token(quest_event)
        if token:
            return token

    raw_event_type = _event_type_from_event(event)
    if raw_event_type.startswith("collect_"):
        token = normalize_inventory_resource_token(raw_event_type)
        if token:
            return token

    return ""


def collect_event_keys(event: Dict[str, Any]) -> List[str]:
    event_type = _event_type_from_event(event)
    payload = _payload_from_event(event)

    keys: List[str] = []

    def _append(key: str) -> None:
        token = str(key or "").strip().lower()
        if token and token not in keys:
            keys.append(token)

    if event_type in {"npc_talk", "talk", "chat"}:
        _append("npc_talk")

    if event_type in {"npc_trigger", "trigger", "interact_entity"}:
        _append("npc_trigger")

    if event_type in {"collect", "pickup", "pickup_item", "item_pickup", "quest_event"}:
        resource = _resource_token_from_event(event, payload)
        if resource:
            _append(f"collect:{resource}")
            for tag in _semantic_tags().get(resource, []):
                _append(f"collect:{tag}")

    trigger = str(payload.get("trigger") or "").strip().lower()
    if trigger:
        _append(trigger)

    return keys
