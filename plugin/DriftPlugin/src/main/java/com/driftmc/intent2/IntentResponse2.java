package com.driftmc.intent2;

import com.driftmc.story.LevelIds;
import com.google.gson.JsonObject;

public class IntentResponse2 {

    public final IntentType2 type;
    public final String levelId;
    public final JsonObject minimap;
    public final String rawText;
        public final String sceneTheme;
        public final String sceneHint;
    public final JsonObject worldPatch; // 新增：世界patch

    public IntentResponse2(IntentType2 type, String levelId, JsonObject minimap, String rawText,
                        String sceneTheme, String sceneHint, JsonObject worldPatch) {
        this.type = type;
        this.levelId = levelId;
        this.minimap = minimap;
        this.rawText = rawText;
                this.sceneTheme = sceneTheme;
                this.sceneHint = sceneHint;
        this.worldPatch = worldPatch;
    }

    public static IntentResponse2 fromJson(JsonObject root) {

        JsonObject intent = root.has("intent") && root.get("intent").isJsonObject()
                ? root.getAsJsonObject("intent")
                : root;

        String typeStr = intent.has("type") ? intent.get("type").getAsString() : null;
        IntentType2 type = IntentType2.fromString(typeStr);

        String levelId = intent.has("level_id") ? intent.get("level_id").getAsString() : null;
        levelId = LevelIds.canonicalizeLevelId(levelId);

        JsonObject minimap = intent.has("minimap") && intent.get("minimap").isJsonObject()
                ? intent.getAsJsonObject("minimap")
                : null;

        String raw = intent.has("raw_text") ? intent.get("raw_text").getAsString() : null;

        String sceneTheme = null;
        if (intent.has("scene_theme") && !intent.get("scene_theme").isJsonNull()) {
            sceneTheme = intent.get("scene_theme").getAsString();
        } else if (intent.has("theme") && !intent.get("theme").isJsonNull()) {
            sceneTheme = intent.get("theme").getAsString();
        }

        String sceneHint = null;
        if (intent.has("scene_hint") && !intent.get("scene_hint").isJsonNull()) {
            sceneHint = intent.get("scene_hint").getAsString();
        } else if (intent.has("hint") && !intent.get("hint").isJsonNull()) {
            sceneHint = intent.get("hint").getAsString();
        }

        JsonObject worldPatch = intent.has("world_patch") && intent.get("world_patch").isJsonObject()
                ? intent.getAsJsonObject("world_patch")
                : null;

        return new IntentResponse2(type, levelId, minimap, raw, sceneTheme, sceneHint, worldPatch);
    }
}