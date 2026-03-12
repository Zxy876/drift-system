# backend/app/routers/level_loader_route.py
from __future__ import annotations

from fastapi import APIRouter

from app.core.story.story_engine import story_engine

router = APIRouter(prefix="/story", tags=["story"])


@router.post("/load_level")
def load_level_api(player_id: str, level_id: str):
    """
    手动加载某一关（通常用于调试或从外部工具强制跳关）。
    真实游戏过程中更推荐通过 /world/apply + /level 命令来切换。
    """
    patch = story_engine.load_level_for_player(player_id, level_id)
    state = story_engine.get_public_state(player_id)
    level = state.get("level") or level_id

    return {
        "status": "ok",
        "level": level,
        "bootstrap_patch": patch,
        "engine_state": state,
    }
