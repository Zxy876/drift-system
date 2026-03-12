"""Quest runtime regression tests for Phase 3 features.

Run with:

    cd backend
    python -m unittest test_quest_runtime.py
"""

from __future__ import annotations

import unittest

from app.core.quest.runtime import QuestRuntime
from app.core.story.story_loader import Level, TUTORIAL_CANONICAL_ID
from app.core.story.level_schema import RuleListener
from app.core.npc import npc_engine


def build_level(tasks):
    level = Level(
        level_id="quest_test_level",
        title="Quest Test Level",
        text=["Test narrative block."],
        tags=[],
        mood={},
        choices=[],
        meta={},
        npcs=[],
        bootstrap_patch={},
        tree=None,
    )
    setattr(level, "tasks", tasks)
    setattr(level, "rule_graph", None)
    return level


def build_tutorial_level(exit_patch):
    level = Level(
        level_id=TUTORIAL_CANONICAL_ID,
        title="Flagship Tutorial",
        text=["Tutorial narrative"],
        tags=[],
        mood={},
        choices=[],
        meta={},
        npcs=[],
        bootstrap_patch={},
        tree=None,
    )
    setattr(level, "tasks", [])
    setattr(level, "rule_graph", None)
    raw_payload = {"tutorial_exit_patch": exit_patch or {}}
    setattr(level, "_raw_payload", raw_payload)
    return level


class QuestRuntimeTests(unittest.TestCase):
    def setUp(self):
        tasks = [
            {
                "id": "kill_goat",
                "type": "kill",
                "target": {"name": "goat"},
                "count": 2,
                "reward": {"world_patch": {"mc": {"effect": "kill_reward"}}},
                "dialogue": {"on_complete": "你战胜了山羊。"},
                "issue_node": {
                    "title": "击败山羊",
                    "text": "消灭两只山羊来稳住你的情绪。",
                },
            },
            {
                "id": "talk_mentor",
                "type": "interact",
                "target": "mentor_awu",
                "reward": {"world_patch": {"mc": {"title": "和阿无谈话成功"}}},
                "dialogue": {"on_complete": "阿无点头回应。"},
                "issue_node": {
                    "title": "和阿无对话",
                    "text": "与阿无交流一次，分享你的情绪。",
                },
            },
        ]
        self.level = build_level(tasks)
        self.player = "quest_test_player"
        self.runtime = QuestRuntime()
        self.runtime.load_level_tasks(self.level, self.player)

    def test_multi_task_kill_and_summary_flow(self):
        issued = self.runtime.issue_tasks_on_beat(self.level, self.player, {"id": "beat_1"})
        self.assertIsNotNone(issued, "First task should issue on beat completion")
        snapshot = self.runtime.get_runtime_snapshot(self.player)
        self.assertEqual(snapshot["tasks"][0]["status"], "issued")

        match = self.runtime.record_event(
            self.player,
            {"type": "kill", "target_id": "GoAt"},
        )
        self.assertIsNotNone(match, "First kill should produce a progress payload")
        progress_node = next(
            (node for node in match.get("nodes", []) if node.get("type") == "task_progress"),
            None,
        )
        self.assertIsNotNone(progress_node, "Progress node should appear after first kill")
        self.assertEqual(progress_node.get("task_id"), "kill_goat")
        self.assertEqual(progress_node.get("task_title"), "击败山羊")
        self.assertEqual(progress_node.get("hint"), "消灭两只山羊来稳住你的情绪。")
        self.assertEqual(progress_node.get("remaining"), 1)

        completed = self.runtime.record_event(
            self.player,
            {"event_type": "kill", "target": "goat"},
        )
        self.assertIsNotNone(completed, "Second kill should return completion payload")
        self.assertIn(
            "kill_goat",
            completed.get("completed_tasks", []),
            "Completion payload should list kill task",
        )
        completion_node = next(
            (node for node in completed.get("nodes", []) if node.get("type") == "task_complete"),
            None,
        )
        self.assertIsNotNone(completion_node, "Completion node should be emitted for finished task")
        self.assertEqual(completion_node.get("title"), "击败山羊")
        self.assertEqual(completion_node.get("hint"), "消灭两只山羊来稳住你的情绪。")

        issued_second = self.runtime.issue_tasks_on_beat(self.level, self.player, {"id": "beat_2"})
        self.assertIsNotNone(issued_second, "Second task should issue after kill task")

        talk_completed = self.runtime.record_event(
            self.player,
            {"type": "interact", "target_id": "mentor_awu"},
        )
        self.assertIsNotNone(talk_completed, "Interact task should return completion payload")
        self.assertIn(
            "talk_mentor",
            talk_completed.get("completed_tasks", []),
            "Interact task should complete immediately",
        )

        updates = self.runtime.check_completion(self.level, self.player)
        self.assertIsNotNone(updates, "Completion check should surface updates")
        self.assertTrue(updates.get("exit_ready"), "All tasks completed should trigger exit_ready")
        self.assertIn("summary", updates, "Completion should include summary node")
        self.assertIn("kill_goat", updates.get("completed_tasks", []))
        self.assertIn("talk_mentor", updates.get("completed_tasks", []))

        world_patch = updates.get("world_patch", {})
        mc_patch = world_patch.get("mc", {}) if isinstance(world_patch, dict) else {}
        self.assertEqual(mc_patch.get("effect"), "kill_reward", "Reward merge should retain first reward effect")
        self.assertEqual(mc_patch.get("title"), "和阿无谈话成功", "Reward merge should include second reward title")

        final_snapshot = self.runtime.get_runtime_snapshot(self.player)
        self.assertTrue(final_snapshot.get("exit_ready"), "Snapshot should mark exit readiness after summary")

    def tearDown(self):
        npc_engine.active_npcs.clear()
        npc_engine.rule_bindings.clear()
        npc_engine.active_rule_refs.clear()


class QuestRuntimeRuleEventTests(unittest.TestCase):
    def setUp(self):
        self.player = "rule_event_player"
        self.runtime = QuestRuntime()
        npc_engine.active_npcs.clear()
        npc_engine.rule_bindings.clear()
        npc_engine.active_rule_refs.clear()

    def tearDown(self):
        npc_engine.active_npcs.clear()
        npc_engine.rule_bindings.clear()
        npc_engine.active_rule_refs.clear()

    def test_rule_trigger_tracks_milestones_and_rewards(self):
        tasks = [
            {
                "id": "collect_sunflower",
                "type": "interact",
                "target": "sunflower",
                "count": 2,
                "milestones": [
                    {
                        "id": "collect_sunflower_stage1",
                        "target": "sunflower",
                        "count": 1,
                    }
                ],
                "reward": {
                    "world_patch": {
                        "tell": "你闻到了花香。",
                    }
                },
                "dialogue": {
                    "on_complete": "你采集了所有向日葵。",
                },
            }
        ]
        level = build_level(tasks)
        self.runtime.load_level_tasks(level, self.player)
        self.runtime.issue_tasks_on_beat(level, self.player, {"id": "beat_seed"})

        first_response = self.runtime.handle_rule_trigger(
            self.player,
            {
                "event_type": "interact",
                "target": "sunflower",
            },
        )

        self.assertIsNotNone(first_response, "Rule trigger should respond for issued task")
        self.assertIn("milestones", first_response, "Milestone completion should be surfaced")
        self.assertIn("active_tasks", first_response, "Quest snapshot should accompany rule response")
        active_snapshot = first_response.get("active_tasks") or {}
        self.assertIn("task_titles", active_snapshot, "Snapshot should list task titles")
        self.assertIn("milestone_names", active_snapshot, "Snapshot should list milestone names")
        self.assertGreaterEqual(active_snapshot.get("remaining_total", 0), 0, "Remaining total should be non-negative")
        self.assertIn(
            "collect_sunflower_stage1",
            first_response.get("milestones", []),
            "First milestone should complete on initial interaction",
        )
        milestone_node = next(
            (node for node in first_response.get("nodes", []) if node.get("type") == "task_milestone"),
            None,
        )
        self.assertIsNotNone(milestone_node, "Milestone node should be emitted for milestone completion")
        self.assertTrue(milestone_node.get("hint"), "Milestone node should include a hint for players")

        snapshot_mid = self.runtime.get_active_tasks_snapshot(self.player)
        self.assertIsNotNone(snapshot_mid, "Snapshot should be present while tasks remain")
        self.assertIn("active_count", snapshot_mid, "Snapshot should include active_count metadata")
        self.assertIn("remaining_total", snapshot_mid, "Snapshot should expose remaining_total metadata")

        second_response = self.runtime.handle_rule_trigger(
            self.player,
            {
                "event_type": "interact",
                "target": "sunflower",
            },
        )

        self.assertIsNotNone(second_response, "Second trigger should return completion payload")
        self.assertIn(
            "collect_sunflower",
            second_response.get("completed_tasks", []),
            "Task completion should be listed in completed_tasks",
        )
        world_patch = second_response.get("world_patch") or {}
        self.assertEqual(
            world_patch.get("tell"),
            "你闻到了花香。",
            "Reward world_patch should be merged into aggregated response",
        )
        completion_node = next(
            (node for node in second_response.get("nodes", []) if node.get("type") == "task_complete"),
            None,
        )
        self.assertIsNotNone(completion_node, "Completion node should be emitted for finished task")
        final_snapshot = self.runtime.get_active_tasks_snapshot(self.player)
        self.assertIsNone(final_snapshot, "Snapshot should clear once all quests are complete")

    def test_rule_trigger_merges_npc_behavior_payload(self):
        level = build_level([])
        self.runtime.load_level_tasks(level, self.player)
        npc_engine.register_npc(level.level_id, {})

        listener = RuleListener(
            type="chat",
            targets=["mia"],
            quest_event="greet_mia",
            metadata={
                "dialogue": {
                    "title": "米娅",
                    "script": [
                        {"op": "npc_say", "npc": "米娅", "text": "你好，旅行者。"},
                        {"op": "narrate", "text": "她递来一杯热茶。"},
                    ],
                    "choices": [
                        {"label": "谢谢", "command": "/thank"},
                        {"label": "有任务吗？"},
                    ],
                },
                "dialogue_hint": "可以继续询问她关于城镇的消息。",
                "world_patch": {
                    "tell": "米娅向你微笑。",
                },
                "commands": ["say {player} greeted Mia"],
            },
        )
        self.runtime.register_rule_listener(level.level_id, listener)

        response = self.runtime.handle_rule_trigger(
            self.player,
            {
                "event_type": "chat",
                "payload": {
                    "quest_event": "greet_mia",
                },
            },
        )

        self.assertIsNotNone(response, "NPC rule payload should be returned even without tasks")
        self.assertIn("nodes", response, "NPC dialogue should surface as nodes")
        dialogue_node = next(
            (node for node in response.get("nodes", []) if node.get("type") == "npc_dialogue"),
            None,
        )
        self.assertIsNotNone(dialogue_node, "Dialogue node should be emitted from NPC metadata")
        script = dialogue_node.get("script")
        self.assertIsNotNone(script, "Structured script should propagate to dialogue nodes")
        self.assertEqual(script[0].get("npc"), "米娅")
        self.assertIn("choices", dialogue_node, "Dialogue choices should be forwarded")
        self.assertEqual(dialogue_node["choices"][0].get("label"), "谢谢")
        self.assertEqual(dialogue_node.get("hint"), "可以继续询问她关于城镇的消息。")
        self.assertIn("commands", response, "NPC commands should be bubbled to caller")
        self.assertIn(
            "say {player} greeted Mia",
            response.get("commands", []),
            "Command list should propagate metadata commands",
        )
        npc_patch = response.get("world_patch", {})
        self.assertEqual(npc_patch.get("tell"), "米娅向你微笑。", "NPC world_patch should merge into response")

    def test_tutorial_completion_emits_milestone_and_exit_patch(self):
        exit_patch = {
            "mc": {
                "tell": "教程完成，欢迎回到主线。",
                "teleport": {
                    "world": "KunmingLakeHub",
                    "x": 128.5,
                    "y": 72.0,
                    "z": -16.5,
                },
            }
        }
        level = build_tutorial_level(exit_patch)
        self.runtime.load_level_tasks(level, self.player)

        self.runtime.handle_rule_trigger(
            self.player,
            {
                "event_type": "quest_event",
                "payload": {"quest_event": "tutorial_meet_guide"},
            },
        )
        completion = self.runtime.handle_rule_trigger(
            self.player,
            {
                "event_type": "quest_event",
                "payload": {"quest_event": "tutorial_complete"},
            },
        )

        self.assertIsNotNone(completion, "Tutorial completion should yield a response payload")
        self.assertTrue(completion.get("exit_ready"), "Tutorial completion should mark exit readiness")
        self.assertIn(
            "tutorial_complete",
            completion.get("milestones", []),
            "Tutorial milestone should be emitted exactly once",
        )
        self.assertTrue(
            completion.get("tutorial_completed"),
            "Tutorial completion flag should be set",
        )
        self.assertEqual(
            completion.get("next_level"),
            "flagship_03",
            "Tutorial completion should nominate flagship_03 as the next level",
        )
        self.assertEqual(
            completion.get("world_patch"),
            exit_patch,
            "Tutorial exit patch should be forwarded to the caller",
        )
        level_exit = completion.get("level_exit") or {}
        self.assertEqual(
            level_exit.get("next_level"),
            "flagship_03",
            "Level exit payload should target flagship_03",
        )
        self.assertTrue(
            level_exit.get("auto"),
            "Level exit signal should request automatic transition",
        )

        repeat = self.runtime.handle_rule_trigger(
            self.player,
            {
                "event_type": "quest_event",
                "payload": {"quest_event": "tutorial_complete"},
            },
        )
        milestones = repeat.get("milestones") if isinstance(repeat, dict) else []
        self.assertNotIn(
            "tutorial_complete",
            milestones or [],
            "Tutorial completion should not emit twice",
        )


if __name__ == "__main__":
    unittest.main()
