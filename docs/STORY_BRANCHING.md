# Story Choices & Branching UI

## Overview

Phase 15 introduces an interactive branching flow that lets players influence the narrative directly inside Minecraft. Backend beats can now declare structured `choices`, and the plugin renders them through a lightweight choice panel that captures the player decision and forwards it to the rule-event pipeline.

## Authoring Choices

Inside a beat definition (for example in `backend/data/heart_levels/level_03.json`) you can attach a `choices` array:

```json
{
  "id": "summit_greeting",
  "trigger": "on_enter",
  "rule_refs": ["choice_follow", "choice_explore"],
  "choices": [
    {
      "id": "follow_taozi",
      "text": "跟随桃子训练漂移",
      "rule_event": "choice_follow",
      "next_level": "level_02",
      "tags": ["training", "mentor"]
    },
    {
      "id": "explore_trail",
      "text": "自己探索赛道",
      "rule_event": "choice_explore",
      "tags": ["explore"]
    }
  ]
}
```

- `rule_event` is required and should match the `rule_refs` that unlock follow-up beats.
- `next_level` and `tags` are optional metadata used by `StoryGraph` to bias future recommendations.
- `choice_prompt` can be added to the beat to override the default prompt text.

## Runtime Flow

1. **StoryEngine** detects choices when a beat activates and emits a `story_choice` node containing the choice payload.
2. **ChoicePanel** (plugin) renders the options in chat with clickable shortcuts and tracks the pending session for the player.
3. When a player types the number/ID, ChoicePanel intercepts the chat message, echoes the selection, and emits the designated `rule_event` via `RuleEventBridge`.
4. **StoryEngine** records the choice, appends it to the player trajectory, and triggers any beats that listen for the associated `rule_refs`.
5. **StoryGraph** now factors stored branching metadata into recommendations, boosting levels linked through `next_level` and tags touched by recent selections.

## Player UX Notes

- Choices show up with numbered options (e.g., `[1] 跟随桃子训练漂移`). Clicking the line suggests the number in chat, so players can press Enter to confirm.
- The plugin clears pending sessions when new dialogue arrives, preventing stale selections.
- A confirmation line (`你选择了: ...`) is emitted before the rule event is sent upstream.

## Extending Branching Logic

- Additional metadata (`tags`) can be used to bias other systems (HUD, analytics).
- Future phases can reference `choice_history` stored in `StoryEngine` to unlock dynamic scenes or achievements.
- To add more complex UI (e.g., timed choices), extend `ChoicePanel` with timers while keeping the rule-event contract intact.
