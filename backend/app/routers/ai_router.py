# backend/app/routers/ai_router.py
from fastapi import APIRouter
from pydantic import BaseModel
from typing import Any, Dict, Optional, List

from app.core.ai.intent_engine import parse_intent
from app.core.story.story_engine import story_engine

router = APIRouter(prefix="/ai", tags=["AI"])


# ================================
# 请求模型
# ================================
class IntentRequest(BaseModel):
    player_id: str = "default"
    text: str
    world_state: Optional[Dict[str, Any]] = None


# ================================
# 返回模型（⭐ 多意图版）
# ================================
class IntentResponse(BaseModel):
    status: str
    intents: List[Dict[str, Any]]


# ================================
# 路由：多意图自然语言解析
# ================================
@router.post("/intent", response_model=IntentResponse)
def ai_intent(req: IntentRequest):
    """
    玩家一句自然语言 → 多意图解析
    不推进剧情，只返回：
    {
      "status": "ok",
      "intents": [ ... ]
    }
    """
    result = parse_intent(
        player_id=req.player_id,
        text=req.text,
        world_state=req.world_state or {},
        story_engine=story_engine,
    )

    # parse_intent 已经返回 {status, intents}
    return IntentResponse(
        status=result["status"],
        intents=result["intents"]
    )