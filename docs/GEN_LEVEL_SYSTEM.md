# Generative Level System

The Phase 18 generator exposes `/world/story/generate-level`, allowing players to craft fully fledged flagship-style chapters from natural language prompts. This document captures the contract and runtime flow for the generator so other subsystems (analytics, plugin transport, StoryGraph weighting) stay aligned.

## 1. API Contract
- **Endpoint**: `POST /world/story/generate-level`
- **Request body** (`application/json`)
  - `description` *(string, required)* — free-form natural language prompt (≥12 characters).
  - `title` *(string, optional)* — overrides the auto-derived title.
  - `tags` *(array[string], optional)* — additional semantic tags to stitch into StoryGraph interest tracking.
- **Response** (`application/json`)
  - `status`: "ok" on success.
  - `level_id`: canonical ID (e.g. `flagship_user_1733842245123`).
  - `path`: absolute path to the saved JSON file under `backend/data/flagship_levels/generated/`.
  - `tags`: resolved tag list.
  - `storyline_theme`: `storyline_theme` assigned to the generated level.

Generated files follow the naming scheme `flagship_user_<epoch_ms>.json`. The handler de-dupes file names when multiple submissions occur within the same millisecond by appending a numeric suffix.

## 2. JSON Structure
The helper `enhance_generated_level.generate_flagship_level` produces schema-compliant payloads keyed off the flagship format:

```json
{
  "id": "flagship_user_1733842245123",
  "title": "玩家创作 · 月下桥的记忆…",
  "tags": ["user", "generated", "flagship", "moon", "bridge"],
  "meta": {
    "chapter": null,
    "word_count": 78,
    "source": "player",
    "created_at": "2025-12-10T07:10:12.345Z"
  },
  "storyline_theme": "user_created_moon",
  "continuity": {
    "previous": "flagship_12",
    "next": null,
    "emotional_vector": "player_authored",
    "arc_step": 0,
    "origin": "user_generated"
  },
  "narrative": {
    "text": ["生成时间…", "<player description>"] ,
    "beats": [
      {"id": "user_intro", "trigger": "on_enter", "choices": [...]},
      {"id": "user_question", "trigger": "rule_event:user_choice_embrace"},
      {"id": "user_linger", "trigger": "rule_event:user_choice_observe"},
      {"id": "user_outro", "trigger": "story:continue"}
    ]
  },
  "scene": {
    "world": "KunmingLakeStory",
    "teleport": {"x": 4.5, "y": 70, "z": -3.5, "yaw": 180, "pitch": 0},
    "environment": {"weather": "CLEAR", "time": "SUNSET"},
    "structures": ["structures/generated/player_canvas.nbt"],
    "npc_skins": [{"id": "玩家影像", "skin": "skins/player_memory.png"}]
  },
  "world_patch": {
    "mc": {
      "_scene": {"level_id": "flagship_user_…", "title": "…"},
      "tell": "<prompt summary>",
      "music": {"record": "otherside"},
      "particle": {"type": "portal", "count": 30}
    },
    "variables": {"theme": "user_created_moon", "arc_position": "user_created"}
  },
  "tasks": [{"id": "user_generated_walk", "type": "story", "milestones": ["embrace", "observe"]}],
  "exit": {
    "phrase_aliases": ["离开玩家创作", "退出玩家章节", "return hub"],
    "return_spawn": "KunmingLakeHub",
    "teleport": {"x": 128.5, "y": 72, "z": -16.5, "yaw": 180, "pitch": 0}
  }
}
```

All beats retain minimal `rule_refs` and optional `memory_set` data so the StoryEngine runtime can reuse existing quest and memory APIs.

## 3. Runtime Flow
1. API validates payload, synthesizes JSON, and writes it under `backend/data/flagship_levels/generated/`.
2. `StoryEngine.register_generated_level` refreshes `StoryGraph` and `MiniMap` so new chapters are immediately available without a restart.
3. `StoryGraph.reload_levels` categorises generated assets with `level_sources[level_id] = "generated"`.
4. Recommendation updates:
   - Tags observed on generated exits increment a "user-generated interest" signal.
   - Subsequent recommendations add a bonus for levels (generated or flagship) sharing those tags.
   - The most recent generated level gains an extra bump to encourage players to continue their authored arc.
5. MiniMap refresh re-lays out the spiral including generated nodes (they appear at the tail of the orbit).

## 4. Safety & Guardrails
- Inputs shorter than 12 characters are rejected with `400` to avoid meaningless outputs.
- Level IDs are slugified and timestamp based to prevent collisions with curated flagship chapters.
- Generator never overrides files outside `generated/` and sanitises additional tags down to simple lower-case tokens.
- StoryGraph mappings ensure generated levels do not insert themselves into the flagship linear chain; they remain isolated nodes unless further edges are defined manually.

## 5. Future Work Hooks
- `continuity.origin = "user_generated"` gives Phase 19 the flag required for emotional world reactivity.
- The generator helper can be extended with richer beat libraries (cinematics, memory mutations) without breaking the API contract.
- Analytics pipeline can consume the saved JSON alongside the returned metadata to build player creativity dashboards.
