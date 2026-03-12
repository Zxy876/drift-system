# backend/app/core/world/scene_generator.py
from __future__ import annotations
from typing import Dict, Any
from app.core.world.environment_builder import environment_builder

"""
SceneGenerator —— 根据关卡内容自动生成 MC 世界环境 patch
集成 EnvironmentBuilder 以生成真实的、可交互的游戏环境
"""


class SceneGenerator:

    def generate_for_level(self, level_id: str, level_data: dict) -> Dict[str, Any]:
        title = level_data.get("title", "")
        text_list = level_data.get("text", [])
        text = "\n".join(text_list)
        
        # 提取关卡元数据
        meta = level_data.get("meta", {})
        chapter = meta.get("chapter", 1)

        # ---- 智能场景识别 ----
        # 1. 检测漂移/赛车场景
        if any(keyword in text or keyword in title 
               for keyword in ["飘移", "漂移", "赛道", "赛车", "驾驶", "油门"]):
            return environment_builder.build_environment(
                "drift_track", level_id, 
                {"radius": 25 + chapter * 2, "width": 5}
            )

        # 2. 检测考试/学习场景
        if any(keyword in text or keyword in title 
               for keyword in ["考试", "试卷", "题目", "答案", "书桌"]):
            return environment_builder.build_environment(
                "exam_room", level_id,
                {"size": 20, "desks": min(10, chapter)}
            )

        # 3. 检测隧道/回溯场景
        if any(keyword in text or keyword in title 
               for keyword in ["隧道", "回溯", "黑暗", "洞穴"]):
            return environment_builder.build_environment(
                "tunnel", level_id,
                {"length": 40 + chapter * 5, "width": 5, "height": 5}
            )
        
        # 4. 检测情感/心灵场景
        if any(keyword in text or keyword in title 
               for keyword in ["心", "温暖", "爱", "感动"]):
            return environment_builder.build_environment(
                "heart_space", level_id,
                {"size": 10}
            )

        # 默认：虚空平台场景
        return environment_builder.build_environment(
            "void_platform", level_id,
            {"size": 12}
        )
