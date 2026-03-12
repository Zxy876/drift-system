"""Phase 25 regression tests for task auto-heal diagnostics."""

from __future__ import annotations

from app.core.quest.runtime import quest_runtime
from app.main import story_engine


def test_orphan_rule_event_records_auto_heal_suggestion():
    player_id = "phase25_autofix_tester"
    level_id = "flagship_03"

    story_engine.load_level_for_player(player_id, level_id)
    level = story_engine.players[player_id]["level"]
    quest_runtime.issue_tasks_on_beat(level, player_id, {"id": level.beats[0].id})

    # Emit an event that should nearly match an existing milestone but contains a typo.
    quest_runtime.handle_rule_trigger(
        player_id,
        {
            "event_type": "quest_event",
            "payload": {"quest_event": "fear_pulse_typo"},
        },
    )

    state = quest_runtime._players[player_id]
    assert state.get("orphan_events"), "orphan event should be recorded"
    assert state.get("auto_heal_suggestions"), "auto-heal suggestions should be populated"

    suggestion = state["auto_heal_suggestions"][0]["suggestion"]
    assert suggestion["candidate_event"] == "fear_pulse"
    assert suggestion["confidence"] >= 0.55

    # StoryEngine should keep an in-memory hint for the player as well.
    player_state = story_engine.players[player_id]
    autofix_hints = player_state.get("autofix_hints") or {}
    assert "fear_pulse_typo" in autofix_hints

    quest_runtime.exit_level(player_id)
    story_engine.players.pop(player_id, None)