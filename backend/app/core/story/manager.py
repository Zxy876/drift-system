# backend/app/core/story/manager.py
from typing import Tuple, Dict, Any, Optional
from app.core.story.story_engine import story_engine

def should_advance(player_id: str, world_state: Dict[str, Any], action: Dict[str, Any]) -> bool:
    return story_engine.should_advance(player_id, world_state, action)

def advance(player_id: str, world_state: Dict[str, Any], action: Dict[str, Any]) -> Tuple[Optional[int], Dict[str, Any]]:
    return story_engine.advance(player_id, world_state, action)