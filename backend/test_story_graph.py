import json
import os
import shutil
import tempfile
import unittest

from app.core.story.story_graph import StoryGraph

class StoryGraphRecommendationTest(unittest.TestCase):
    def setUp(self):
        self.tempdir = tempfile.mkdtemp(prefix="story-graph-test-")
        self._write_level("flagship_01.json", {
            "id": "flagship_1",
            "title": "Level 1",
            "text": ["intro"],
            "tags": ["main"],
            "mood": {"base": "calm", "intensity": 0.5},
            "choices": [],
            "meta": {"chapter": 1},
        })
        self._write_level("flagship_02.json", {
            "id": "flagship_2",
            "title": "Level 2",
            "text": ["next"],
            "tags": ["main"],
            "mood": {"base": "calm", "intensity": 0.5},
            "choices": [],
            "meta": {"chapter": 2},
        })
        self._write_level("tutorial_level.json", {
            "id": "tutorial_level",
            "title": "Tutorial",
            "text": ["start"],
            "tags": ["tutorial"],
            "mood": {"base": "calm", "intensity": 0.5},
            "choices": [],
            "meta": {"chapter": 0},
        })

        self.graph = StoryGraph(self.tempdir)

    def tearDown(self):
        shutil.rmtree(self.tempdir)

    def test_canonicalizes_numeric_level_ids(self):
        self.assertEqual(self.graph.canonicalize_level_id("flagship_1"), "flagship_01")
        self.assertEqual(self.graph.canonicalize_level_id("flagship_01"), "flagship_01")
        # legacy aliases should still resolve to the new flagship id
        self.assertEqual(self.graph.canonicalize_level_id("level_1"), "flagship_01")
        self.assertEqual(self.graph.canonicalize_level_id("tutorial_level"), "tutorial_level")

    def test_recommendation_prefers_mainline_after_exit(self):
        player_id = "player_test"
        self.graph.update_trajectory(player_id, "flagship_1", "enter")
        self.graph.update_trajectory(player_id, "flagship_1", "exit")

        recommendations = self.graph.recommend_next_levels(player_id, "flagship_1", limit=2)
        self.assertGreaterEqual(len(recommendations), 1)
        self.assertEqual(recommendations[0]["level_id"], "flagship_02")
        self.assertEqual(recommendations[0]["title"], "Level 2")

    def test_recommendation_returns_fresh_start(self):
        recommendations = self.graph.recommend_next_levels("new_player", None, limit=1)
        self.assertEqual(recommendations[0]["level_id"], "flagship_01")
        self.assertTrue(recommendations[0]["reasons"])
        self.assertEqual(recommendations[0]["title"], "Level 1")

    def _write_level(self, filename: str, payload: dict) -> None:
        path = os.path.join(self.tempdir, filename)
        with open(path, "w", encoding="utf-8") as fh:
            json.dump(payload, fh)


if __name__ == "__main__":
    unittest.main()
