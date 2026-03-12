# Flagship Arc Story Structure

## Narrative Spine
- **Tutorial – Lakeside Awakening (`flagship_tutorial`)**: introduces XinYue, primes memory flags, and frames the flagship arc as an act of shared resilience. The lake sunrise palette bridges players from neutral hub mood into hopeful readiness.
- **Chapter 03 – Storm Summit (`flagship_03`)**: escalates tension on the mountain. Split greeting beats adapt to the player’s earlier confession choice, reinforcing emotional continuity. Summit success prepares the hand-off toward introspective mid-game trials.
- **Chapter 08 – Rain Maze Reckoning (`flagship_08`)**: the arc’s midpoint. Rain-soaked memories and branching comfort/avoidance paths retune memory flags that downstream chapters consume. Lighting and weather transitions gradually lift toward calm for players who face their fears.
- **Chapter 12 – Neon Crossroads (`flagship_12`)**: late-game synthesis. Pharmacy and bridge branches echo earlier decision patterns, looping avoidance back to Chapter 03 or steering resolved players toward the finale placeholder.
- **Finale Placeholder**: reserved for Phase 18 integrations. StoryGraph continuity biases already aim players toward this slot when flagship themes remain dominant.

## Continuity Signals
- `storyline_theme="flagship_resilience"` threads through each JSON level, surfacing in StoryGraph scoring to reward sustained engagement with the flagship arc.
- Each level’s `continuity` block documents previous/next waypoints and emotional vectors, making downstream tooling aware of arc positioning (`arc_step`, `arc_position`).
- Beats and choices ship `branch_hint` and `continuity_tags` so runtime analytics can bucket player intent without hardcoding level IDs.
- `next_major_level` highlights canonical flagship progression (Tutorial → 03 → 08 → 12 → Finale) without removing optional detours.

## Runtime Expectations
- Scene hand-offs: world patches now transmit `lighting_shift` and `weather_transition` metadata so the plugin can fade cues between chapters.
- StoryGraph introduces a continuity bonus when recommending levels that share the latest flagship theme, gently nudging players forward unless strong branch preferences override.
- Existing exit aliases and hub teleports remain valid; the arc metadata purely enriches decision support layers.
