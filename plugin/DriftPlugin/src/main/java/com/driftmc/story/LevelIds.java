package com.driftmc.story;

import java.util.Collections;
import java.util.HashMap;
import java.util.Locale;
import java.util.Map;
import java.util.Objects;

/**
 * Central place to normalize level ids before calling the backend.
 */
public final class LevelIds {

    public static final String FLAGSHIP_TUTORIAL = "flagship_tutorial";
    public static final String DEFAULT_LEVEL = FLAGSHIP_TUTORIAL;

    private static final Map<String, String> CANONICAL;

    static {
        Map<String, String> map = new HashMap<>();
        register(map, FLAGSHIP_TUTORIAL,
                "flagship_tutorial",
                "flagship-tutorial",
                "flagshiptutorial",
                "level_01",
                "level-01",
                "level01",
                "level1",
                "level_1",
                "tutorial",
                "tutorial_level",
                "level_tutorial");
        CANONICAL = Collections.unmodifiableMap(map);
    }

    private LevelIds() {
    }

    private static void register(Map<String, String> map, String canonical, String... aliases) {
        map.put(canonical.toLowerCase(Locale.ROOT), canonical);
        for (String alias : aliases) {
            if (alias == null || alias.isEmpty()) {
                continue;
            }
            map.put(alias.toLowerCase(Locale.ROOT), canonical);
        }
    }

    public static String canonicalizeLevelId(String levelId) {
        if (levelId == null) {
            return null;
        }
        String trimmed = levelId.trim();
        if (trimmed.isEmpty()) {
            return trimmed;
        }
        String canonical = CANONICAL.get(trimmed.toLowerCase(Locale.ROOT));
        return canonical != null ? canonical : trimmed;
    }

    public static String canonicalizeOrDefault(String levelId) {
        String canonical = canonicalizeLevelId(levelId);
        return canonical == null || canonical.isEmpty() ? DEFAULT_LEVEL : canonical;
    }

    public static boolean isFlagshipTutorial(String levelId) {
        return Objects.equals(canonicalizeLevelId(levelId), FLAGSHIP_TUTORIAL);
    }
}
