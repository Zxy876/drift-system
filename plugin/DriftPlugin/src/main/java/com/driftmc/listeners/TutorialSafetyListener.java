package com.driftmc.listeners;

import java.util.Locale;
import java.util.Map;
import java.util.UUID;
import java.util.concurrent.ConcurrentHashMap;

import org.bukkit.Bukkit;
import org.bukkit.Location;
import org.bukkit.Material;
import org.bukkit.World;
import org.bukkit.entity.Player;
import org.bukkit.event.EventHandler;
import org.bukkit.event.EventPriority;
import org.bukkit.event.Listener;
import org.bukkit.event.entity.EntityDamageEvent;
import org.bukkit.event.entity.EntityDamageEvent.DamageCause;
import org.bukkit.event.player.PlayerChangedWorldEvent;
import org.bukkit.event.player.PlayerMoveEvent;
import org.bukkit.event.player.PlayerQuitEvent;
import org.bukkit.event.player.PlayerRespawnEvent;
import org.bukkit.plugin.java.JavaPlugin;

import com.driftmc.scene.SceneLoader;

/**
 * Applies tutorial-only safeguards that prevent accidental death loops.
 */
public final class TutorialSafetyListener implements Listener {

    private static final String PRIMARY_TUTORIAL_WORLD = "KunmingLakeTutorial";
    private static final String FLAGSHIP_TUTORIAL_SCENE = "flagship_tutorial";
    private static final double DEFAULT_SAFE_X = 4.5D;
    private static final double DEFAULT_SAFE_Y = 68.0D;
    private static final double DEFAULT_SAFE_Z = 4.5D;

    private final JavaPlugin plugin;
    private final SceneLoader sceneLoader;
    private final Map<UUID, Location> lastStableLocation = new ConcurrentHashMap<>();

    public TutorialSafetyListener(JavaPlugin plugin, SceneLoader sceneLoader) {
        this.plugin = plugin;
        this.sceneLoader = sceneLoader;
    }

    @EventHandler(ignoreCancelled = true, priority = EventPriority.MONITOR)
    public void onPlayerMove(PlayerMoveEvent event) {
        Player player = event.getPlayer();
        if (!isInTutorialScene(player)) {
            return;
        }
        if (!isTutorialWorld(player.getWorld())) {
            return;
        }
        if (!hasMeaningfulMovement(event)) {
            return;
        }
        if (isStableGround(player)) {
            lastStableLocation.put(player.getUniqueId(), sanitize(player.getLocation()));
        }
    }

    @EventHandler(ignoreCancelled = true, priority = EventPriority.HIGHEST)
    public void onTutorialFall(EntityDamageEvent event) {
        if (!(event.getEntity() instanceof Player player)) {
            return;
        }
        if (!isInTutorialScene(player) || !isTutorialWorld(player.getWorld())) {
            return;
        }

        DamageCause cause = event.getCause();
        if (cause != DamageCause.FALL && cause != DamageCause.VOID) {
            return;
        }

        event.setCancelled(true);
        player.setFallDistance(0.0F);

        Location safe = resolveSafeAnchor(player);
        teleportSafely(player, safe);
        plugin.getLogger().info("[TutorialSafety] Fall damage prevented in flagship_tutorial for " + player.getName());
    }

    @EventHandler(priority = EventPriority.HIGHEST)
    public void onTutorialRespawn(PlayerRespawnEvent event) {
        Player player = event.getPlayer();
        Location respawnLocation = event.getRespawnLocation();
        if (respawnLocation == null) {
            return;
        }
        if (!isInTutorialScene(player) || !isTutorialWorld(respawnLocation.getWorld())) {
            return;
        }

        Location safe = resolveSafeAnchor(player);
        event.setRespawnLocation(safe);
        teleportSafely(player, safe);
    }

    @EventHandler
    public void onPlayerChangeWorld(PlayerChangedWorldEvent event) {
        lastStableLocation.remove(event.getPlayer().getUniqueId());
    }

    @EventHandler
    public void onPlayerQuit(PlayerQuitEvent event) {
        lastStableLocation.remove(event.getPlayer().getUniqueId());
    }

    private boolean isInTutorialScene(Player player) {
        return player != null
            && sceneLoader != null
            && sceneLoader.isPlayerInScene(player, FLAGSHIP_TUTORIAL_SCENE);
    }

    private boolean isTutorialWorld(World world) {
        if (world == null) {
            return false;
        }
        String name = world.getName();
        if (name == null) {
            return false;
        }
        if (name.equalsIgnoreCase(PRIMARY_TUTORIAL_WORLD)) {
            return true;
        }
        return name.toLowerCase(Locale.ROOT).contains("tutorial");
    }

    private boolean hasMeaningfulMovement(PlayerMoveEvent event) {
        Location from = event.getFrom();
        Location to = event.getTo();
        if (to == null) {
            return false;
        }
        return from.getX() != to.getX()
            || from.getY() != to.getY()
            || from.getZ() != to.getZ();
    }

    private boolean isStableGround(Player player) {
        if (player == null) {
            return false;
        }
        if (player.isOnGround()) {
            return true;
        }
        Location below = player.getLocation().clone().subtract(0.0D, 0.6D, 0.0D);
        Material material = below.getBlock().getType();
        return material.isSolid() || material == Material.WATER || material == Material.BUBBLE_COLUMN;
    }

    private Location resolveSafeAnchor(Player player) {
        Location sceneAnchor = sceneLoader != null ? sceneLoader.getSceneAnchor(player) : null;
        if (sceneAnchor != null) {
            return applyFacing(sceneAnchor, player);
        }

        UUID playerId = player.getUniqueId();
        Location stored = lastStableLocation.get(playerId);
        if (stored != null) {
            return stored.clone();
        }

        World world = player.getWorld();
        if (world != null && isTutorialWorld(world)) {
            Location spawn = sanitize(world.getSpawnLocation());
            if (spawn != null && spawn.getY() > world.getMinHeight()) {
                return applyFacing(spawn, player);
            }
            Location fallback = new Location(world, DEFAULT_SAFE_X, DEFAULT_SAFE_Y, DEFAULT_SAFE_Z);
            return applyFacing(fallback, player);
        }
        return sanitize(player.getLocation());
    }

    private Location applyFacing(Location base, Player reference) {
        if (base == null) {
            return null;
        }
        Location clone = base.clone();
        if (reference != null) {
            clone.setYaw(reference.getLocation().getYaw());
            clone.setPitch(reference.getLocation().getPitch());
        }
        return clone;
    }

    private Location sanitize(Location location) {
        return location == null ? null : location.clone();
    }

    private void teleportSafely(Player player, Location target) {
        if (player == null || target == null) {
            return;
        }
        Bukkit.getScheduler().runTask(plugin, () -> {
            player.teleport(target);
            lastStableLocation.put(player.getUniqueId(), target.clone());
        });
    }
}
