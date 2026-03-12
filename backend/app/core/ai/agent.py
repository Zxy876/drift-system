# backend/app/core/ai/agent.py

"""
最小可运行的 AI 决策器：
- 输入世界状态 world_state(dict)
- 返回 {"option": int | None}
"""

from typing import Dict, Any


def decide_next_step(world_state: Dict[str, Any]) -> Dict[str, int | None]:
    """
    世界状态示例:
    {
        "player": {
            "x": 12.3,
            "y": 70.0,
            "z": -4.7,
            "speed": 0.14,
            "moving": true
        },
        "time": 103,
        ...
    }
    """

    player = world_state.get("player", {})
    speed = player.get("speed", 0)
    moving = player.get("moving", False)
    x = float(player.get("x", 0))
    z = float(player.get("z", 0))

    # === AI 简单规则：未来会替换深度模型 ===

    # 1. 玩家第一次移动 → 推进剧情 option 0
    if speed > 0.2:
        return {"option": 0}

    # 2. 玩家接近 (0,0)“昆明湖中心” → 推进 option 1
    if (x**2 + z**2) ** 0.5 < 5:
        return {"option": 1}

    # 3. 其他情况：暂不推进
    return {"option": None}
