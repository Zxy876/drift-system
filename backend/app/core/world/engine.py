import math
from typing import Dict, Any

class WorldEngine:
    def __init__(self):
        self.state = {
            "entities": {},
            "variables": {
                "speed": 0.0,
                "angle": 0.0,
                "friction": 0.5,
                "x": 0.0, "y": 0.0, "z": 0.0,
                "vx": 0.0, "vz": 0.0,
            }
        }

    def get_state(self):
        return self.state

    # 原来的 apply（玩家 move/say 进来时）
    def apply(self, action: dict):
        v = self.state["variables"]
        move = action.get("move")
        if move:
            # 你现有 move 协议
            for k in ["x","y","z","speed","moving"]:
                if k in move:
                    v[k] = move[k]
        return {
            "status": "ok",
            "variables": v,
            "entities": self.state["entities"]
        }

    # 新增：AI patch 真正改世界
    def apply_patch(self, patch: Dict[str, Any]):
        v = self.state["variables"]
        ent = self.state["entities"]

        vars_patch = patch.get("variables", {})
        if isinstance(vars_patch, dict):
            for k, val in vars_patch.items():
                v[k] = val

        ent_patch = patch.get("entities", {})
        if isinstance(ent_patch, dict):
            ent.update(ent_patch)

        # mc patch 不在后端执行，只透传给前端/插件
        mc_patch = patch.get("mc")

        return {
            "status": "ok",
            "variables": v,
            "entities": ent,
            **({"mc": mc_patch} if mc_patch else {})
        }

    def tick(self, dt=0.05):
        v = self.state["variables"]

        v["speed"] = max(0.0, v["speed"] - v["friction"] * dt)
        rad = math.radians(v["angle"])
        v["vx"] = v["speed"] * math.cos(rad)
        v["vz"] = v["speed"] * math.sin(rad)
        v["x"] += v["vx"] * dt
        v["z"] += v["vz"] * dt
        return v