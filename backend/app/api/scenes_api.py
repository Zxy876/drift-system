from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict

from fastapi import APIRouter

from app.core.fragments.fragment_loader import fragment_registry_info, get_fragment_registry
from app.core.narrative.scene_library import FRAGMENT_GRAPH_FILE, SEMANTIC_TAGS_FILE
from app.core.semantic.semantic_registry import semantic_registry_info
from app.core.themes.theme_loader import get_theme_registry, theme_registry_info


router = APIRouter(prefix="/scenes", tags=["Scenes"])


def _read_json(path: Path) -> Any:
    if not path.exists() or not path.is_file():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None


@router.get("/library")
def get_scene_library() -> Dict[str, Any]:
    raw_fragment_graph = _read_json(FRAGMENT_GRAPH_FILE)
    raw_semantic_tags = _read_json(SEMANTIC_TAGS_FILE)

    fragment_graph = dict(raw_fragment_graph) if isinstance(raw_fragment_graph, dict) else {}
    semantic_tags = dict(raw_semantic_tags) if isinstance(raw_semantic_tags, dict) else {}

    try:
        fragment_registry = get_fragment_registry()
        fragments = fragment_registry.fragment_map() if hasattr(fragment_registry, "fragment_map") else {}
    except Exception:
        fragments = {}

    try:
        theme_registry = get_theme_registry()
        themes = theme_registry.theme_map() if hasattr(theme_registry, "theme_map") else {}
    except Exception:
        themes = {}

    return {
        "status": "ok",
        "meta": {
            "fragment_graph_root_count": len(fragment_graph),
            "semantic_tag_item_count": len(semantic_tags),
            "fragment_count": len(fragments),
            "theme_count": len(themes),
            "fragment_registry": fragment_registry_info(),
            "theme_registry": theme_registry_info(),
            "semantic_registry": semantic_registry_info(),
        },
        "fragment_graph": fragment_graph,
        "semantic_tags": semantic_tags,
        "fragments": fragments,
        "themes": themes,
    }
