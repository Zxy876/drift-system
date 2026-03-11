from __future__ import annotations

from typing import Any, Dict, Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from app.core.narrative.poetry_engine import (
    build_poetry_resources,
    default_poetry_scene_hint,
    extract_poetry_concepts,
    suggest_poetry_scene_theme,
)
from app.core.semantic.player_tag_store import player_tag_store


router = APIRouter(prefix="/poetry", tags=["Poetry"])


def _normalize_text(value: Any) -> str:
    return str(value or "").strip()


class PoetryGenerateRequest(BaseModel):
    player_id: str = Field(default="default", min_length=1)
    poem: str = Field(min_length=1)
    scene_theme: Optional[str] = None
    scene_hint: Optional[str] = None
    anchor: Optional[str] = None
    player_position: Optional[Dict[str, Any]] = None
    max_resources: int = Field(default=12, ge=1, le=48)


class PoetryCommandRequest(BaseModel):
    player_id: str = Field(default="default", min_length=1)
    command: str = Field(min_length=1)
    poem: Optional[str] = None
    scene_theme: Optional[str] = None
    scene_hint: Optional[str] = None
    anchor: Optional[str] = None
    player_position: Optional[Dict[str, Any]] = None
    max_resources: int = Field(default=12, ge=1, le=48)


def _extract_poem_from_command(command: str) -> str:
    normalized = _normalize_text(command)
    if not normalized:
        return ""

    lowered = normalized.lower()
    if lowered.startswith("/poem"):
        return normalized[5:].strip()
    if lowered.startswith("poem "):
        return normalized[5:].strip()
    return ""


def _generate_poetry_scene_payload(
    *,
    player_id: str,
    poem: str,
    explicit_theme: Optional[str],
    explicit_hint: Optional[str],
    anchor: Optional[str],
    player_position: Optional[Dict[str, Any]],
    max_resources: int,
) -> Dict[str, Any]:
    try:
        player_tags = player_tag_store.list_player_tags(player_id)
    except Exception:
        player_tags = []

    concept_payload = extract_poetry_concepts(poem)
    concept_scores = concept_payload.get("concept_scores") if isinstance(concept_payload.get("concept_scores"), dict) else {}

    resources_payload = build_poetry_resources(
        concept_scores,
        player_tag_rows=player_tags,
        max_resources=max_resources,
    )
    resource_weights = resources_payload.get("resources") if isinstance(resources_payload.get("resources"), dict) else {}

    scene_theme = suggest_poetry_scene_theme(
        concept_scores,
        semantic_payload=concept_payload.get("semantic_engine") if isinstance(concept_payload.get("semantic_engine"), dict) else None,
        explicit_theme=explicit_theme,
    )
    poem_preview = default_poetry_scene_hint(poem)
    scene_hint = explicit_hint

    try:
        from app.api.story_api import build_scene_events, _scene_event_plan_to_world_patch

        scene_output = build_scene_events(
            player_id=player_id,
            scene_theme=scene_theme,
            scene_hint=scene_hint,
            text=poem,
            anchor=anchor,
            player_position=player_position,
            registry_resources=resource_weights,
        )
        world_patch = _scene_event_plan_to_world_patch(scene_output)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"poetry scene generation failed: {exc}") from exc

    scene_plan = scene_output.get("scene_plan") if isinstance(scene_output.get("scene_plan"), dict) else {}
    scoring_debug = scene_output.get("scoring_debug") if isinstance(scene_output.get("scoring_debug"), dict) else {}
    event_plan = scene_output.get("event_plan") if isinstance(scene_output.get("event_plan"), list) else []
    fragments = scene_plan.get("fragments") if isinstance(scene_plan.get("fragments"), list) else []

    return {
        "status": "ok",
        "msg": "Poetry scene generated.",
        "player_id": player_id,
        "poem": poem,
        "scene_theme": scene_theme,
        "scene_hint": scene_hint,
        "poem_preview": poem_preview,
        "semantic_engine": concept_payload.get("semantic_engine"),
        "concepts": concept_payload.get("concepts") if isinstance(concept_payload.get("concepts"), list) else [],
        "concept_scores": dict(concept_scores),
        "resource_weights": dict(resource_weights),
        "resource_trace": resources_payload.get("resource_trace") if isinstance(resources_payload.get("resource_trace"), dict) else {},
        "resource_source_stats": resources_payload.get("source_stats") if isinstance(resources_payload.get("source_stats"), dict) else {},
        "player_tag_matches": resources_payload.get("player_tag_matches") if isinstance(resources_payload.get("player_tag_matches"), list) else [],
        "selected_root": scoring_debug.get("selected_root"),
        "selected_fragments": list(fragments),
        "fragment_count": len(fragments),
        "event_count": len(event_plan),
        "reasons": dict(scoring_debug.get("reasons") or {}),
        "scene": scene_output,
        "world_patch": world_patch if isinstance(world_patch, dict) else {},
    }


@router.post("/generate")
def generate_poetry_scene(payload: PoetryGenerateRequest):
    player_id = _normalize_text(payload.player_id) or "default"
    poem = _normalize_text(payload.poem)
    if not poem:
        raise HTTPException(status_code=400, detail="poem is required")

    explicit_theme = _normalize_text(payload.scene_theme) or None
    explicit_hint = _normalize_text(payload.scene_hint) or None
    anchor = _normalize_text(payload.anchor) or None
    player_position = payload.player_position if isinstance(payload.player_position, dict) else None
    return _generate_poetry_scene_payload(
        player_id=player_id,
        poem=poem,
        explicit_theme=explicit_theme,
        explicit_hint=explicit_hint,
        anchor=anchor,
        player_position=player_position,
        max_resources=payload.max_resources,
    )


@router.post("/command")
def run_poetry_command(payload: PoetryCommandRequest):
    player_id = _normalize_text(payload.player_id) or "default"
    command = _normalize_text(payload.command)
    poem = _normalize_text(payload.poem) or _extract_poem_from_command(command)
    if not poem:
        raise HTTPException(status_code=400, detail="poem is required (use /poem <text> or poem field)")

    explicit_theme = _normalize_text(payload.scene_theme) or None
    explicit_hint = _normalize_text(payload.scene_hint) or None
    anchor = _normalize_text(payload.anchor) or None
    player_position = payload.player_position if isinstance(payload.player_position, dict) else None

    result = _generate_poetry_scene_payload(
        player_id=player_id,
        poem=poem,
        explicit_theme=explicit_theme,
        explicit_hint=explicit_hint,
        anchor=anchor,
        player_position=player_position,
        max_resources=payload.max_resources,
    )

    world_patch = result.get("world_patch") if isinstance(result.get("world_patch"), dict) else {}
    mc_patch = world_patch.get("mc") if isinstance(world_patch.get("mc"), dict) else {}

    return {
        **result,
        "command": command,
        "mc_actions": {
            "build_multi": list(mc_patch.get("build_multi") or []) if isinstance(mc_patch.get("build_multi"), list) else [],
            "spawn_multi": list(mc_patch.get("spawn_multi") or []) if isinstance(mc_patch.get("spawn_multi"), list) else [],
            "blocks": list(mc_patch.get("blocks") or []) if isinstance(mc_patch.get("blocks"), list) else [],
            "structure": list(mc_patch.get("structure") or []) if isinstance(mc_patch.get("structure"), list) else [],
        },
    }
