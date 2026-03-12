# Memory System Overview

The flagship arc now shares continuity through lightweight memory flags. These flags let chapters react to earlier choices, adjust NPC tone, and feed into StoryGraph recommendations.

## Naming Convention
- Memory identifiers follow `domain.topic.event` (e.g., `xinyue.face_once`).
- Prefix with the narrative arc (`xinyue`), then the focus (`face`, `escape`, `admitted`), and finally the context (`once`, `pain`, `summit`).
- Prefer verbs that describe what the player *did*, not how the system responded.

## Schema Extensions
`backend/app/core/story/level_schema.py` introduces three new helpers:

| Field | Description |
| --- | --- |
| `memory_required` | Optional list or condition; beat/task only fires when the player already owns the listed flags. |
| `memory_set` / `memory_clear` | Flags to add/remove when a beat activates or a task/milestone completes. |
| `milestone_memory` | Task-level mapping from milestone id to memory mutation. |

All three are parsed into `MemoryCondition` / `MemoryMutation` dataclasses. Beats and tasks expose these as attributes so StoryEngine can decide when to trigger and how to update state.

### Beat Example
```jsonc
{
  "id": "flagship_08_memory_face",
  "trigger": ["rule_event:comfort_path", "rule_event:fight_path"],
  "memory_set": ["xinyue.face_once"],
  "memory_clear": ["xinyue.escape_once"],
  "world_patch": {
    "mc": {
      "tell": "§a 雨声渐弱，你踩在泥水里的脚步慢慢稳了下来。"
    }
  }
}
```

StoryEngine applies the mutations automatically whenever quests report completed tasks or milestones.

## Runtime Behaviour
- Memory sets are per-player and persist across levels in `StoryEngine.players[player_id]["memory_flags"]`.
- Beats with unmet `memory_required` conditions are deferred until flags become available; once the requirement is satisfied they auto-trigger.
- StoryGraph stores the latest snapshot (`StoryGraph.memory_snapshots`) and blends flags into recommendations via `memory_affinity`/`memory_recovery` hints in level JSON.
- `GET /world/story/{player}/memory` exposes the active flag list for quick validation in Minecraft.

## Flagship Arc Flags
| Flag | Meaning |
| --- | --- |
| `xinyue.admitted_pain` | Player voiced their pain during the flagship tutorial. |
| `xinyue.masked_pain` | Player chose to stay stoic during the tutorial intro. |
| `xinyue.face_once` | Player faced the maze heart demon / bridge shadow directly. |
| `xinyue.escape_once` | Player escaped the maze confrontation or ran from their shadow. |
| `xinyue.reached_summit` | Player completed the summit beat in flagship_03. |

Add new flags sparingly—prefer evolving existing ones to keep recommendation signals meaningful.
