from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List


@dataclass
class SceneGraph:
    root: str
    nodes: List[str] = field(default_factory=list)
    edges: List[tuple[str, str]] = field(default_factory=list)

    def add_node(self, node_id: str) -> None:
        token = str(node_id or "").strip().lower()
        if not token:
            return
        if token not in self.nodes:
            self.nodes.append(token)

    def add_edge(self, source: str, target: str) -> None:
        src = str(source or "").strip().lower()
        dst = str(target or "").strip().lower()
        if not src or not dst:
            return
        self.add_node(src)
        self.add_node(dst)
        edge = (src, dst)
        if edge not in self.edges:
            self.edges.append(edge)

    def to_dict(self) -> Dict[str, object]:
        return {
            "root": str(self.root or "").strip().lower(),
            "nodes": list(self.nodes),
            "edges": [{"from": source, "to": target} for source, target in self.edges],
        }
