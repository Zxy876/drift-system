# NPC Interaction System

Phase 13 introduces a dedicated dialogue HUD, improved interaction triggers, and extensible skin metadata that flows from the backend scene descriptors into the Minecraft plugin. This document captures the surface area so designers and developers can extend NPC content consistently.

## Feature Overview

- **Dialogue Panel** – Structured quest nodes of type `npc_dialogue` now render inside `DialoguePanel`. Players see a title banner, animated line-by-line delivery, and optional branching choices. Backend responses may supply either a `text` body or a `script` array (supporting `npc_say`/`narrate` operations).
- **Right-Click Activation** – Players can right-click any tracked NPC to open the latest conversation. Interactions are throttled to prevent accidental double-click spam and always emit a `right_click` rule event back to the backend.
- **Scene-Driven Skins** – Scene metadata (`scene.npc_skins`) is parsed during `_scene` application. The plugin loads skin descriptors, applies stylised nameplates (for example `桃子 · 赛道教练`), and spawns an armor-stand marker with an appropriate player head as a visual anchor.
- **Nameplate Styling** – NPC nameplates now use a consistent light-purple treatment with contextual subtitles. Additional overrides can be added inside `NPCManager.NAMEPLATE_OVERRIDES`.

## Authoring Guidance

1. **Dialogue Nodes**
   - Use `type: "npc_dialogue"` in rule metadata or story nodes to trigger the panel.
   - Supply either:
     - `text`: Multiline string (newline separated), or
     - `script`: Array containing objects such as `{ "op": "npc_say", "npc": "赛车手桃子", "text": "保持弯心！" }`.
   - Optional `choices` array supports `label` and `command` fields. When `command` is present it appears as a clickable option in-game.

2. **Scene Skins**
   - Define skins in level JSON under `scene.npc_skins`, e.g.:
     ```json
     "npc_skins": [
       { "id": "赛车手桃子", "skin": "skins/racer_taozi.png" }
     ]
     ```
   - The `id` should match the NPC name used inside `world_patch.mc.spawn.name` for automatic matching.
   - For unpublished textures, provide a placeholder PNG path; the plugin maps known identifiers to curated fallback player heads.

3. **Spawn Metadata**
   - Ensure `_scene` patches include NPC `spawn` entries with a readable `name`. `NPCManager` pre-registers these names while the world patch executes and attaches overlays as soon as entities spawn.

## Extension Points

- `com.driftmc.hud.dialogue.DialoguePanel` – Extend to support additional script operations or custom click handling.
- `com.driftmc.npc.NPCManager` – Update `NAMEPLATE_OVERRIDES` or `SKIN_FALLBACK_PLAYERS` to add new stylistic rules, or integrate with a full texture pipeline.
- `NearbyNPCListener` – Hook additional gestures (e.g., sneaking near an NPC) by emitting new rule events.

## Testing Checklist

- Load a level containing `npc_skins` and ensure nameplates update on spawn and after scene reloads.
- Right-click the NPC to verify the dialogue panel opens, progression lines render sequentially, and choices (if any) appear.
- Confirm repeated proximity moves do not spam chat, and right-click throttling prevents duplicate backend triggers.

Document last updated for **Phase 13 – NPC Dialogue UI & Skin Integration**.
