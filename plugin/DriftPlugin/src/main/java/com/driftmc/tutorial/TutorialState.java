package com.driftmc.tutorial;

import java.util.Locale;

/**
 * Represents the discrete learning gates in the tutorial flow. Ordering matters for unlock checks.
 */
public enum TutorialState {

    INACTIVE("未开始", "等待教程启动"),
    WELCOME("欢迎", "向心悦向导打招呼，例如输入 '你好' 或 '我准备好了'"),
    DIALOGUE("自由对话", "提问一些问题，比如 '这里是什么地方？'"),
    CREATE_STORY("创造剧情", "让AI生成剧情，例如 '写一个剧情'"),
    CONTINUE_STORY("推进剧情", "让故事继续，比如输入 '继续'"),
    JUMP_LEVEL("关卡跳转", "尝试跳转关卡，例如 '跳到第一关'"),
    NPC_INTERACT("NPC互动", "与心悦向导互动或对话"),
    VIEW_MAP("查看地图", "查看小地图，输入 '给我小地图'"),
    COMPLETE("完成", "教程已完成");

    private final String displayName;
    private final String requirementHint;

    TutorialState(String displayName, String requirementHint) {
        this.displayName = displayName;
        this.requirementHint = requirementHint;
    }

    public String getDisplayName() {
        return displayName;
    }

    public String getRequirementHint() {
        return requirementHint;
    }

    public boolean hasUnlocked(TutorialState required) {
        if (required == null) {
            return true;
        }
        return this.ordinal() >= required.ordinal();
    }

    public TutorialState next() {
        int ordinal = this.ordinal();
        TutorialState[] values = values();
        if (ordinal + 1 < values.length) {
            return values[ordinal + 1];
        }
        return COMPLETE;
    }

    public static TutorialState fromObject(Object value) {
        if (value == null) {
            return null;
        }
        if (value instanceof TutorialState state) {
            return state;
        }
        if (value instanceof Number number) {
            int idx = (int) Math.round(number.doubleValue());
            return fromIndex(idx);
        }
        if (value instanceof Iterable<?> iterable) {
            for (Object element : iterable) {
                TutorialState state = fromObject(element);
                if (state != null) {
                    return state;
                }
            }
            return null;
        }
        if (value instanceof java.util.Map<?, ?> map) {
            for (Object entryValue : map.values()) {
                TutorialState state = fromObject(entryValue);
                if (state != null) {
                    return state;
                }
            }
            return null;
        }
        return fromString(value.toString());
    }

    public static TutorialState fromString(String raw) {
        if (raw == null || raw.isBlank()) {
            return null;
        }
        String normalized = normalize(raw);
        return switch (normalized) {
            case "INACTIVE", "NONE" -> INACTIVE;
            case "WELCOME", "STEP_1", "STEP1" -> WELCOME;
            case "DIALOGUE", "STEP_2", "STEP2", "CHAT" -> DIALOGUE;
            case "CREATE_STORY", "CREATE", "STEP_3", "STEP3", "MAKE_STORY" -> CREATE_STORY;
            case "CONTINUE_STORY", "CONTINUE", "STEP_4", "STEP4" -> CONTINUE_STORY;
            case "JUMP_LEVEL", "LEVEL_JUMP", "STEP_5", "STEP5", "LEVEL" -> JUMP_LEVEL;
            case "NPC_INTERACT", "NPC", "STEP_6", "STEP6" -> NPC_INTERACT;
            case "VIEW_MAP", "MAP", "STEP_7", "STEP7", "MINIMAP" -> VIEW_MAP;
            case "COMPLETE", "FINISHED", "DONE", "STEP_8", "STEP8", "TUTORIAL_COMPLETE" -> COMPLETE;
            default -> null;
        };
    }

    private static String normalize(String raw) {
        String norm = raw.trim().toUpperCase(Locale.ROOT);
        norm = norm.replace('-', '_');
        norm = norm.replace(' ', '_');
        if (norm.startsWith("TUTORIAL_")) {
            norm = norm.substring("TUTORIAL_".length());
        }
        if (norm.startsWith("STEP_")) {
            return norm;
        }
        if (norm.matches("STEP\\d+")) {
            return norm;
        }
        return norm;
    }

    private static TutorialState fromIndex(int idx) {
        return switch (idx) {
            case 0 -> INACTIVE;
            case 1 -> WELCOME;
            case 2 -> DIALOGUE;
            case 3 -> CREATE_STORY;
            case 4 -> CONTINUE_STORY;
            case 5 -> JUMP_LEVEL;
            case 6 -> NPC_INTERACT;
            case 7 -> VIEW_MAP;
            case 8 -> COMPLETE;
            default -> null;
        };
    }
}
