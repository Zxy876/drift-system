import sys
import types
import unittest


class _RequestsStub(types.SimpleNamespace):
    Timeout = Exception
    RequestException = Exception

    @staticmethod
    def post(*_args, **_kwargs):
        raise RuntimeError("requests stub invoked during tests")


sys.modules.setdefault("requests", _RequestsStub())
sys.modules.setdefault("dotenv", types.SimpleNamespace(load_dotenv=lambda: None))

from app.core.story.story_engine import StoryEngine
from app.core.story.level_schema import SceneConfig


class DummyEngine(StoryEngine):
    def __init__(self):
        # Skip heavy StoryEngine initialization for targeted metadata tests.
        pass


class SceneMetadataTests(unittest.TestCase):
    def test_attach_scene_metadata_includes_npc_skins(self):
        engine = DummyEngine()
        level = type("Level", (), {})()
        level.level_id = "metadata_demo"
        level.scene = SceneConfig.from_dict(
            {
                "world": "KunmingLakeStory",
                "npc_skins": [
                    {"id": "Serene Gardener", "skin": "skins/gardener.png"},
                    {"id": "Traveler", "skin": None},
                ],
            }
        )

        payload = {}
        engine._attach_scene_metadata(payload, level)

        scene_meta = payload.get("_scene")
        self.assertIsNotNone(scene_meta, "Scene metadata should be attached to payload")
        self.assertEqual(scene_meta.get("level_id"), "metadata_demo")
        skins = scene_meta.get("npc_skins")
        self.assertIsInstance(skins, list)
        self.assertEqual(len(skins), 1)
        self.assertEqual(skins[0].get("id"), "Serene Gardener")


if __name__ == "__main__":
    unittest.main()
