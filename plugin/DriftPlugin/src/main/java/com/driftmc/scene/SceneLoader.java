package com.driftmc.scene;

import java.util.LinkedHashMap;
import java.util.Map;
import java.util.Objects;
import java.util.logging.Level;

import org.bukkit.Location;
import org.bukkit.entity.Player;
import org.bukkit.plugin.java.JavaPlugin;

import com.driftmc.cinematic.CinematicController;
import com.driftmc.npc.NPCManager;
import com.driftmc.world.WorldPatchExecutor;

/**
 * Coordinates scene application and cleanup for a player.
 */
public final class SceneLoader implements SceneLifecycleBridge {

    private final JavaPlugin plugin;
    private final SceneCleanupService cleanup;
    private final WorldPatchExecutor world;
    private final NPCManager npcManager;
    private CinematicController cinematicController;

    public SceneLoader(JavaPlugin plugin, WorldPatchExecutor world, NPCManager npcManager) {
        this.plugin = Objects.requireNonNull(plugin, "plugin");
        this.world = Objects.requireNonNull(world, "world");
        this.cleanup = new SceneCleanupService(plugin, this.world);
        this.npcManager = Objects.requireNonNull(npcManager, "npcManager");
    }

    @Override
    public void handleScenePatch(Player player, Map<String, Object> metadata, Map<String, Object> operations) {
        if (player == null || operations == null || operations.isEmpty()) {
            return;
        }
        cleanup.beginSession(player, metadata, operations);
        world.ensureFeaturedNpc(player, metadata, operations);
        npcManager.onScenePatch(player, metadata, operations);
        triggerCinematic(player, metadata, operations);
        emitSceneEntryTrigger(player, metadata);
        plugin.getLogger().log(Level.FINE, "[SceneLoader] Scene applied for player {0}", player.getName());
    }

    @Override
    public void handleSceneCleanup(Player player, Map<String, Object> metadata) {
        if (player == null) {
            return;
        }
        cleanup.cleanup(player, metadata);
        npcManager.onSceneCleanup(player, metadata);
    }

    public void shutdown() {
        cleanup.cleanupAll();
    }

    public void setCinematicController(CinematicController cinematicController) {
        this.cinematicController = cinematicController;
    }

    public void handleCinematic(Player player, Map<String, Object> definition) {
        if (player == null || cinematicController == null || definition == null || definition.isEmpty()) {
            return;
        }
        Map<String, Object> copy = ScenePatchUtils.deepCopyMap(definition);
        cinematicController.playSequence(player, copy);
    }

    private void triggerCinematic(Player player, Map<String, Object> metadata, Map<String, Object> operations) {
        if (player == null || cinematicController == null) {
            return;
        }
        Map<String, Object> candidate = null;
        if (metadata != null) {
            Object metaCinematic = metadata.get("cinematic");
            if (metaCinematic instanceof Map<?, ?> map) {
                candidate = ScenePatchUtils.deepCopyMap(map);
            }
        }
        if (candidate == null && operations != null) {
            Object opCinematic = operations.get("_cinematic");
            if (opCinematic instanceof Map<?, ?> map) {
                candidate = ScenePatchUtils.deepCopyMap(map);
            }
        }
        if (candidate != null && !candidate.isEmpty()) {
            cinematicController.playSequence(player, candidate);
        }
    }

    private void emitSceneEntryTrigger(Player player, Map<String, Object> metadata) {
        if (player == null || metadata == null) {
            return;
        }
        RuleEventBridge bridge = world.getRuleEventBridge();
        if (bridge == null) {
            return;
        }

        String trigger = asString(metadata.get("entry_trigger"));
        if (trigger.isBlank()) {
            trigger = asString(metadata.get("entry_rule_event"));
        }
        if (trigger.isBlank()) {
            return;
        }

        Map<String, Object> payload = new LinkedHashMap<>();
        payload.put("source", "scene_entry");
        bridge.emitQuestEvent(player, trigger, player.getLocation(), payload);
    }

    private String asString(Object value) {
        return value == null ? "" : value.toString().trim();
    }

    public boolean isPlayerInScene(Player player, String sceneId) {
        if (player == null) {
            return false;
        }
        return cleanup.isPlayerInScene(player.getUniqueId(), sceneId);
    }

    public Location getSceneAnchor(Player player) {
        if (player == null) {
            return null;
        }
        SceneSession session = cleanup.getSession(player.getUniqueId());
        if (session == null) {
            return null;
        }
        Location anchor = session.getAnchor();
        return anchor == null ? null : anchor.clone();
    }

    public String getActiveSceneId(Player player) {
        if (player == null) {
            return null;
        }
        SceneSession session = cleanup.getSession(player.getUniqueId());
        return session == null ? null : session.getSceneId();
    }

    public void endSession(Player player, String reason) {
        cleanup.endSession(player, reason);
    }
}
