package com.driftmc.scene;

import java.util.Collections;
import java.util.HashMap;
import java.util.Locale;
import java.util.Map;

/**
 * Normalises quest event identifiers emitted by the plugin before they reach
 * the backend.
 */
public final class QuestEventCanonicalizer {

    private static final Map<String, String> ALIASES;

    static {
        Map<String, String> aliases = new HashMap<>();
        register(aliases, "tutorial_intro_started",
                "tutorial_begin",
                "tutorial_intro",
                "tutorial_start",
                "tutorial_open");
        register(aliases, "tutorial_meet_guide",
                "tutorial_question",
                "tutorial_greet",
                "tutorial_guide",
                "tutorial_talk_guide");
        register(aliases, "tutorial_complete",
                "tutorial_reach_checkpoint",
                "tutorial_progress",
                "tutorial_checkpoint",
                "tutorial_checkpoint_reach",
                "tutorial_task_complete",
                "tutorial_exit",
                "tutorial_finish",
                "tutorial_end");
        String[] flagshipEvents = {
                "intro_calm",
                "fear_pulse",
                "summit_view",
                "flagship_08_intro",
                "approach_grandma",
                "approach_heart_demon",
                "comfort_path",
                "deny_path",
                "fight_path",
                "escape_path",
                "flagship_08_reconcile",
                "flagship_08_linger",
                "flagship_08_ending",
                "night12_crossroad_choice",
                "night12_pharmacy_counsel",
                "night12_shadow_whisper",
                "night12_take_now",
                "night12_pocket_pills",
                "night12_listen_shadow",
                "night12_run_shadow",
                "night12_branch_dialogue",
                "night12_branch_choice",
                "finale_arrival",
                "final_face_branch",
                "final_escape_branch",
                "final_face_step",
                "final_face_listen",
                "final_escape_loop",
                "final_escape_pause",
                "final_face_resolution",
                "final_escape_resolution",
                "finale_resolution",
                "final_closure",
                "flagship_12_face_recap",
                "flagship_12_escape_recap",
                "flagship_12_ending"
        };
        for (String event : flagshipEvents) {
            registerCanonical(aliases, event);
        }
        ALIASES = Collections.unmodifiableMap(aliases);
    }

    private QuestEventCanonicalizer() {
    }

    private static void register(Map<String, String> map, String canonical, String... aliases) {
        String canonicalKey = canonical.toLowerCase(Locale.ROOT);
        map.put(canonicalKey, canonical);
        for (String alias : aliases) {
            if (alias == null || alias.isBlank()) {
                continue;
            }
            map.put(alias.trim().toLowerCase(Locale.ROOT), canonical);
        }
    }

    private static void registerCanonical(Map<String, String> map, String canonical) {
        if (canonical == null || canonical.isBlank()) {
            return;
        }
        String dashVariant = canonical.replace('_', '-');
        String dotVariant = canonical.replace('_', '.');
        if (dashVariant.equals(canonical)) {
            dashVariant = null;
        }
        if (dotVariant.equals(canonical)) {
            dotVariant = null;
        }
        register(map, canonical, dashVariant, dotVariant);
    }

    /**
     * Canonicalises a quest event token. Returns an empty string when no token is
     * present.
     */
    public static String canonicalize(String event) {
        if (event == null) {
            return "";
        }
        String token = event.trim().toLowerCase(Locale.ROOT);
        if (token.isEmpty()) {
            return "";
        }
        String mapped = ALIASES.get(token);
        return mapped != null ? mapped : token;
    }

    /**
     * Mutates the provided payload map in-place so that the {@code quest_event}
     * entry is canonical.
     */
    public static void canonicalizePayload(Map<String, Object> payload) {
        if (payload == null || payload.isEmpty()) {
            return;
        }
        Object questEvent = payload.get("quest_event");
        if (questEvent == null) {
            return;
        }
        String canonical = canonicalize(String.valueOf(questEvent));
        if (!canonical.isEmpty()) {
            payload.put("quest_event", canonical);
        }
    }
}
