# backend/app/routers/story.py
from fastapi import APIRouter

from app.core.story.story_engine import story_engine

router = APIRouter(prefix="/story", tags=["story"])


@router.post("/load/{player_id}/{level_id}")
def load_level(player_id: str, level_id: str):
    """
    给 MC 插件的“跳关加载剧情”接口。
    返回 bootstrap_patch，MC 会用 WorldPatchExecutor 执行。
    """
    patch = story_engine.load_level_for_player(player_id, level_id)
    return {"bootstrap_patch": patch, "state": story_engine.get_public_state(player_id)}