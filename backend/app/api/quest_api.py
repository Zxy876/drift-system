# backend/app/api/quest_api.py

from typing import Any, Dict, Optional

from fastapi import APIRouter
from pydantic import BaseModel, Field

from app.core.quest.runtime import quest_runtime
from app.core.story.story_engine import story_engine

router = APIRouter(prefix="/quests")


class QuestEventPayload(BaseModel):
    type: str = Field(..., description="Event type, e.g. kill/break/interact")
    target_id: Optional[str] = Field(None, description="Identifier of the target entity/block")
    meta: Dict[str, Any] = Field(default_factory=dict, description="Additional event context")


@router.get("/{player_id}/status")
def get_quest_status(player_id: str) -> Dict[str, Any]:
    snapshot = quest_runtime.get_runtime_snapshot(player_id)
    state = story_engine.player_state.get(player_id, {})
    level_id = snapshot.get("level_id") or state.get("current_level")
    return {
        "status": "ok",
        "snapshot": snapshot,
        "level_id": level_id,
        "exit_ready": bool(state.get("quest_exit_ready")),
    }


@router.post("/{player_id}/event")
def post_quest_event(player_id: str, payload: QuestEventPayload) -> Dict[str, Any]:
    event = {
        "type": payload.type,
        "target_id": payload.target_id,
        "meta": payload.meta,
    }
    response = story_engine.handle_event(player_id, event)
    response.setdefault("snapshot", quest_runtime.get_runtime_snapshot(player_id))
    response.setdefault("status", "ok")
    return response
