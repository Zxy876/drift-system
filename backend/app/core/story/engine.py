# backend/app/core/story/engine.py
from dataclasses import dataclass, field
from typing import Dict, Any, Tuple, Optional, List
import time, math
from collections import deque

from app.core.ai.deepseek_agent import deepseek_decide

@dataclass
class PlayerStoryState:
    current_node_id: str = "B0_START"
    last_advance_ts: float = 0.0
    last_pos: Tuple[float, float, float] = (0.0, 0.0, 0.0)
    history: deque = field(default_factory=lambda: deque(maxlen=40))  # [{"role","content"}]

class StoryEngine:
    def __init__(self):
        self.players: Dict[str, PlayerStoryState] = {}
        self.start_node_id = "B0_START"

        # ✅ 节奏参数（你可以调）
        self.cooldown_sec = 6.0         # 最短 6 秒推进一次
        self.min_move_dist = 2.5        # 移动超过 2.5 格才可能推进
        self.force_on_say = True        # 玩家说话强制推进

    # --------- public helpers ----------
    def _get_player(self, player_id: str) -> PlayerStoryState:
        if player_id not in self.players:
            self.players[player_id] = PlayerStoryState(current_node_id=self.start_node_id)
        return self.players[player_id]

    def get_public_state(self) -> Dict[str, Any]:
        return {
            "start_node_id": self.start_node_id,
            "players": list(self.players.keys()),
            "cooldown_sec": self.cooldown_sec,
            "min_move_dist": self.min_move_dist
        }

    # --------- pacing ----------
    def should_advance(self, player_id: str, world_state: Dict[str, Any], action: Dict[str, Any]) -> bool:
        ps = self._get_player(player_id)
        now = time.time()

        # 1) 聊天输入强触发
        if self.force_on_say and action.get("say"):
            return True

        # 2) 时间冷却
        if now - ps.last_advance_ts < self.cooldown_sec:
            return False

        # 3) 距离阈值
        move = action.get("move")
        if not move:
            return False

        x, y, z = move.get("x", 0), move.get("y", 0), move.get("z", 0)
        lx, ly, lz = ps.last_pos
        dist = math.sqrt((x-lx)**2 + (y-ly)**2 + (z-lz)**2)
        if dist < self.min_move_dist:
            return False

        return True

    # --------- advance ----------
    def advance(self, player_id: str, world_state: Dict[str, Any], action: Dict[str, Any]) -> Tuple[Optional[int], Dict[str, Any]]:
        ps = self._get_player(player_id)
        now = time.time()

        # 更新 last_pos
        move = action.get("move") or {}
        if move:
            ps.last_pos = (move.get("x", 0), move.get("y", 0), move.get("z", 0))

        # 组 context（给 AI）
        context = {
            "player_id": player_id,
            "current_node_id": ps.current_node_id,
            "world_state": world_state,
            "action": action
        }

        ai_json = deepseek_decide(context=context, history=list(ps.history))

        option = ai_json.get("option", None)
        node = ai_json.get("node") or {"title": "昆明湖", "text": "湖水静静地等你下一步。"}

        # 写入历史，让下一次连贯
        ps.history.append({"role": "assistant", "content": f"{node['title']}\n{node['text']}"})
        if action.get("say"):
            ps.history.append({"role": "user", "content": action["say"]})

        # 更新时间
        ps.last_advance_ts = now

        # 简单推进 node_id（你未来可以接 tree / story graph）
        ps.current_node_id = ps.current_node_id + "_NEXT"

        return option, node