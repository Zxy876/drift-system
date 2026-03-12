"""Regression test for StoryEngine beat progression (Phase 1).

Run with:

    cd backend
    source venv/bin/activate  # if available
    python test_beats_v1.py

The script loads level_03, feeds utterances that should sequentially
trigger each beat, and prints runtime snapshots alongside the returned
world patches.
"""

from __future__ import annotations

import json
from pprint import pprint
import unittest

from app.core.story.story_engine import story_engine


def snapshot_runtime(player_id: str):
    player_state = story_engine.players.get(player_id, {})
    beat_state = player_state.get("beat_state") or {}
    order = list(beat_state.get("order") or [])
    index = beat_state.get("index")
    completed = sorted(beat_state.get("completed") or [])
    memory_locked = sorted(beat_state.get("memory_locked") or [])
    locked_sources = beat_state.get("memory_locked_sources") or {}
    return {
        "order": order,
        "index": index,
        "completed": completed,
        "memory_locked": memory_locked,
        "locked_sources": locked_sources,
    }


def main():
    player = "beat_test_regression"
    world = {"variables": {}}

    utterances = [
        "开始",
        "我害怕",
        "呐喊",
        "怎么办",
        "我觉得不太好玩",
        "我愿意",
        "愿谁记得谁",
    ]

    # 使用新的 StoryEngine API 载入旗舰登山关卡
    initial_patch = story_engine.load_level_for_player(player, "flagship_03")
    print("== 初始 world_patch ==")
    pprint(initial_patch, width=100)

    for text in utterances:
        option, node, patch = story_engine.advance(player, world, {"say": text})
        print(f"=== 玩家说: {text}")
        print("option:")
        pprint(option, width=100)
        print("node:")
        pprint(node, width=100)
        print("patch:")
        pprint(patch, width=100)
        print("runtime:")
        pprint(snapshot_runtime(player), width=120)
        beat_state = story_engine.players[player].get("beat_state") or {}
        print("exit_ready:", sorted(beat_state.get("completed") or []))
        print("--")

    print("== 最终状态 ==")
    pprint(story_engine.players[player].get("beat_state"))
    print("pending_nodes:")
    pprint(story_engine.players[player].get("pending_nodes"))


if __name__ == "__main__":
    main()


class StoryEngineSmokeTest(unittest.TestCase):
    def test_flagship_level_loads(self):
        player = "beat_unittest"
        story_engine.players.pop(player, None)
        patch = story_engine.load_level_for_player(player, "flagship_03")
        self.assertIsInstance(patch, dict)
        state = story_engine.players.get(player, {})
        beat_state = state.get("beat_state")
        self.assertIsNotNone(beat_state)
        self.assertIn("order", beat_state)