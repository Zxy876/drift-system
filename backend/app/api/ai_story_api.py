# app/api/ai_story_api.py

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
import httpx

router = APIRouter()

# 你以后可以替换为 OpenAI / DeepSeek / 本地模型
AI_URL = "http://127.0.0.1:5001/ai"   # 先假设你 AI 服务在这里

@router.post("/ai-react")
async def ai_react_to_world(request: Request, world_state: dict):
    """
    给 AI 世界状态 (来自 MC 行为驱动后的 world_state)
    AI 返回 decision.option -> 推进剧情
    """
    story_engine = request.app.state.story_engine  # ✅ 从 app.state 取引擎

    # 1) 发给 AI
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            ai_resp = await client.post(AI_URL, json=world_state)
        ai_json = ai_resp.json()
    except Exception as e:
        return JSONResponse(content={
            "triggered": False,
            "error": f"AI service not reachable: {e}"
        })

    # 2) 解析 AI 决策
    decision = ai_json.get("decision", {})
    option = decision.get("option", None)

    # 3) 推进剧情
    if option is not None:
        next_node = story_engine.go_next(int(option))
        return JSONResponse(content={
            "triggered": True,
            "option": option,
            "node": next_node
        })

    return JSONResponse(content={"triggered": False, "reason": "no option returned"})
