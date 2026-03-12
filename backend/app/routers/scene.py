from typing import Any, Dict, Optional

from fastapi import APIRouter, Body, HTTPException

from app.core.story.story_engine import story_engine

router = APIRouter(prefix="/scene", tags=["scene"])


@router.post("/prepare/{player_id}/{level_id}")
def prepare_scene(
    player_id: str,
    level_id: str,
    payload: Optional[Dict[str, Any]] = Body(default=None),
):
    """Return the staged scene bundle for a player entering a level."""

    try:
        return story_engine.prepare_scene_for_player(player_id, level_id)
    except FileNotFoundError as exc:  # pragma: no cover - surfaced as HTTP error
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post("/release/{player_id}/{scene_id}")
def release_scene(
    player_id: str,
    scene_id: str,
    payload: Optional[Dict[str, Any]] = Body(default=None),
):
    """Notify the backend that a player has left the scene."""

    reason = None
    if isinstance(payload, dict):
        raw_reason = payload.get("reason")
        if isinstance(raw_reason, str):
            reason = raw_reason

    return story_engine.release_scene_for_player(player_id, scene_id, reason)
