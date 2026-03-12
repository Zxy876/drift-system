from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


@dataclass
class StoryNode:
    node_id: str
    node_type: str
    text: str
    event_type: str
    state_patch: Dict[str, Any] = field(default_factory=dict)


@dataclass
class GraphState:
    nodes: List[StoryNode] = field(default_factory=list)
    current_node_id: Optional[str] = None

    def append_node(self, node: StoryNode) -> None:
        self.nodes.append(node)
        self.current_node_id = node.node_id


@dataclass
class InternalState:
    phase: str = "intro"
    silence_count: int = 0
    tension: int = 0
    memory_flags: Dict[str, Any] = field(default_factory=dict)
    last_node_id: Optional[str] = None
    world_patch_hash: Optional[str] = None
    rule_version: Optional[str] = None
