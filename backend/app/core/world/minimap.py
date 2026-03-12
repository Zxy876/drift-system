from __future__ import annotations
from typing import Dict, List, Any, Tuple
from collections import defaultdict
import math


class MiniMap:
    """
    MiniMap —— 心悦宇宙的世界略缩图（螺旋漂移布局）

    - 以 (512,512) 为中心点
    - 按螺旋排列（飘移感/星轨感）
    """

    def __init__(self, story_graph):
        self.graph = story_graph

        # level → {"x": float , "y": float}
        self.positions: Dict[str, Dict[str, float]] = {}

        # 玩家状态
        self.player_state: Dict[str, Dict[str, Any]] = defaultdict(
            lambda: {"pos": (0, 0, 0), "unlocked": set(), "current": None}
        )

        self.mainline: List[str] = story_graph.all_levels()

        # 螺旋排布
        self._auto_layout_spiral()

    def refresh(self) -> None:
        """Recompute layout when the story graph reloads levels."""

        self.mainline = self.graph.all_levels()
        self.positions.clear()
        self._auto_layout_spiral()

    # -----------------------------------------------------
    # 螺旋漂移布局（中心 = 512,512）
    # -----------------------------------------------------
    def _auto_layout_spiral(self):
        cx, cy = 512, 512  # 画布中心对应背景书本中央

        R0 = 80        # 初始半径（越小越贴近书本）
        dR = 22        # 每一关往外扩张的距离
        dTheta = 0.55  # 弧度步长（越小越紧密）

        for i, lv in enumerate(self.mainline):
            r = R0 + dR * i
            theta = i * dTheta

            x = cx + r * math.cos(theta)
            y = cy + r * math.sin(theta)

            self.positions[lv] = {"x": x, "y": y}

    # -----------------------------------------------------
    # 玩家进入关卡（自动解锁）
    # -----------------------------------------------------
    def enter_level(self, player_id: str, level_id: str):
        ps = self.player_state[player_id]
        ps["unlocked"].add(level_id)
        ps["current"] = level_id
        print(f"[MiniMap] Player {player_id} entered level {level_id}")

    # -----------------------------------------------------
    # 玩家移动更新
    # -----------------------------------------------------
    def update_player_pos(self, player_id: str, pos: Tuple[float, float, float]):
        self.player_state[player_id]["pos"] = tuple(pos)

    # -----------------------------------------------------
    # 外部手动解锁
    # -----------------------------------------------------
    def mark_unlocked(self, player_id: str, level_id: str):
        self.player_state[player_id]["unlocked"].add(level_id)

    # -----------------------------------------------------
    # 推荐下一关
    # -----------------------------------------------------
    def _recommended_next(self, player_id: str):
        ps = self.player_state[player_id]
        unlocked = ps["unlocked"]

        if not unlocked:
            return "level_01"

        for lv in self.mainline:
            if lv not in unlocked:
                return lv
        return None

    # -----------------------------------------------------
    # 玩家视角
    # -----------------------------------------------------
    def to_dict(self, player_id: str) -> Dict[str, Any]:
        ps = self.player_state[player_id]

        nodes = []
        for lv in self.mainline:
            nodes.append({
                "level": lv,
                "pos": self.positions[lv],           # 已经是绝对像素坐标
                "neighbors": self.graph.neighbors(lv),
                "unlocked": (lv in ps["unlocked"]),
            })

        return {
            "player_id": player_id,
            "nodes": nodes,
            "player_pos": ps["pos"],
            "current_level": ps["current"],
            "recommended_next": self._recommended_next(player_id),
        }

    # -----------------------------------------------------
    def to_dict_global(self) -> Dict[str, Any]:
        return {
            "levels": self.mainline,
            "nodes": [
                {
                    "level": lv,
                    "pos": self.positions[lv],
                    "neighbors": self.graph.neighbors(lv),
                }
                for lv in self.mainline
            ],
        }

    # -----------------------------------------------------
    def reset_player(self, player_id: str):
        if player_id in self.player_state:
            del self.player_state[player_id]

    # -----------------------------------------------------
    def recommended_next(self, player_id: str):
        return self._recommended_next(player_id)