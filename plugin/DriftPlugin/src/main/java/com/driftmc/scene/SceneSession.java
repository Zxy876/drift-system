package com.driftmc.scene;

import java.util.Collections;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.UUID;

import org.bukkit.Location;
import org.bukkit.entity.Player;

@SuppressWarnings("unused")
final class SceneSession {

    private final UUID playerId;
    private final String sceneId;
    private final Location anchor;
    private final double triggerRadius;
    private final Map<String, Object> operations;
    private boolean insideRadius;

    private SceneSession(UUID playerId,
                         String sceneId,
                         Location anchor,
                         double triggerRadius,
                         Map<String, Object> operations) {
        this.playerId = playerId;
        this.sceneId = sceneId;
        this.anchor = anchor;
        this.triggerRadius = triggerRadius;
        this.operations = operations;
    }

    static SceneSession create(Player player,
                               Map<String, Object> metadata,
                               Map<String, Object> operations) {
        String sceneId = "scene";
        if (metadata != null) {
            Object levelId = metadata.get("level_id");
            if (levelId instanceof String s && !s.isBlank()) {
                sceneId = s;
            } else {
                Object sceneIdAlt = metadata.get("scene_id");
                if (sceneIdAlt instanceof String s2 && !s2.isBlank()) {
                    sceneId = s2;
                }
            }
        }
        double radius = metadata != null && metadata.get("radius") instanceof Number num
                ? num.doubleValue()
                : 6.0d;
        Location anchor = player.getLocation().clone();
        Map<String, Object> opsCopy = ScenePatchUtils.deepCopyMap(operations);
        return new SceneSession(player.getUniqueId(), sceneId, anchor, radius, opsCopy);
    }

    UUID getPlayerId() {
        return playerId;
    }

    String getSceneId() {
        return sceneId;
    }

    Location getAnchor() {
        return anchor;
    }

    double getTriggerRadius() {
        return triggerRadius;
    }

    boolean isInsideRadius() {
        return insideRadius;
    }

    void setInsideRadius(boolean inside) {
        this.insideRadius = inside;
    }

    Map<String, Object> buildCleanupPatch() {
        Map<String, Object> cleanup = new LinkedHashMap<>();

        Object build = operations.get("build");
        if (build instanceof Map<?, ?> map) {
            cleanup.put("build", ScenePatchUtils.invertBuild(map));
        }

        Object buildMulti = operations.get("build_multi");
        if (buildMulti instanceof List<?> list) {
            cleanup.put("build_multi", ScenePatchUtils.invertBuildList(list));
        }

        if (cleanup.isEmpty()) {
            return Collections.emptyMap();
        }
        return cleanup;
    }

    void reset() {
        this.insideRadius = false;
    }
}
