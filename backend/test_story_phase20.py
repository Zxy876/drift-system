import contextlib
from pathlib import Path
import sys

from fastapi.testclient import TestClient

BASE_DIR = Path(__file__).resolve().parents[1]
BACKEND_SRC = BASE_DIR / "backend"
if str(BACKEND_SRC) not in sys.path:
    sys.path.insert(0, str(BACKEND_SRC))

from app.core.story.story_loader import load_level
from app.core.story.story_graph import StoryGraph
from app.core.story.story_engine import story_engine
from app.main import app

FLAGSHIP_DIR = BACKEND_SRC / "data" / "flagship_levels"


def test_legacy_ids_map_to_flagship_tutorial():
    aliases = ["level_01", "level_1", "level01", "level1", "tutorial", "tutorial_level", "level_tutorial"]
    for alias in aliases:
        level = load_level(alias)
        assert level.level_id == "flagship_tutorial"


def test_story_graph_canonicalizes_tutorial_aliases():
    graph = StoryGraph(str(FLAGSHIP_DIR))
    for alias in ["level_01", "level_1", "level01", "level1", "tutorial", "tutorial_level", "level_tutorial"]:
        assert graph.canonicalize_level_id(alias) == "flagship_tutorial"


def test_default_entry_level_is_flagship_tutorial():
    assert story_engine.DEFAULT_ENTRY_LEVEL == "flagship_tutorial"


def test_world_story_endpoints_available():
    client = TestClient(app)
    player = "phase20_tester"

    with contextlib.suppress(Exception):
        story_engine.load_level_for_player(player, "flagship_tutorial")

    resp_state = client.get(f"/world/state/{player}")
    assert resp_state.status_code == 200

    resp_quest = client.get(f"/world/story/{player}/quest-log")
    assert resp_quest.status_code == 200

    resp_weather = client.get(f"/world/story/{player}/emotional-weather")
    assert resp_weather.status_code == 200
