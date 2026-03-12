from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Tuple

from .scene_state import SceneState


@dataclass
class SceneDiff:
    added_nodes: List[str] = field(default_factory=list)
    added_edges: List[Tuple[str, str]] = field(default_factory=list)
    added_positions: Dict[str, Dict[str, int]] = field(default_factory=dict)
    trigger_event_keys: List[str] = field(default_factory=list)

    def is_empty(self) -> bool:
        return not self.added_nodes and not self.added_edges and not self.added_positions

    def to_dict(self) -> Dict[str, Any]:
        return {
            "added_nodes": list(self.added_nodes),
            "added_edges": [{"from": source, "to": target} for source, target in self.added_edges],
            "added_positions": {node: dict(value) for node, value in self.added_positions.items()},
            "trigger_event_keys": list(self.trigger_event_keys),
        }


def build_scene_diff(
    previous: SceneState,
    current: SceneState,
    *,
    trigger_event_keys: List[str] | None = None,
) -> SceneDiff:
    previous_nodes = set(previous.nodes)
    previous_edges = set(previous.edges)

    added_nodes = [node for node in current.nodes if node not in previous_nodes]
    added_edges = [edge for edge in current.edges if edge not in previous_edges]

    added_positions: Dict[str, Dict[str, int]] = {}
    for node in added_nodes:
        position = current.positions.get(node)
        if isinstance(position, dict):
            added_positions[node] = {
                "x": int(position.get("x", 0)),
                "z": int(position.get("z", 0)),
            }

    return SceneDiff(
        added_nodes=added_nodes,
        added_edges=added_edges,
        added_positions=added_positions,
        trigger_event_keys=list(trigger_event_keys or []),
    )
