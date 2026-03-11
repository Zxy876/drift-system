from __future__ import annotations

from typing import Any, Dict, List

from fastapi import APIRouter

from app.core.story.narrative_graph_evaluator import load_narrative_graph


router = APIRouter(prefix="/narrative", tags=["Narrative"])


@router.get("/graph")
def get_narrative_graph() -> Dict[str, Any]:
    graph = load_narrative_graph()

    nodes: List[Dict[str, Any]] = []
    edges: List[Dict[str, str]] = []
    arc_counts: Dict[str, int] = {}

    for node_id in graph.node_order:
        rule = graph.nodes.get(node_id)
        if rule is None:
            continue

        arc_counts[rule.arc] = int(arc_counts.get(rule.arc, 0)) + 1
        nodes.append(
            {
                "id": node_id,
                "arc": rule.arc,
                "next": list(rule.next_nodes),
                "requires": list(rule.requires),
            }
        )

        for next_node in rule.next_nodes:
            edges.append(
                {
                    "from": node_id,
                    "to": next_node,
                }
            )

    return {
        "status": "ok",
        "version": graph.version,
        "entry_node": graph.entry_node,
        "node_count": len(nodes),
        "edge_count": len(edges),
        "arc_count": len(arc_counts),
        "arcs": arc_counts,
        "nodes": nodes,
        "edges": edges,
    }
