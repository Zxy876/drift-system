package com.driftmc.cinematic;

import java.util.UUID;

import org.bukkit.Bukkit;
import org.bukkit.entity.Player;
import org.bukkit.plugin.java.JavaPlugin;

import com.driftmc.world.WorldPatchExecutor;

/**
 * Runtime context passed to individual cinematic actions.
 */
public class CinematicContext {

    private final JavaPlugin plugin;
    private final WorldPatchExecutor world;
    private final UUID playerId;
    private Float originalWalkSpeed;
    private Float originalFlySpeed;
    private boolean slowMotionApplied;

    public CinematicContext(JavaPlugin plugin, WorldPatchExecutor world, Player player) {
        this.plugin = plugin;
        this.world = world;
        this.playerId = player.getUniqueId();
    }

    public JavaPlugin getPlugin() {
        return plugin;
    }

    public WorldPatchExecutor getWorldExecutor() {
        return world;
    }

    public Player getPlayer() {
        return Bukkit.getPlayer(playerId);
    }

    public void applySlowMotion(double multiplier) {
        Player player = getPlayer();
        if (player == null) {
            return;
        }
        double clamped = Math.max(0.05d, Math.min(multiplier, 1.0d));
        if (!slowMotionApplied) {
            originalWalkSpeed = player.getWalkSpeed();
            originalFlySpeed = player.getFlySpeed();
            slowMotionApplied = true;
        }
        float walk = clampSpeed((float) (originalWalkSpeed * clamped));
        float fly = clampSpeed((float) (originalFlySpeed * clamped));
        player.setWalkSpeed(walk);
        player.setFlySpeed(fly);
    }

    public void clearSlowMotion() {
        if (!slowMotionApplied) {
            return;
        }
        Player player = getPlayer();
        if (player != null) {
            if (originalWalkSpeed != null) {
                player.setWalkSpeed(clampSpeed(originalWalkSpeed));
            }
            if (originalFlySpeed != null) {
                player.setFlySpeed(clampSpeed(originalFlySpeed));
            }
        }
        slowMotionApplied = false;
        originalWalkSpeed = null;
        originalFlySpeed = null;
    }

    private float clampSpeed(float speed) {
        return Math.max(-1.0f, Math.min(speed, 1.0f));
    }
}
