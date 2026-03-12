# backend/app/core/ai/ai_agent.py

class AIAgent:
    """
    非常简单的 AI：
    - 观察 world_state
    - 判断玩家是否进入“触发区”
    - 决定要不要推进剧情
    """

    def __init__(self):
        self.last_x = None
        self.last_z = None

    def react(self, world_state: dict) -> dict:
        player = world_state.get("player", {})
        x = player.get("x")
        z = player.get("z")

        if x is None or z is None:
            return {"trigger": False}

        # 初始化
        if self.last_x is None:
            self.last_x = x
            self.last_z = z
            return {"trigger": False}

        # 玩家移动距离
        dx = abs(x - self.last_x)
        dz = abs(z - self.last_z)
        dist = dx + dz

        # 更新历史
        self.last_x = x
        self.last_z = z

        # 移动超过阈值 → 推进剧情
        if dist > 0.7:
            return {"trigger": True, "option": 0}

        return {"trigger": False}
