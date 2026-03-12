from __future__ import annotations

import json
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any, Dict, List, Set

from app.core.runtime.resource_canonical import normalize_inventory_resource_token

from .narrative_state import NarrativeState, NarrativeTransitionCandidate


CONTENT_DIR = Path(__file__).resolve().parents[2] / "content" / "story"
NARRATIVE_GRAPH_FILE = CONTENT_DIR / "narrative_graph.json"


def _normalize_token(value: Any) -> str:
    token = str(value or "").strip().lower()
    if not token:
        return ""
    return token.replace("-", "_").replace(" ", "_").strip("_")


def _normalize_token_list(raw_value: Any) -> List[str]:
    if not isinstance(raw_value, list):
        return []

    rows: List[str] = []
    seen: Set[str] = set()
    for item in raw_value:
        token = _normalize_token(item)
        if not token or token in seen:
            continue
        seen.add(token)
        rows.append(token)
    return rows


def _safe_dict(raw_value: Any) -> Dict[str, Any]:
    return dict(raw_value) if isinstance(raw_value, dict) else {}


@dataclass(frozen=True)
class NarrativeNodeRule:
    node: str
    arc: str
    next_nodes: List[str]
    requires: List[str]


@dataclass(frozen=True)
class NarrativeGraphConfig:
    version: str
    entry_node: str
    node_order: List[str]
    nodes: Dict[str, NarrativeNodeRule]


def _default_graph_payload() -> Dict[str, Any]:
    return {
        "version": "p8a_v1",
        "entry_node": "forest_intro",
        "nodes": {
            "forest_intro": {
                "arc": "main",
                "next": ["camp_life"],
                "requires": ["scene:camp"],
            },
            "camp_life": {
                "arc": "main",
                "next": ["village_arrival"],
                "requires": ["scene:village"],
            },
            "village_arrival": {
                "arc": "main",
                "next": [],
                "requires": ["scene:forge"],
            },
        },
    }


def _load_json(path: Path) -> Any:
    if not path.exists() or not path.is_file():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None


def _normalize_graph(raw_graph: Any) -> NarrativeGraphConfig:
    payload = _safe_dict(raw_graph)
    if not payload:
        payload = _default_graph_payload()

    raw_nodes = _safe_dict(payload.get("nodes"))
    if not raw_nodes:
        raw_nodes = _safe_dict(payload)

    node_order: List[str] = []
    nodes: Dict[str, NarrativeNodeRule] = {}

    for raw_node, raw_rule in raw_nodes.items():
        node_id = _normalize_token(raw_node)
        if not node_id:
            continue

        rule_map = _safe_dict(raw_rule)
        arc = _normalize_token(rule_map.get("arc")) or "main"
        next_nodes = _normalize_token_list(rule_map.get("next"))
        requires = _normalize_token_list(rule_map.get("requires"))

        node_order.append(node_id)
        nodes[node_id] = NarrativeNodeRule(
            node=node_id,
            arc=arc,
            next_nodes=next_nodes,
            requires=requires,
        )

    if not nodes:
        fallback = _default_graph_payload()
        return _normalize_graph(fallback)

    version = str(payload.get("version") or "p8a_v1").strip() or "p8a_v1"
    entry_node = _normalize_token(payload.get("entry_node"))
    if entry_node not in nodes:
        entry_node = node_order[0]

    return NarrativeGraphConfig(
        version=version,
        entry_node=entry_node,
        node_order=node_order,
        nodes=nodes,
    )


@lru_cache(maxsize=1)
def load_narrative_graph() -> NarrativeGraphConfig:
    raw = _load_json(NARRATIVE_GRAPH_FILE)
    return _normalize_graph(raw)


def _event_type_from_row(row: Dict[str, Any]) -> str:
    if not isinstance(row, dict):
        return ""

    for candidate in (
        row.get("event_type"),
        (_safe_dict(row.get("raw_payload")).get("event_type")),
        (_safe_dict(row.get("event")).get("event_type")),
    ):
        token = _normalize_token(candidate)
        if token:
            return token

    return ""


def _collect_signals(
    *,
    level_state: Dict[str, Any] | None,
    scene_generation: Dict[str, Any] | None,
    recent_rule_events: List[Dict[str, Any]] | None,
) -> Set[str]:
    signals: Set[str] = set()

    level_map = _safe_dict(level_state)
    scene_map = _safe_dict(scene_generation)

    current_stage = _normalize_token(level_map.get("current_stage"))
    if current_stage:
        signals.add(f"level_stage:{current_stage}")

    for stage in _normalize_token_list(level_map.get("stage_path")):
        signals.add(f"level_stage:{stage}")

    scene_state = _safe_dict(scene_map.get("scene_state"))
    scene_graph = _safe_dict(scene_map.get("scene_graph"))

    selected_root = _normalize_token(scene_map.get("selected_root"))
    if selected_root:
        signals.add(f"scene:{selected_root}")

    for root_candidate in (scene_state.get("root"), scene_graph.get("root")):
        root = _normalize_token(root_candidate)
        if root:
            signals.add(f"scene:{root}")

    for node_id in _normalize_token_list(scene_map.get("fragments")):
        signals.add(f"scene:{node_id}")

    for node_id in _normalize_token_list(scene_state.get("nodes")):
        signals.add(f"scene:{node_id}")

    for node_id in _normalize_token_list(scene_graph.get("nodes")):
        signals.add(f"scene:{node_id}")

    for row in list(recent_rule_events or []):
        if not isinstance(row, dict):
            continue

        event_type = _event_type_from_row(row)
        if event_type:
            signals.add(f"event:{event_type}")

        payload = _safe_dict(row.get("payload"))
        if not payload:
            payload = _safe_dict(_safe_dict(row.get("raw_payload")).get("payload"))
        if not payload:
            payload = _safe_dict(_safe_dict(row.get("event")).get("payload"))

        resource = ""
        for key in ("resource", "item", "item_type", "block_type"):
            resource = normalize_inventory_resource_token(payload.get(key))
            if resource:
                break

        if resource:
            signals.add(f"collect:{_normalize_token(resource)}")

    return signals


def evaluate_narrative_state(
    *,
    level_state: Dict[str, Any] | None,
    scene_generation: Dict[str, Any] | None,
    recent_rule_events: List[Dict[str, Any]] | None = None,
    current_node_hint: str | None = None,
) -> Dict[str, Any]:
    graph = load_narrative_graph()

    signals = _collect_signals(
        level_state=level_state,
        scene_generation=scene_generation,
        recent_rule_events=recent_rule_events,
    )

    unlocked_nodes: List[str] = []
    for node_id in graph.node_order:
        rule = graph.nodes.get(node_id)
        if not rule:
            continue
        if all(requirement in signals for requirement in rule.requires):
            unlocked_nodes.append(node_id)

    current_node = _normalize_token(current_node_hint)
    if current_node not in graph.nodes:
        current_node = graph.entry_node

    current_rule = graph.nodes.get(current_node)
    if current_rule is None:
        current_node = graph.entry_node
        current_rule = graph.nodes.get(current_node)

    transition_candidates: List[NarrativeTransitionCandidate] = []
    blocked_union: List[str] = []

    for candidate_node in list(current_rule.next_nodes if current_rule else []):
        candidate_rule = graph.nodes.get(candidate_node)
        if not candidate_rule:
            continue

        blocked_by = [requirement for requirement in candidate_rule.requires if requirement not in signals]
        satisfied = len(blocked_by) == 0

        transition_candidates.append(
            NarrativeTransitionCandidate(
                node=candidate_node,
                requires=list(candidate_rule.requires),
                blocked_by=list(blocked_by),
                satisfied=satisfied,
            )
        )

        for requirement in blocked_by:
            if requirement not in blocked_union:
                blocked_union.append(requirement)

    state = NarrativeState(
        version="narrative_state_v1",
        graph_version=graph.version,
        current_arc=current_rule.arc if current_rule else "main",
        current_node=current_node,
        unlocked_nodes=unlocked_nodes,
        completed_nodes=[],
        transition_candidates=transition_candidates,
        blocked_by=blocked_union,
        observed_signals=sorted(signals),
    )

    return state.to_dict()
