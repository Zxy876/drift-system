# Task Auto-Healing Overview

Phase 25 introduces _orphan rule_event_ detection and confidence-scored heal hints. The system avoids destructive patching and instead records actionable diagnostics that operators (or future automation) can review.

## Detection Flow

1. **QuestRuntime.handle_rule_trigger** normalizes each incoming `rule_event`.
2. If no active task matches, and the player is inside a level with an active scene, the runtime records an orphan event.
3. The orphan payload captures:
   - `player_id`, `level_id`, and timestamp
   - normalized event payload and original raw payload
   - recent task activity and matched status
4. Each orphan is appended to `state['orphan_events']` (bounded list) and surfaced through `/world/story/{player}/debug/tasks`.

## Auto-Heal Suggestions

- QuestRuntime delegates unmatched events to **StoryEngine** via `_handle_orphan_rule_event`.
- StoryEngine inspects:
  - Live TaskSession data (rule refs, milestones, targets)
  - Original level task definitions (conditions, tags, titles)
- Candidate rule events are scored with `SequenceMatcher`, producing:
  - `candidate_event`
  - `task_id` / `task_title`
  - `reason` and `source` (runtime vs level metadata)
  - `confidence` in `[0,1]`
- Suggestions are stored in-memory under `player_state['autofix_hints']` and fed back to QuestRuntime (`auto_heal_suggestions`).
- No task rewrites happen automatically; operators can apply fixes manually or feed suggestions into future automation.

## Accessing Diagnostics

- `/world/story/{player}/debug/tasks` now includes:
  - `orphan_events`: recent unmatched rule events
  - `auto_heal_suggestions`: up to 10 recent suggestions with confidence scores
- The `/taskdebug` command surfaces `last_rule_event.auto_heal_suggestion` to in-game operators (permission `drift.taskdebug`).

## Operational Notes

- Auto-heal only runs when a level provides scene metadata, reducing noise from lobby/world chatter.
- Suggestions require a confidence of ≥0.55 to appear.
- Logging is emitted at `WARNING` for orphan detection and `INFO` for heal suggestions. No persistent file updates occur.
- Rotate the debug token (`DRIFT_TASK_DEBUG_TOKEN` / `config.yml:debug.task_token`) regularly to guard diagnostic access.
