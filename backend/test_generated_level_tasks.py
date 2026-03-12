"""Phase 23 verification for natural-language task generation."""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

from fastapi.testclient import TestClient

BACKEND_ROOT = Path(__file__).resolve().parent
PARENT_ROOT = BACKEND_ROOT.parent
for candidate in (str(BACKEND_ROOT), str(PARENT_ROOT)):
    if candidate not in sys.path:
        sys.path.insert(0, candidate)

from app.api.level_api import GenerateLevelRequest, generate_story_level
from app.core.quest.runtime import quest_runtime
from app.main import story_engine, app


def _collect_player_session(player_id: str):
    state = quest_runtime._players.get(player_id)
    if not state:
        return None, None
    tasks = state.get("tasks") or []
    session = tasks[0] if tasks else None
    return state, session


def test_generated_level_emits_structured_tasks():
    description = (
        "在旧城区的雾气中寻找被遗忘的灯塔，"
        "沿着积水的街巷倾听居民的故事，"
        "最后在钟楼顶端点亮纪念之光。"
    )

    level_path: Path | None = None
    level_id: str | None = None
    player_id = "phase23_verifier"

    request = GenerateLevelRequest(description=description, title="记忆灯塔")
    response = asyncio.run(generate_story_level(request))
    assert response.get("status") == "ok"
    level_id = response.get("level_id")
    level_path = Path(response.get("path")) if response.get("path") else None
    assert level_id and level_path and level_path.exists()

    with TestClient(app) as client:
        try:
            story_engine.load_level_for_player(player_id, level_id)

            player_state = story_engine.players[player_id]
            level_obj = player_state["level"]
            assert getattr(level_obj, "tasks", []), "generated level should include tasks"

            beats = getattr(level_obj, "beats", [])
            assert beats, "generated level should expose beats"
            first_beat = beats[0]
            quest_runtime.issue_tasks_on_beat(level_obj, player_id, {"id": first_beat.id})

            state, session = _collect_player_session(player_id)
            assert state is not None and session is not None, "quest runtime must create a session"
            assert session.milestones, "session should include milestones"
            assert session.status == "issued"

            debug_pre = client.get(f"/world/story/{player_id}/debug/tasks")
            assert debug_pre.status_code == 200
            debug_pre_json = debug_pre.json()
            assert debug_pre_json.get("status") == "ok"
            assert isinstance(debug_pre_json.get("pending_conditions"), list)

            tokens: list[str] = []
            for milestone in session.milestones:
                candidate = milestone.target or milestone.event
                if isinstance(candidate, str):
                    tokens.append(candidate.lower())

            assert len(tokens) >= 3, "milestone-driven quest events should exist"

            for idx, token in enumerate(tokens):
                result = quest_runtime.handle_rule_trigger(
                    player_id,
                    {
                        "event_type": "quest_event",
                        "payload": {"quest_event": token},
                    },
                )
                if result:
                    story_engine.apply_quest_updates(player_id, result)

                if idx == 0:
                    debug_mid = client.get(f"/world/story/{player_id}/debug/tasks")
                    assert debug_mid.status_code == 200
                    debug_mid_json = debug_mid.json()
                    assert debug_mid_json.get("status") == "ok"
                    last_event = debug_mid_json.get("last_rule_event")
                    assert last_event is not None
                    assert last_event.get("matched") is True

            _, session_after = _collect_player_session(player_id)
            assert session_after is not None
            assert session_after.status == "completed"
            assert all(m.status == "completed" for m in session_after.milestones)

            completion = quest_runtime.check_completion(level_obj, player_id)
            assert completion is not None
            assert completion.get("exit_ready") is True

            debug_post = client.get(f"/world/story/{player_id}/debug/tasks")
            assert debug_post.status_code == 200
            debug_post_json = debug_post.json()
            assert debug_post_json.get("status") == "ok"
            assert debug_post_json.get("pending_conditions") == []

        finally:
            player_state = story_engine.players.get(player_id)
            level_obj = player_state.get("level") if player_state else None
            if level_obj:
                story_engine.exit_level_with_cleanup(player_id, level_obj)
            else:
                quest_runtime.exit_level(player_id)
            story_engine.players.pop(player_id, None)
            if level_path and level_path.exists():
                level_path.unlink()
            story_engine.register_generated_level(level_id)
