# Phase 4 · Quest Runtime & NPC Rulegraph Contract

This document captures the backend ↔ plugin protocol introduced in Phase 4. It explains how rule events flow from Minecraft to the FastAPI backend, how QuestRuntime and NPCBehaviorEngine respond, and what payloads the plugin must apply in-game.

---

## 1. Rule Event Ingestion

### 1.1 Plugin → Backend

Rule events are delivered through `POST /world/story/rule-event`.

```json
{
  "player_id": "Steve",
  "event_type": "near",
  "payload": {
    "target": "mia_npc",
    "quest_event": "near_mia_npc",
    "location": {
      "world": "world",
      "x": -11.3,
      "y": 75.0,
      "z": 209.7
    }
  }
}
```

**Recommended events**

| Event             | Trigger                                       | Notes |
|-------------------|-----------------------------------------------|-------|
| `near`            | Player walks within 3 blocks of an NPC        | Include `target` and `location`. |
| `chat`            | Player chat captured by `PlayerChatListener`  | Include `text` and normalized `quest_event`. |
| `interact_block`  | Block interaction (click / step)              | Include `action`, `block_type`, `location`. |
| `interact_entity` | Entity interaction (right-click)              | Include `entity_type`, optional `entity_name`. |

### 1.2 Backend Normalisation

`QuestRuntime._normalize_event` lowercases `event_type`, extracts a `target` from the payload, and passes the atomised event to TaskSession and NPCBehaviorEngine. The original payload is retained as `meta` for behavior rules.

---

## 2. QuestRuntime Responses

### 2.1 TaskSession lifecycle

Each task definition (from level JSON `tasks`) becomes a `TaskSession`:

- `id`: Unique identifier (defaults to `task_XX`).
- `type`: Event type that increments progress (`near`, `chat`, etc.).
- `target`: Optional match target (string or object).
- `count`: Required progress count.
- `milestones`: Optional checkpoints (`id`, `target`, `count`).
- `reward`: Optional rewards (`world_patch`, `npc_dialogue`).
- `dialogue`: Copy for completion nodes.

When issued, the runtime emits an issue node:

```json
{
  "nodes": [
    {
      "type": "task",
      "task_id": "greet_mia",
      "title": "任务：greet_mia",
      "text": "靠近米娅并打招呼。"
    }
  ]
}
```

### 2.2 Rule-event response schema

`QuestRuntime.handle_rule_trigger` aggregates task/NPC outcomes and surfaces them via `/world/story/rule-event`:

```json
{
  "status": "ok",
  "result": {
    "world_patch": { ... },
    "nodes": [ ... ],
    "completed_tasks": [ "greet_mia" ],
    "milestones": [ "greet_mia_step1" ],
    "commands": [ "say §aMia 完成第一阶段" ],
    "exit_ready": true,
    "summary": {
      "type": "task_summary",
      "title": "湖畔初遇 · 任务总结",
      "text": "你已经完成所有任务，继续冒险吧！"
    }
  }
}
```

**Field meanings**

| Field              | Type           | Description |
|--------------------|----------------|-------------|
| `world_patch`      | `Map[str,Any]` | Patch to apply through `SceneAwareWorldPatchExecutor` (delegates to `WorldPatchExecutor`). |
| `nodes`            | `List[dict]`   | Narration cards (`type` identifies styling). |
| `completed_tasks`  | `List[str]`    | Task IDs completed by this event. |
| `milestones`       | `List[str]`    | Milestone IDs newly completed. |
| `commands`         | `List[str]`    | Console commands to run (`{player}` placeholder supported). |
| `exit_ready`       | `bool`         | All tasks complete; player can exit or advance. |
| `summary`          | `dict`         | Optional summary node emitted once per level. |

`QuestRuntime` merges NPCBehaviorEngine results into the same structure, so plugin consumers do not need to differentiate quest vs. NPC sources.

---

## 3. NPC Behavior Bindings

### 3.1 Level metadata

`rule_listeners` inside a level JSON feed `QuestRuntime.register_rule_listener` and `NPCBehaviorEngine.register_rule_binding`.

Example:

```json
{
  "type": "near",
  "quest_event": "near_mia_npc",
  "metadata": {
    "dialogue": {
      "title": "米娅",
      "text": "啊，是你！准备好冒险了吗？"
    },
    "world_patch": {
      "tell": "米娅向你挥手。"
    },
    "commands": [
      "title {player} subtitle 米娅的心声"
    ]
  }
}
```

NPCBehaviorEngine builds a map of bindings keyed by:

- Listener `type`
- `quest_event`
- Entries in `metadata.rule_ref` / `metadata.id`
- Targets listed in `listener.targets`

Activated rule refs (via `QuestRuntime.activate_rule_refs`) unlock additional bindings for later events.

### 3.2 Engine outputs

When a binding matches an event, NPCBehaviorEngine emits:

- Dialogue nodes (`metadata.dialogue` or list/string).
- Patched world updates (`metadata.world_patch`).
- Command list (`metadata.commands`).
- Behavior mutations (`metadata.update_behaviors`) appended to in-memory NPC state.

These payloads are merged into the `/world/story/rule-event` response.

### 3.3 Visual identity hooks

- Level authors can set `scene.npc_skins[]` in JSON to inform the plugin which cosmetic skin to load for a named NPC (identifier should match the spawn `name`).
- `world_patch.mc._scene.featured_npc` highlights which character anchors the scene; Phase 7 NPC polish uses this so the plugin can pin portraits and cleanup logic to the active guide.
- Behavior updates pushed through `metadata.update_behaviors` may introduce new entries (e.g., `particle`, `patrol`), so downstream consumers should tolerate additional keys without schema drift.

---

## 4. Plugin Responsibilities

`RuleEventBridge` now:

1. Sends rule events with cooldown protection.
2. Parses backend responses.
3. Applies `world_patch` via `SceneAwareWorldPatchExecutor` (scene metadata is honoured automatically).
4. Streams nodes to chat with contextual prefixes (`【任务】`, `【阶段】`, `【NPC】`, etc.).
5. Announces completed tasks / milestones once per player session.
6. Dispatches backend `commands` through the console after substituting `{player}`.
7. Notifies players when `exit_ready` becomes `true`.

**Persistence guards**

- `PlayerRuleState` caches completed tasks/milestones per player to avoid duplicate announcements during repeated backend responses.
- Response handling is scheduled on the main thread to remain Bukkit-safe.

---

## 5. Testing Checklist

- **Quest loop**: Trigger `near` → verify task issuance node and progress updates.
- **Milestones**: Provide repeated events to reach milestone counts; ensure distinct milestone toast appears once.
- **Rewards**: Confirm `reward.world_patch` (e.g., item grants) applies when task completes.
- **Commands**: Backend-delivered command (e.g., `title`) should execute with `{player}` replaced by the sender.
- **Exit readiness**: After all tasks complete, player receives summary node and golden exit prompt.
- **Offline handling**: If player disconnects before response, plugin logs a skip and no dispatch occurs.

---

## 6. Future Work

- Automated coverage for duplicate event suppression and offline players.
- Designer tooling to preview level JSON → response outputs.
- Optional scoreboard or bossbar hooks for task progress percentages.

---

For schema changes, update this document alongside backend/runtime modifications to keep the contract stable.
