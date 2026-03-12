from __future__ import annotations
from typing import Any, Dict
from fastapi import APIRouter
from pydantic import BaseModel
from app.core.story.story_engine import story_engine
import logging

router = APIRouter(prefix="/world", tags=["world"])
logger = logging.getLogger("uvicorn.error")


class ApplyReq(BaseModel):
    player_id: str
    action: Dict[str, Any]
    world_state: Dict[str, Any] = {}


@router.post("/apply")
def apply(req: ApplyReq):
    player_id = req.player_id
    action = req.action or {}
    world_state = req.world_state or {}

    say = action.get("say", "")

    # --- 调试 /level 指令 ---
    if isinstance(say, str) and say.strip().startswith("/level"):
        parts = say.strip().split()
        if len(parts) >= 2:
            suffix = parts[1].rstrip(".json")
            canonical = story_engine.graph.canonicalize_level_id(suffix)
            if not canonical and not suffix.startswith("flagship_"):
                canonical = story_engine.graph.canonicalize_level_id(f"flagship_{suffix}")
            level_id = canonical or suffix
            patch = story_engine.load_level_for_player(player_id, level_id)

            result = {
                "status": "ok",
                "story_node": {"title": "关卡加载", "text": f"已加载关卡 {level_id}"},
                "world_patch": patch,
                "ai_option": None,
                "world_state": story_engine.get_public_state(player_id),
            }
            logger.warning("APPLY RETURN: %s", result)
            return result

    # --- 冷却，不推进剧情 ---
    if not story_engine.should_advance(player_id, world_state, action):
        result = {
            "status": "ok",
            "world_patch": {},
            "story_node": None,
            "ai_option": None,
            "world_state": story_engine.get_public_state(player_id),
        }
        logger.warning("APPLY RETURN: %s", result)
        return result

    # --- 正常推进剧情 ---
    option, node, patch = story_engine.advance(player_id, world_state, action)

    result = {
        "status": "ok",
        "ai_option": option,
        "story_node": node,
        "world_patch": patch,
        "world_state": story_engine.get_public_state(player_id),
    }

    logger.warning("APPLY RETURN: %s", result)
    return result


@router.get("/state/{player_id}")
def get_state(player_id: str):
    return story_engine.get_public_state(player_id)