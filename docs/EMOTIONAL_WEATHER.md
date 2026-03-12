# Emotional Weather System

Phase 19 introduces a narrative-aware "emotional weather" pipeline that lets the DriftSystem backend and Minecraft plugin respond to player memory flags in real time. This document explains the data model, runtime flow, and debugging hooks for the new system.

## 1. Concept Overview
- **Memory driven:** The StoryEngine reads existing flagship memory flags such as `xinyue.face_once` and `xinyue.escape_once` to infer the current emotional profile after every beat.
- **Hot reload:** Emotional patches are merged into the active `world_patch` without restarting the backend or server. The engine only applies a fresh patch when the player's memory digest changes.
- **Multi-channel feedback:** Weather, lighting, diegetic music, and hub NPC tone all shift together so the player feels the world reacting to their choices.

## 2. Flagship Level Schema
Each flagship JSON can describe emotional reactivity with the optional `emotional_world_patch` block.

```jsonc
"emotional_world_patch": {
  "default": {
    "label": "雨夜悬念",
    "tone": "brooding",
    "patch": {
      "mc": {
        "lighting_shift": "night_to_neon_glow",
        "music": { "record": "ward", "volume": 0.7 },
        "npc_emotion": {
          "tone": "brooding",
          "targets": ["grandma_memory"],
          "lines": ["雨声像问句一样敲着迷宫的墙。"]
        }
      }
    }
  },
  "profiles": [
    {
      "id": "face_maze",
      "requires": ["xinyue.face_once"],
      "priority": 10,
      "label": "雨停一隙",
      "tone": "encouraging",
      "patch": {
        "mc": {
          "weather_transition": { "to": "CLEAR" },
          "lighting_shift": "lantern_warm",
          "music": { "record": "otherside", "volume": 0.75 },
          "npc_emotion": {
            "tone": "encouraging",
            "targets": ["grandma_memory"],
            "lines": ["奶奶的影子笑了：你敢转身，雨势就替你散开。"],
            "actionbar": "雨线稀疏 · 面对"
          }
        }
      }
    }
  ]
}
```

### Keys
- `default.patch`: Baseline cues applied when no profile matches.
- `profiles[]`: Ordered by `priority` (desc). Each profile activates when its `requires` / `requires_all` flags are satisfied or any `requires_any` flag matches.
- `mc.weather_transition`: Hands a transition hint to the plugin; the executor fades to the target weather and prints a short message.
- `mc.lighting_shift`: Symbolic lighting keyword. The plugin sends a micro-story cue and nudges the time of day when possible.
- `mc.music`: `{ "record": "otherside", "volume": 0.8, "pitch": 1.0 }` plays the matching Minecraft music-disc sound.
- `mc.npc_emotion`: Communicates hub tone adjustments.
  - `targets`: NPC display names for tone tagging (defaults to 心悦向导 + 登山者 when omitted).
  - `lines`: Quick chat lines delivered to the active player.
  - `actionbar`: Optional banner pushed to the player for moment-to-moment feedback.

## 3. StoryEngine Runtime
1. **Level load** – `story_loader` now keeps the raw JSON payload so `ensure_level_extensions(..., payload)` can parse emotional patches alongside beats/tasks.
2. **Beat progress** – After `_process_beat_progress`, `StoryEngine.advance` calls `_compose_emotional_patch`. The helper:
   - Reads the current memory set.
   - Selects the highest priority profile whose requirements are satisfied.
   - Compiles a merged patch (default → profile) and records a summary (`profile_id`, `label`, `tone`, `patch_keys`).
3. **Hot application** – When the profile or memory digest changes, the merged patch is appended to the outgoing `world_patch`. A cached `emotional_profile` snapshot tracks when the last patch was sent.
4. **Debug API** – `GET /world/story/{player_id}/emotional-weather` exposes the cached summary (profile id, tone, memory flags, last applied patch preview).

## 4. Minecraft Integration Highlights
- `WorldPatchExecutor`
  - Understands `weather_transition`, `lighting_shift`, and `music` keys.
  - Resolves record names to `SoundCategory.RECORDS` playback and prints lightweight story cues.
- `SceneAwareWorldPatchExecutor`
  - Forwards any `mc.npc_emotion` payload to the `NPCManager` before executing the base patch.
- `NPCManager`
  - Maintains an `emotionProfiles` map keyed by normalized NPC display names.
  - Updates nameplates to append the active profile label (`桃子 · 赛道教练 · 面对勇气`).
  - Sends scripted chat/actionbar lines from the payload to the triggering player.

## 5. Testing Checklist
1. **Backend unit smoke**
   - Hit `/world/story/{player}/emotional-weather` before and after triggering `xinyue.face_once` to confirm profile changes.
2. **In-game validation**
   - Enter `flagship_03` and trigger both facing and escape branches. Observe weather/lighting transitions and NPC tone changes.
   - Verify hub NPC nameplates update and chat lines appear exactly once per change.
3. **Regression**
   - Ensure `/world/story/generate-level` flow still registers levels (emotional pipeline is opt-in and backward compatible).
4. **Logging**
   - Server console should show the record sound mapping (unknown records log as `fine` level for debugging).

## 6. Extensibility Notes
- All additions are optional; legacy flagship JSONs without `emotional_world_patch` behave exactly as before.
- Future chapters can add more nuanced profiles (e.g., `requires_any` with multiple memory flags, incremental priorities).
- Additional cues (particles, minimap overlays, quest log prompts) can piggyback inside the same `mc` payloads.

Happy weather weaving! 🌦️
