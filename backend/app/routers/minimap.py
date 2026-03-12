# backend/app/routers/minimap.py
from fastapi import APIRouter
from app.core.story.story_engine import story_engine

router = APIRouter(prefix="/minimap", tags=["MiniMap"])

@router.get("/state")
def get_state():
    """全局地图（所有关卡布局）"""
    return story_engine.minimap.to_dict_global()

@router.get("/player/{player_id}")
def get_player_minimap(player_id: str):
    """玩家视角地图：哪些关卡已解锁"""
    return story_engine.minimap.to_dict(player_id)

@router.post("/unlock/{player_id}/{level_id}")
def unlock_level(player_id: str, level_id: str):
    story_engine.minimap.mark_unlocked(player_id, level_id)
    return {"status": "ok", "player": player_id, "level": level_id}