# backend/app/core/world/trigger.py
from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, Set, List, Optional, Tuple, Any

from app.core.story.story_loader import list_levels


@dataclass
class TriggerPoint:
    """
    一个世界触发点：
    - id: 唯一标识
    - center: (x, y, z) 中心点（目前只用 x、z 做水平距离）
    - radius: 触发半径（方块数）
    - action: 动作类型：load_level / ...
    - level_id: 若 action 是 load_level，则指定要加载的 level_xx
    """
    id: str
    center: Tuple[float, float, float]
    radius: float
    action: str
    level_id: Optional[str] = None


class TriggerEngine:
    def __init__(self):
        # 全局触发点列表
        self.triggers: List[TriggerPoint] = []
        # per-player 已经触发过的 trigger_id
        self.fired: Dict[str, Set[str]] = {}

        self._bootstrap_default()

    def _bootstrap_default(self):
        """
        先做一个默认例子：
        玩家在世界 (0, 0) 附近（水平距离半径 5 格）时，会自动加载 level_01。
        之后你可以扩展为：
        - 从 JSON 读
        - 一关多个触发点等等
        """
        default_level = self._resolve_default_level_id()
        self.triggers.append(
            TriggerPoint(
                id=f"start_{default_level}",
                center=(0.0, 0.0, 0.0),   # (x, y, z)
                radius=5.0,
                action="load_level",
                level_id=default_level,
            )
        )

    def _resolve_default_level_id(self) -> str:
        try:
            levels = list_levels()
        except Exception:
            levels = []

        def _entry_to_id(entry: Dict[str, Any]) -> Optional[str]:
            file_name = entry.get("file")
            if isinstance(file_name, str):
                return file_name.replace(".json", "")
            identifier = entry.get("id")
            if isinstance(identifier, str):
                return identifier
            return None

        for entry in levels:
            level_id = _entry_to_id(entry)
            if level_id == "flagship_tutorial":
                return level_id

        for entry in levels:
            if entry.get("source") == "flagship" and not entry.get("deprecated"):
                level_id = _entry_to_id(entry)
                if level_id:
                    return level_id

        for entry in levels:
            level_id = _entry_to_id(entry)
            if level_id:
                return level_id

        return "flagship_01"

    def reset_player(self, player_id: str):
        """清空某个玩家已经触发过的记录"""
        self.fired.pop(player_id, None)

    def check(self, player_id: str, x: float, y: float, z: float) -> Optional[TriggerPoint]:
        """
        检查玩家当前位置是否命中某个触发点。
        目前只按水平距离 sqrt(dx^2 + dz^2) 判断，不考虑高度差。
        命中后：
        - 只触发一次（存入 fired）
        - 返回对应 TriggerPoint
        """
        if not self.triggers:
            return None

        fired = self.fired.setdefault(player_id, set())

        for t in self.triggers:
            if t.id in fired:
                continue

            dx = x - t.center[0]
            dz = z - t.center[2]
            dist2 = dx * dx + dz * dz

            if dist2 <= t.radius * t.radius:
                fired.add(t.id)
                return t

        return None


# 全局单例
trigger_engine = TriggerEngine()