# backend/app/api/npc_api.py
from fastapi import APIRouter
from typing import Dict, Any
from pydantic import BaseModel

from app.core.npc import npc_engine
from app.core.story.story_engine import story_engine

router = APIRouter(prefix="/npc", tags=["NPC"])


class NPCInteractionRequest(BaseModel):
    player_id: str
    level_id: str
    message: str  # 玩家发送的消息


@router.get("/behaviors/{level_id}")
def get_npc_behaviors(level_id: str):
    """获取指定关卡的NPC行为列表"""
    behaviors = npc_engine.get_npc_behaviors(level_id)
    
    return {
        "status": "ok",
        "level_id": level_id,
        "behaviors": [
            {
                "type": b.type,
                "description": b.description,
                "config": b.config
            }
            for b in behaviors
        ]
    }


@router.post("/interact")
def interact_with_npc(request: NPCInteractionRequest):
    """
    处理玩家与NPC的交互
    支持自然语言触发NPC行为
    """
    result = npc_engine.handle_player_interaction(
        request.level_id,
        request.message
    )
    
    if not result:
        return {
            "status": "no_response",
            "message": "NPC没有回应"
        }
    
    # 构建MC指令
    mc_commands = []
    
    if result["type"] == "dialogue":
        # 对话响应
        for msg in result.get("messages", []):
            mc_commands.append({
                "tell": msg
            })
    
    elif result["type"] == "quest_trigger":
        # 任务触发
        mc_commands.append({
            "tell": f"§e✨ 任务开始：{result['quest_name']}"
        })
        mc_commands.append({
            "tell": result.get("npc_response", "")
        })
        
        # 可以添加奖励给予
        for reward in result.get("rewards", []):
            if reward == "speed_boost":
                mc_commands.append({
                    "effect": {
                        "type": "SPEED",
                        "duration": 600,
                        "amplifier": 1
                    }
                })
            elif reward == "experience":
                mc_commands.append({
                    "give_xp": 100
                })
    
    return {
        "status": "ok",
        "interaction_type": result["type"],
        "mc": mc_commands
    }


@router.get("/context/{level_id}")
def get_npc_ai_context(level_id: str):
    """
    获取NPC的AI上下文（用于对话生成）
    """
    context = npc_engine.get_behavior_context_for_ai(level_id)
    ai_hints = npc_engine.get_npc_ai_hints(level_id)
    
    return {
        "status": "ok",
        "level_id": level_id,
        "ai_hints": ai_hints,
        "full_context": context
    }


@router.post("/command/{level_id}")
def execute_npc_command(level_id: str, command: Dict[str, Any]):
    """
    执行针对NPC的自然语言命令
    例如："让桃子巡逻赛道"、"让诗人朗诵一首诗"
    """
    player_id = command.get("player_id", "system")
    instruction = command.get("instruction", "")
    
    # 这里可以用AI解析自然语言指令
    # 暂时返回简单响应
    
    return {
        "status": "ok",
        "message": f"指令已发送给 {level_id} 的NPC",
        "mc": {
            "tell": f"§7[系统] NPC收到指令: {instruction}"
        }
    }
