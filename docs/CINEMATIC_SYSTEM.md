# Cinematic System Overview

The Phase 14 rollout introduces a dedicated cinematic pipeline that allows scene metadata coming from the backend to orchestrate timed camera moves, fades, particle bursts, and soundtracks inside the Minecraft plugin. This document captures the moving parts and how to author new sequences.

## Runtime Components

- **`CinematicController` (plugin)** – Parses a sequence definition, applies optional slow-motion, and executes each action in order on the Bukkit main thread. Active sequences are tracked per-player so a new trigger replaces the existing playback gracefully.
- **`CinematicContext` (plugin)** – Lightweight handle shared by actions. It keeps the player UUID, plugin reference, world patch executor, and manages temporary slow-motion adjustments to walk/fly speed.
- **`CinematicAction` (plugin)** – Simple callback interface (`play(context, on_complete)`) implemented by the built-in actions (fade, wait, teleport, camera, sound, particle, world patch). Each action is responsible for invoking `on_complete` when its effect has finished so the controller can advance the sequence.
- **`SceneLoader` (plugin)** – When `_scene` metadata arrives, it now forwards any nested `cinematic` or `_cinematic` definitions to the controller. The loader still manages cleanup and NPC hooks, but additionally starts cinematics alongside those updates.
- **`story_engine.CINEMATIC_LIBRARY` (backend)** – Declarative lookup table mapping `scene_patch` identifiers to world patch templates plus cinematic sequences. Beat metadata referencing a known scene patch now gains the extra cinematic payload automatically.

## Sequence Format

Cinematic sequences are JSON-compatible dictionaries with the following shape:

```jsonc
{
  "slow_motion": 0.75,         // optional player speed multiplier (0 < value ≤ 1)
  "sequence": [
    {"action": "fade_out", "duration": 1.0},
    {"action": "wait", "duration": 0.25},
    {"action": "camera", "offset": {"yaw": 25.0, "pitch": -10.0}, "hold": 0.6},
    {"action": "sound", "sound": "ENTITY_FIREWORK_ROCKET_LAUNCH", "volume": 1.3, "pitch": 1.0},
    {"action": "particle", "particle": "FIREWORKS_SPARK", "count": 140, "radius": 2.4, "offset": {"y": 1.2}},
    {"action": "fade_in", "duration": 1.0}
  ]
}
```

Supported `action` values:

- `fade_out` / `fade_in` – Applies or lifts a blindness overlay for cinematic fades.
- `wait` – Delays the next step by `duration` seconds.
- `camera` – Teleports the player a tiny amount or adjusts yaw/pitch. Supports `offset`, `position`, and `look_at` fields plus `hold` to linger.
- `sound` – Plays a Bukkit `Sound` enum at the player, respecting `volume`, `pitch`, and optional `offset`.
- `particle` – Emits Bukkit `Particle` effects around the player, with `count`, `radius`, `offset`, and `speed` controls.
- `teleport` – Uses the existing `WorldPatchExecutor` safe teleport logic; pass a `teleport` or `target` map mirroring normal world patch payloads.
- `world` – Applies a lightweight world patch (weather, titles, etc.) mid-sequence.

Every action accepts `hold` (seconds) to keep the camera steady before proceeding. The controller schedules each block on the main thread while preserving existing world patch cleanup behaviour.

## Backend Authoring

Beat definitions already carry `scene_patch` references. The backend now consults `CINEMATIC_LIBRARY` in `story_engine.py` and merges the preset if the key is known. To introduce a new preset:

1. Update `CINEMATIC_LIBRARY` with the desired `mc` patch and `_cinematic` sequence.
2. Reference the preset from the beat definition (`scene_patch: "scene_custom"`).
3. Optionally add additional per-level overrides via `level.scene_patches` if individual levels require tweaks.

Because the preset is deep-copied at runtime, authoring is safe from accidental cross-player mutation.

## Testing Workflow

- `/cinematic test` – Invokes a sample sequence showing fades, camera tilt, particles, and soundtrack for rapid validation.
- Existing `/drift` commands continue to function; cinematic playback is transparent to other systems.
- To verify beat-driven cinematics, trigger the relevant level beat (e.g., `level_1_finish` or `level_3_intro`). The plugin will log the scene application and execute the preset.

## Safety Notes

- All action scheduling happens on the Bukkit main thread to avoid unsafe world interactions.
- Slow-motion temporarily scales the player walk/fly speeds and is automatically restored, even if the sequence is interrupted.
- If a new cinematic starts while another is still running, the controller cancels the previous playback and restores player speeds before starting the next sequence.

With these components in place, backend authors can express rich story moments declaratively, and the plugin faithfully stages them without bespoke Java code for each beat.
