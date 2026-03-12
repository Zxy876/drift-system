# Level Format Reference

## Level Schema v2.0 (Active)

> Phase 6 promotes the former v1.5 draft into the live baseline. The schema remains backward compatible with existing v1 JSON files; unspecified sections continue to fall back to defaults handled by the runtime and loader.

### Overview

Level Schema v2.0 extends the legacy narrative format into five coordinated layers:

1. **Narrative Beats** – ordered story milestones that can trigger scene patches or rule hooks.
2. **Scene** – deterministic world setup, including teleport, environment, prefabs, and NPC presentation.
3. **Rules** – listener graph for in-world events that should notify the backend quest runtime.
4. **Tasks** – quest objectives, milestones, and reward descriptors consumed by `QuestRuntime`.
5. **Exit** – phrases and return spawn metadata to let players leave gracefully.

### Example

```json
{
  "id": "level_20251208_153045",
  "narrative": {
    "beats": [
      { "id": "beat_intro", "trigger": "on_enter", "scene_patch": "scene_intro", "rule_refs": ["rule_welcome"] },
      { "id": "beat_conflict", "trigger": "milestone:collect_3", "scene_patch": "scene_conflict" }
    ]
  },
  "scene": {
    "world": "KunmingLakeStory",
    "teleport": { "x": 120.5, "y": 72, "z": -30.2, "yaw": 90, "pitch": 0 },
    "environment": { "weather": "RAIN", "time": "NIGHT", "lighting": "DIM" },
    "structures": ["structures/kunming_gate.nbt"],
    "npc_skins": [{ "id": "npc_host", "skin": "skins/host.png" }]
  },
  "rules": {
    "listeners": [
      { "type": "BLOCK_BREAK", "targets": ["custom:memory_crystal"], "quest_event": "crystal_damaged" }
    ]
  },
  "tasks": [
    {
      "id": "collect_memories",
      "type": "collect",
      "conditions": [{ "item": "custom:memory_shard", "count": 3 }],
      "milestones": ["shard_1", "shard_2", "shard_3"],
      "rewards": [{ "type": "xp", "amount": 150 }]
    }
  ],
  "exit": { "phrase_aliases": ["结束剧情", "离开关卡"], "return_spawn": "KunmingLakeHub" }
}
```

### Field Reference (Draft)

- `narrative.beats[]`
  - `id` – unique beat identifier.
  - `trigger` – string describing when the beat unlocks (`on_enter`, `milestone:*`, etc.).
  - `scene_patch` – identifier for a scene patch asset.
  - `rule_refs` – optional list of rule listener IDs to activate on beat.

- `scene`
  - `world` – optional Minecraft world name.
  - `teleport` – `{ x, y, z, yaw, pitch }` landing position.
  - `environment` – `{ weather, time, lighting }` hints for world patching.
  - `structures` – array of prefab references.
  - `npc_skins` – cosmetic mapping for named NPCs.

- `rules`
  - `listeners[]` – entries like `{ type, targets, quest_event }` describing hook points.

- `tasks[]`
  - `id` – stable quest/tasks identifier.
  - `type` – classification string (collect, kill, etc.).
  - `conditions[]` – list of `{ item|entity|location, count }` descriptors.
  - `milestones[]` – optional milestone IDs the engine can unlock.
  - `rewards[]` – entries such as `{ type: "xp", amount: 150 }`.

- `exit`
  - `phrase_aliases[]` – recognized escape phrases for natural-language exit.
  - `return_spawn` – symbolic identifier or coordinates for the return hub.

### `_scene` Metadata

World patches now expose deterministic scene metadata via the `_scene` key under `world_patch.mc`. Level exporters should stamp:

```json
"_scene": {
  "level_id": "level_1",
  "scene_world": "KunmingLakeStory",
  "teleport": { "x": 0.5, "y": 70.0, "z": 0.5, "yaw": 0.0, "pitch": 0.0 }
}
```

The Minecraft plugin consumes this payload to scope cleanup radii and teleport hints.

> **Backwards compatibility:** Existing v1 JSON files load unchanged. Absent sections resolve to empty lists or `None`, allowing the runtime to continue using default world patches until the richer hooks are fully exercised.
