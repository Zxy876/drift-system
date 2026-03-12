package com.driftmc.scene;

import java.util.Map;

import org.bukkit.entity.Player;

/**
 * Bridge between backend scene metadata and the Bukkit runtime.
 */
public interface SceneLifecycleBridge {
    void handleScenePatch(Player player, Map<String, Object> metadata, Map<String, Object> operations);

    void handleSceneCleanup(Player player, Map<String, Object> metadata);
}
