from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, Iterable, List, Tuple


def _normalize_token(raw_value: Any) -> str:
    token = str(raw_value or "").strip().lower()
    if not token:
        return ""
    return token.replace("-", "_").replace(" ", "_").strip("_")


def _safe_int(value: Any, default: int = 0) -> int:
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return int(default)


def _normalize_nodes(raw_nodes: Any) -> List[str]:
    nodes: List[str] = []
    seen: set[str] = set()
    if not isinstance(raw_nodes, list):
        return nodes

    for item in raw_nodes:
        token = _normalize_token(item)
        if not token or token in seen:
            continue
        seen.add(token)
        nodes.append(token)

    return nodes


def _normalize_edges(raw_edges: Any) -> List[Tuple[str, str]]:
    edges: List[Tuple[str, str]] = []
    seen: set[Tuple[str, str]] = set()
    if not isinstance(raw_edges, list):
        return edges

    for item in raw_edges:
        source = ""
        target = ""
        if isinstance(item, dict):
            source = _normalize_token(item.get("from"))
            target = _normalize_token(item.get("to"))
        elif isinstance(item, (list, tuple)) and len(item) >= 2:
            source = _normalize_token(item[0])
            target = _normalize_token(item[1])

        if not source or not target:
            continue

        edge = (source, target)
        if edge in seen:
            continue

        seen.add(edge)
        edges.append(edge)

    return edges


def _normalize_positions(raw_positions: Any) -> Dict[str, Dict[str, int]]:
    positions: Dict[str, Dict[str, int]] = {}
    if not isinstance(raw_positions, dict):
        return positions

    for key, value in raw_positions.items():
        node_id = _normalize_token(key)
        if not node_id or not isinstance(value, dict):
            continue

        positions[node_id] = {
            "x": _safe_int(value.get("x"), 0),
            "z": _safe_int(value.get("z"), 0),
        }

    return positions


@dataclass
class SceneState:
    level_id: str
    root: str
    nodes: List[str] = field(default_factory=list)
    edges: List[Tuple[str, str]] = field(default_factory=list)
    positions: Dict[str, Dict[str, int]] = field(default_factory=dict)
    spawned_nodes: List[str] = field(default_factory=list)
    version: int = 1

    def __post_init__(self) -> None:
        self.level_id = str(self.level_id or "").strip() or "runtime"
        self.root = _normalize_token(self.root)

        self.nodes = _normalize_nodes(self.nodes)
        self.edges = _normalize_edges(self.edges)
        self.positions = _normalize_positions(self.positions)
        self.spawned_nodes = _normalize_nodes(self.spawned_nodes)

        if self.root and self.root not in self.nodes:
            self.nodes.insert(0, self.root)

        for source, target in self.edges:
            if source not in self.nodes:
                self.nodes.append(source)
            if target not in self.nodes:
                self.nodes.append(target)

        for node_id in list(self.positions.keys()):
            if node_id not in self.nodes:
                del self.positions[node_id]

        if self.root and self.root not in self.positions:
            self.positions[self.root] = {"x": 0, "z": 0}

        if self.version < 1:
            self.version = 1

    def add_node(self, node_id: str) -> None:
        token = _normalize_token(node_id)
        if token and token not in self.nodes:
            self.nodes.append(token)

    def add_edge(self, source: str, target: str) -> None:
        src = _normalize_token(source)
        dst = _normalize_token(target)
        if not src or not dst:
            return

        self.add_node(src)
        self.add_node(dst)
        edge = (src, dst)
        if edge not in self.edges:
            self.edges.append(edge)

    def to_scene_graph_dict(self) -> Dict[str, Any]:
        return {
            "root": self.root,
            "nodes": list(self.nodes),
            "edges": [{"from": source, "to": target} for source, target in self.edges],
        }

    def to_layout_dict(self, strategy: str = "radial_v1") -> Dict[str, Any]:
        return {
            "strategy": str(strategy or "radial_v1"),
            "root": self.root,
            "positions": {node: dict(value) for node, value in self.positions.items()},
        }

    def to_dict(self) -> Dict[str, Any]:
        return {
            "level_id": self.level_id,
            "root": self.root,
            "nodes": list(self.nodes),
            "edges": [{"from": source, "to": target} for source, target in self.edges],
            "positions": {node: dict(value) for node, value in self.positions.items()},
            "spawned_nodes": list(self.spawned_nodes),
            "version": int(self.version),
        }

    @classmethod
    def from_dict(cls, payload: Dict[str, Any] | None, *, fallback_level_id: str = "runtime") -> "SceneState":
        source = payload if isinstance(payload, dict) else {}

        return cls(
            level_id=str(source.get("level_id") or fallback_level_id or "runtime"),
            root=str(source.get("root") or ""),
            nodes=list(source.get("nodes") or []),
            edges=list(source.get("edges") or []),
            positions=dict(source.get("positions") or {}),
            spawned_nodes=list(source.get("spawned_nodes") or []),
            version=_safe_int(source.get("version"), 1),
        )

    @classmethod
    def from_scene_payload(
        cls,
        *,
        level_id: str,
        scene_graph: Dict[str, Any] | None,
        layout: Dict[str, Any] | None,
        spawned_nodes: Iterable[str] | None = None,
        version: int = 1,
    ) -> "SceneState":
        graph_payload = scene_graph if isinstance(scene_graph, dict) else {}
        layout_payload = layout if isinstance(layout, dict) else {}

        nodes = list(graph_payload.get("nodes") or [])
        edges = list(graph_payload.get("edges") or [])
        positions = dict(layout_payload.get("positions") or {})

        if spawned_nodes is None:
            spawned: List[str] = list(nodes)
        else:
            spawned = list(spawned_nodes)

        return cls(
            level_id=str(level_id or "runtime"),
            root=str(graph_payload.get("root") or layout_payload.get("root") or ""),
            nodes=nodes,
            edges=edges,
            positions=positions,
            spawned_nodes=spawned,
            version=_safe_int(version, 1),
        )
