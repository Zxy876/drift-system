package com.driftmc.intent;

public enum IntentType {
    STORY,
    WORLD,
    NPC,
    DSL,
    CHAT,
    UNKNOWN;

    public static IntentType fromString(String s) {
        if (s == null) return UNKNOWN;
        return switch (s.toLowerCase()) {
            case "story" -> STORY;
            case "world" -> WORLD;
            case "npc"   -> NPC;
            case "dsl"   -> DSL;
            case "chat"  -> CHAT;
            default      -> UNKNOWN;
        };
    }
}
