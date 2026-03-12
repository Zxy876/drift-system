from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Set, Tuple

from .narrative_policy import load_narrative_policy
from .narrative_transition_log import (
    NarrativeTransitionLogEntry,
    NarrativeTransitionLogStore,
    narrative_transition_log_store,
)


def _normalize_token(value: Any) -> str:
    token = str(value or "").strip().lower()
    if not token:
        return ""
    return token.replace("-", "_").replace(" ", "_").strip("_")


def _normalize_token_list(raw_value: Any) -> List[str]:
    rows: List[str] = []
    seen: Set[str] = set()
    if not isinstance(raw_value, list):
        return rows

    for item in raw_value:
        token = _normalize_token(item)
        if not token or token in seen:
            continue
        seen.add(token)
        rows.append(token)
    return rows


def _safe_int(value: Any, default: int = 0) -> int:
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return int(default)


def _observed_signals_from_narrative_state(narrative_state: Dict[str, Any]) -> Set[str]:
    return set(_normalize_token_list(narrative_state.get("observed_signals")))


def _asset_signals_from_scene_generation(scene_generation: Dict[str, Any] | None) -> Set[str]:
    payload = scene_generation if isinstance(scene_generation, dict) else {}

    asset_tokens: Set[str] = set()
    selected_assets = payload.get("selected_assets") if isinstance(payload.get("selected_assets"), list) else []
    asset_selection = payload.get("asset_selection") if isinstance(payload.get("asset_selection"), dict) else {}
    candidate_assets = asset_selection.get("candidate_assets") if isinstance(asset_selection.get("candidate_assets"), list) else []

    for item in list(selected_assets) + list(candidate_assets):
        token = _normalize_token(item)
        if token:
            asset_tokens.add(token)

    return {f"asset:{token}" for token in sorted(asset_tokens)}


def _level_signals(level_state: Dict[str, Any] | None) -> Set[str]:
    payload = level_state if isinstance(level_state, dict) else {}
    rows: Set[str] = set()
    current_stage = _normalize_token(payload.get("current_stage"))
    if current_stage:
        rows.add(f"level_stage:{current_stage}")
    for stage in _normalize_token_list(payload.get("stage_path")):
        rows.add(f"level_stage:{stage}")
    return rows


def _event_signals(recent_rule_events: List[Dict[str, Any]] | None) -> Set[str]:
    rows: Set[str] = set()
    for event in list(recent_rule_events or []):
        if not isinstance(event, dict):
            continue

        event_type = _normalize_token(event.get("event_type"))
        if event_type:
            rows.add(f"event:{event_type}")

        payload = event.get("payload") if isinstance(event.get("payload"), dict) else {}
        resource = ""
        for key in ("resource", "item", "item_type", "block_type"):
            token = _normalize_token(payload.get(key))
            if token:
                resource = token
                break
        if resource:
            rows.add(f"collect:{resource}")

    return rows


def _requirements_by_axis(requirements: List[str]) -> Dict[str, List[str]]:
    grouped = {
        "scene": [],
        "event": [],
        "asset": [],
        "level": [],
    }

    for requirement in _normalize_token_list(requirements):
        if requirement.startswith("scene:"):
            grouped["scene"].append(requirement)
        elif requirement.startswith("event:") or requirement.startswith("collect:"):
            grouped["event"].append(requirement)
        elif requirement.startswith("asset:"):
            grouped["asset"].append(requirement)
        elif requirement.startswith("level_stage:"):
            grouped["level"].append(requirement)

    return grouped


def _all_requirements_satisfied(requirements: List[str], signals: Set[str]) -> bool:
    if not requirements:
        return True
    return all(requirement in signals for requirement in requirements)


def _score_candidate(
    candidate: Dict[str, Any],
    *,
    policy: Dict[str, Any],
    all_signals: Set[str],
) -> Tuple[int, List[str], Dict[str, Any]]:
    requirements = _normalize_token_list(candidate.get("requires"))
    grouped = _requirements_by_axis(requirements)

    weights = policy.get("weights") if isinstance(policy.get("weights"), dict) else {}
    score = 0
    matched_axes: List[str] = []

    axis_mapping = {
        "scene": "scene_match",
        "event": "event_match",
        "asset": "asset_match",
        "level": "level_match",
    }

    for axis, requirement_list in grouped.items():
        if not requirement_list:
            continue
        if _all_requirements_satisfied(requirement_list, all_signals):
            weight_key = axis_mapping.get(axis, "")
            axis_score = _safe_int(weights.get(weight_key), 0)
            score += axis_score
            matched_axes.append(axis)

    details = {
        "requirements": requirements,
        "grouped_requirements": grouped,
        "matched_axes": list(matched_axes),
        "score": int(score),
    }
    return score, matched_axes, details


def _transition_id(current_node: str, node: str) -> str:
    normalized_current = _normalize_token(current_node)
    normalized_node = _normalize_token(node)
    if normalized_current and normalized_node:
        return f"{normalized_current}_to_{normalized_node}"
    return normalized_node


def _ranking_tuple(candidate: Dict[str, Any], tie_break_order: List[str]) -> Tuple[Any, ...]:
    tuple_rows: List[Any] = [-_safe_int(candidate.get("score"), 0)]
    for token in tie_break_order:
        if token == "priority":
            tuple_rows.append(-_safe_int(candidate.get("priority"), 0))
        elif token == "target_node_lexicographic":
            tuple_rows.append(str(candidate.get("target_node") or ""))

    tuple_rows.append(str(candidate.get("target_node") or ""))
    tuple_rows.append(str(candidate.get("transition_id") or ""))
    return tuple(tuple_rows)


@dataclass
class NarrativeDecision:
    player_id: str
    current_node: str | None
    chosen_transition: str | None
    target_node: str | None
    reason: str
    blocked_by: List[str]
    input_snapshot: Dict[str, Any]
    decided_at_ms: int

    def to_dict(self) -> Dict[str, Any]:
        return {
            "player_id": str(self.player_id or "default"),
            "current_node": _normalize_token(self.current_node),
            "chosen_transition": _normalize_token(self.chosen_transition),
            "target_node": _normalize_token(self.target_node),
            "reason": str(self.reason or ""),
            "blocked_by": _normalize_token_list(self.blocked_by),
            "input_snapshot": dict(self.input_snapshot or {}),
            "decided_at_ms": _safe_int(self.decided_at_ms, int(time.time() * 1000)),
        }


def choose_transition(
    player_id: str,
    mode: str = "auto_best",
    *,
    transition_id: str | None = None,
    narrative_state: Dict[str, Any] | None = None,
    scene_generation: Dict[str, Any] | None = None,
    level_state: Dict[str, Any] | None = None,
    recent_rule_events: List[Dict[str, Any]] | None = None,
    transition_log_store: NarrativeTransitionLogStore | None = None,
) -> Dict[str, Any]:
    normalized_player = str(player_id or "").strip() or "default"
    normalized_mode = str(mode or "auto_best").strip().lower() or "auto_best"
    normalized_transition_id = _normalize_token(transition_id)

    state_payload = dict(narrative_state or {})
    current_node = _normalize_token(state_payload.get("current_node"))
    candidates = state_payload.get("transition_candidates") if isinstance(state_payload.get("transition_candidates"), list) else []
    blocked_union = _normalize_token_list(state_payload.get("blocked_by"))

    policy = load_narrative_policy()
    tie_break_order = policy.get("tie_break_order") if isinstance(policy.get("tie_break_order"), list) else ["priority", "target_node_lexicographic"]

    all_signals = set(_observed_signals_from_narrative_state(state_payload))
    all_signals.update(_asset_signals_from_scene_generation(scene_generation))
    all_signals.update(_level_signals(level_state))
    all_signals.update(_event_signals(recent_rule_events))

    candidate_rows: List[Dict[str, Any]] = []
    for raw_candidate in candidates:
        if not isinstance(raw_candidate, dict):
            continue

        target_node = _normalize_token(raw_candidate.get("node"))
        if not target_node:
            continue

        candidate_requires = _normalize_token_list(raw_candidate.get("requires"))
        candidate_blocked = _normalize_token_list(raw_candidate.get("blocked_by"))
        candidate_satisfied = bool(raw_candidate.get("satisfied")) and len(candidate_blocked) == 0

        candidate_transition_id = _normalize_token(raw_candidate.get("transition_id"))
        if not candidate_transition_id:
            candidate_transition_id = _transition_id(current_node, target_node)

        score, matched_axes, score_details = _score_candidate(
            raw_candidate,
            policy=policy,
            all_signals=all_signals,
        )

        candidate_rows.append(
            {
                "transition_id": candidate_transition_id,
                "target_node": target_node,
                "priority": _safe_int(raw_candidate.get("priority"), 0),
                "requires": candidate_requires,
                "blocked_by": candidate_blocked,
                "satisfied": candidate_satisfied,
                "score": score,
                "matched_axes": matched_axes,
                "score_details": score_details,
            }
        )

    selected_row: Optional[Dict[str, Any]] = None
    decision_reason = ""
    decision_blocked_by: List[str] = []

    if normalized_transition_id:
        matched = [row for row in candidate_rows if _normalize_token(row.get("transition_id")) == normalized_transition_id]
        if not matched:
            decision_reason = "transition_not_found"
            decision_blocked_by = []
        else:
            row = matched[0]
            if bool(row.get("satisfied")):
                selected_row = row
                decision_reason = f"explicit_transition:score={_safe_int(row.get('score'), 0)}"
            else:
                decision_reason = "transition_blocked"
                decision_blocked_by = _normalize_token_list(row.get("blocked_by"))
    else:
        if normalized_mode != "auto_best":
            normalized_mode = "auto_best"

        satisfied_rows = [row for row in candidate_rows if bool(row.get("satisfied"))]
        if not satisfied_rows:
            decision_reason = "no_satisfied_candidates"
            decision_blocked_by = list(blocked_union)
        else:
            selected_row = sorted(
                satisfied_rows,
                key=lambda row: _ranking_tuple(row, _normalize_token_list(tie_break_order)),
            )[0]
            matched_axes = list(selected_row.get("matched_axes") or [])
            matched_text = "+".join(matched_axes) if matched_axes else "none"
            decision_reason = f"auto_best:score={_safe_int(selected_row.get('score'), 0)}:{matched_text}"

    decided_at_ms = int(time.time() * 1000)

    input_snapshot = {
        "mode": normalized_mode,
        "requested_transition_id": normalized_transition_id or None,
        "current_node": current_node,
        "transition_candidates": [
            {
                "transition_id": row.get("transition_id"),
                "target_node": row.get("target_node"),
                "satisfied": bool(row.get("satisfied")),
                "score": _safe_int(row.get("score"), 0),
                "blocked_by": _normalize_token_list(row.get("blocked_by")),
            }
            for row in candidate_rows
        ],
        "observed_signals": sorted(all_signals),
        "selected_assets": _normalize_token_list((scene_generation or {}).get("selected_assets")),
        "theme_filter": dict((scene_generation or {}).get("theme_filter") or {}),
    }

    chosen_transition = _normalize_token((selected_row or {}).get("transition_id"))
    target_node = _normalize_token((selected_row or {}).get("target_node"))

    if selected_row is not None:
        decision_blocked_by = []

    decision = NarrativeDecision(
        player_id=normalized_player,
        current_node=current_node,
        chosen_transition=chosen_transition or None,
        target_node=target_node or None,
        reason=decision_reason,
        blocked_by=list(decision_blocked_by),
        input_snapshot=input_snapshot,
        decided_at_ms=decided_at_ms,
    )
    decision_payload = decision.to_dict()

    updated_state = dict(state_payload)
    updated_state.setdefault("version", "narrative_state_v1")
    updated_state.setdefault("graph_version", str(state_payload.get("graph_version") or "p8a_v1"))
    updated_state.setdefault("current_arc", str(state_payload.get("current_arc") or "main"))
    updated_state.setdefault("unlocked_nodes", _normalize_token_list(state_payload.get("unlocked_nodes")))
    updated_state.setdefault("completed_nodes", _normalize_token_list(state_payload.get("completed_nodes")))
    updated_state["blocked_by"] = list(decision_payload.get("blocked_by") or [])

    if chosen_transition and target_node:
        previous_node = _normalize_token(updated_state.get("current_node"))
        completed_nodes = _normalize_token_list(updated_state.get("completed_nodes"))
        if previous_node and previous_node not in completed_nodes:
            completed_nodes.append(previous_node)
        updated_state["completed_nodes"] = completed_nodes

        unlocked_nodes = _normalize_token_list(updated_state.get("unlocked_nodes"))
        if target_node not in unlocked_nodes:
            unlocked_nodes.append(target_node)
        updated_state["unlocked_nodes"] = unlocked_nodes
        updated_state["current_node"] = target_node

        entry = NarrativeTransitionLogEntry(
            player_id=normalized_player,
            from_node=previous_node or None,
            transition_id=chosen_transition,
            to_node=target_node,
            reason=str(decision_payload.get("reason") or ""),
            input_snapshot=dict(input_snapshot),
            created_at_ms=decided_at_ms,
        )
        store = transition_log_store or narrative_transition_log_store
        log_row = store.append_entry(entry)
    else:
        log_row = None

    updated_state["last_decision"] = dict(decision_payload)

    return {
        "decision": decision_payload,
        "narrative_state": updated_state,
        "transition_log_entry": log_row,
        "candidate_scores": [
            {
                "transition_id": row.get("transition_id"),
                "target_node": row.get("target_node"),
                "score": _safe_int(row.get("score"), 0),
                "priority": _safe_int(row.get("priority"), 0),
                "satisfied": bool(row.get("satisfied")),
                "blocked_by": _normalize_token_list(row.get("blocked_by")),
            }
            for row in candidate_rows
        ],
    }
