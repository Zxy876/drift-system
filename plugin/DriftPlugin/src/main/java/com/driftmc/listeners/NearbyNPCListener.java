package com.driftmc.listeners;

import java.util.LinkedHashMap;
import java.util.Locale;
import java.util.Map;
import java.util.Set;
import java.util.UUID;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.ConcurrentMap;
import java.util.logging.Level;

import org.bukkit.Bukkit;
import org.bukkit.ChatColor;
import org.bukkit.Location;
import org.bukkit.entity.AbstractVillager;
import org.bukkit.entity.Entity;
import org.bukkit.entity.Player;
import org.bukkit.entity.Projectile;
import org.bukkit.event.EventHandler;
import org.bukkit.event.EventPriority;
import org.bukkit.event.Listener;
import org.bukkit.event.entity.EntityDamageByEntityEvent;
import org.bukkit.event.player.PlayerInteractAtEntityEvent;
import org.bukkit.event.player.PlayerInteractEntityEvent;
import org.bukkit.event.player.PlayerMoveEvent;
import org.bukkit.inventory.EquipmentSlot;
import org.bukkit.metadata.MetadataValue;
import org.bukkit.plugin.java.JavaPlugin;
import org.bukkit.scheduler.BukkitTask;

import com.driftmc.DriftPlugin;
import com.driftmc.intent.IntentRouter;
import com.driftmc.npc.NPCManager;
import com.driftmc.scene.QuestEventCanonicalizer;
import com.driftmc.scene.RuleEventBridge;
import com.driftmc.session.PlayerSessionManager;
import com.driftmc.story.LevelIds;
import com.driftmc.story.StoryManager;
import com.driftmc.tutorial.TutorialManager;

import net.kyori.adventure.text.Component;
import net.kyori.adventure.text.format.NamedTextColor;

@SuppressWarnings("deprecation")
public class NearbyNPCListener implements Listener {

    private static final long NPC_INTERACT_COOLDOWN_MS = 2_000L;
    private static final long NEAR_INTENT_COOLDOWN_MS = 2_500L;
    private static final long NEAR_INTENT_DEBOUNCE_TICKS = 10L;
    private static final String NPC_ID_META = "npc_id";
    private static final String NPC_ID_PREFIX = "npc_id:";
    private static final String TUTORIAL_WORLD_NAME = "KunmingLakeTutorial";
    private static final String TUTORIAL_GUIDE_NAME = "心悦向导";
    private static final String TUTORIAL_GUIDE_ID = "tutorial_guide";
    private static final String TUTORIAL_COMPLETE_EVENT = "tutorial_complete";

    private final JavaPlugin plugin;
    private final NPCManager npcManager;
    private final IntentRouter router;
    private final RuleEventBridge ruleEvents;
    private final StoryManager storyManager;
    private final PlayerSessionManager sessions;
    private final TutorialManager tutorialManager;
    private final Map<String, Long> proximityCooldown = new ConcurrentHashMap<>();
    private final Map<UUID, Long> interactCooldown = new ConcurrentHashMap<>();
    private final Map<String, Long> npcQuestCooldown = new ConcurrentHashMap<>();
    private final Map<UUID, Long> nearIntentCooldown = new ConcurrentHashMap<>();
    private final Map<UUID, BukkitTask> pendingNearIntents = new ConcurrentHashMap<>();
    private final ConcurrentMap<UUID, Boolean> tutorialCompletionEmitted = new ConcurrentHashMap<>();

    public NearbyNPCListener(JavaPlugin plugin, NPCManager npcManager, IntentRouter router, RuleEventBridge ruleEvents,
            PlayerSessionManager sessions) {
        this.plugin = plugin;
        this.npcManager = npcManager;
        this.router = router;
        this.ruleEvents = ruleEvents;
        this.storyManager = plugin instanceof DriftPlugin drift ? drift.getStoryManager() : null;
        this.sessions = sessions;
        this.tutorialManager = plugin instanceof DriftPlugin drift ? drift.getTutorialManager() : null;
    }

    @EventHandler
    public void onMove(PlayerMoveEvent event) {

        Player p = event.getPlayer();
        if (p == null) {
            return;
        }

        UUID playerId = p.getUniqueId();

        if (shouldIgnoreTutorialListener(p)) {
            cancelPendingNearIntent(playerId);
            return;
        }

        boolean tutorialMovement = isTutorialMovement(p);
        if (tutorialMovement) {
            cancelPendingNearIntent(playerId);
        }

        String levelId = resolveCurrentLevel(p);
        boolean flagshipTutorial = LevelIds.isFlagshipTutorial(levelId);
        boolean tutorialCompleted = sessions != null && sessions.hasCompletedTutorial(p);

        for (Entity entity : npcManager.getSpawnedNPCs()) {

            if (entity == null)
                continue;
            if (!entity.isValid())
                continue;

            Location loc = entity.getLocation();
            if (loc.getWorld() != p.getWorld())
                continue;

            // 距离判断
            if (loc.distance(p.getLocation()) < 3) {

                String name = entity.getCustomName();
                if (name == null)
                    name = "未知NPC";

                String npcId = extractNpcId(entity);
                boolean tutorialGuide = isTutorialGuide(entity, name, npcId);

                if (tutorialGuide && hasFinishedTutorial(p)) {
                    continue;
                }

                boolean notify = shouldNotifyProximity(playerId, entity.getUniqueId());
                if (notify) {
                    p.sendMessage(ChatColor.LIGHT_PURPLE + "你靠近了 " + name + "。");
                    if (ruleEvents != null) {
                        ruleEvents.emitNearNpc(p, name, entity.getLocation());
                    }
                    if (!tutorialMovement && !shouldSuppressNearIntent(p)) {
                        scheduleNearIntent(p, entity, name);
                    }
                }
            }
        }

        if (tutorialMovement) {
            return;
        }
    }

    @EventHandler(ignoreCancelled = true)
    public void onInteract(PlayerInteractEntityEvent event) {
        if (event.getHand() != EquipmentSlot.HAND) {
            return;
        }
        plugin.getLogger().log(Level.INFO,
                "[NearbyNPCListener] PlayerInteractEntityEvent: {0} -> {1}",
                new Object[] { event.getPlayer().getName(), event.getRightClicked().getType() });
        if (handleNpcInteraction(event.getPlayer(), event.getRightClicked())) {
            event.setCancelled(true);
        }
    }

    @EventHandler(ignoreCancelled = true)
    public void onInteractAt(PlayerInteractAtEntityEvent event) {
        if (event.getHand() != EquipmentSlot.HAND) {
            return;
        }
        plugin.getLogger().log(Level.INFO,
                "[NearbyNPCListener] PlayerInteractAtEntityEvent: {0} -> {1}",
                new Object[] { event.getPlayer().getName(), event.getRightClicked().getType() });
        if (handleNpcInteraction(event.getPlayer(), event.getRightClicked())) {
            event.setCancelled(true);
        }
    }

    @EventHandler(priority = EventPriority.MONITOR, ignoreCancelled = true)
    public void onNpcDamaged(EntityDamageByEntityEvent event) {
        if (ruleEvents == null || npcManager == null) {
            return;
        }

        Entity target = event.getEntity();
        if (!npcManager.isNpc(target)) {
            return;
        }

        Player attacker = resolvePlayerDamager(event.getDamager());
        if (attacker == null) {
            return;
        }

        String npcName = target.getCustomName();
        if (npcName == null || npcName.isBlank()) {
            npcName = "未知NPC";
        }

        ruleEvents.emitNpcAttack(attacker, target, extractNpcId(target), npcName, event.getFinalDamage());
    }

    private boolean shouldNotifyProximity(UUID playerId, UUID entityId) {
        long now = System.currentTimeMillis();
        String key = playerId + ":" + entityId;
        Long last = proximityCooldown.get(key);
        if (last != null && now - last < 3_000L) {
            return false;
        }
        proximityCooldown.put(key, now);
        return true;
    }

    private void scheduleNearIntent(Player player, Entity entity, String displayName) {
        if (router == null || player == null) {
            return;
        }

        if (shouldIgnoreTutorialListener(player)) {
            cancelPendingNearIntent(player.getUniqueId());
            return;
        }

        if (isTutorialMovement(player)) {
            cancelPendingNearIntent(player.getUniqueId());
            return;
        }

        UUID playerId = player.getUniqueId();
        BukkitTask existing = pendingNearIntents.remove(playerId);
        if (existing != null) {
            existing.cancel();
        }

        BukkitTask task = Bukkit.getScheduler().runTaskLater(plugin, () -> {
            pendingNearIntents.remove(playerId);

            if (!consumeNearIntent(playerId)) {
                return;
            }

            Player current = Bukkit.getPlayer(playerId);
            if (current == null || !current.isOnline()) {
                return;
            }

            if (shouldSuppressNearIntent(current)) {
                return;
            }

            if (entity != null && entity.isValid()) {
                Location playerLoc = current.getLocation();
                Location entityLoc = entity.getLocation();
                if (entityLoc.getWorld() != playerLoc.getWorld()) {
                    return;
                }
                if (entityLoc.distanceSquared(playerLoc) > 9.0D) {
                    return;
                }
            }

            router.handlePlayerSpeak(current, "我靠近了 " + displayName);

        }, NEAR_INTENT_DEBOUNCE_TICKS);

        pendingNearIntents.put(playerId, task);
    }

    private void cancelPendingNearIntent(UUID playerId) {
        BukkitTask pending = pendingNearIntents.remove(playerId);
        if (pending != null) {
            pending.cancel();
        }
    }

    private boolean consumeNearIntent(UUID playerId) {
        long now = System.currentTimeMillis();
        Long last = nearIntentCooldown.get(playerId);
        if (last != null && now - last < NEAR_INTENT_COOLDOWN_MS) {
            return false;
        }
        nearIntentCooldown.put(playerId, now);
        return true;
    }

    private boolean shouldSuppressNearIntent(Player player) {
        if (player == null) {
            return false;
        }
        if (sessions != null && sessions.isTutorial(player)) {
            return true;
        }
        if (sessions == null) {
            return false;
        }
        if (sessions.hasCompletedTutorial(player)) {
            return false;
        }
        return isFlagshipTutorialLevel(player);
    }

    private boolean isTutorialMovement(Player player) {
        if (player == null) {
            return false;
        }
        return sessions != null && sessions.isTutorial(player);
    }

    private boolean isInTutorialWorld(Location location) {
        if (location == null || location.getWorld() == null) {
            return false;
        }
        String worldName = location.getWorld().getName();
        if (worldName.isBlank()) {
            return false;
        }
        if (worldName.equalsIgnoreCase(TUTORIAL_WORLD_NAME)) {
            return true;
        }
        return worldName.toLowerCase(Locale.ROOT).contains("tutorial");
    }

    private boolean tryConsumeInteract(UUID playerId) {
        long now = System.currentTimeMillis();
        Long last = interactCooldown.get(playerId);
        if (last != null && now - last < 750L) {
            return false;
        }
        interactCooldown.put(playerId, now);
        return true;
    }

    private boolean handleNpcInteraction(Player player, Entity target) {
        if (player == null || target == null) {
            return false;
        }
        if (!npcManager.isNpc(target)) {
            return false;
        }

        UUID playerId = player.getUniqueId();
        if (!tryConsumeInteract(playerId)) {
            return true;
        }

        String displayName = target.getCustomName();
        if (displayName == null || displayName.isBlank()) {
            displayName = "未知NPC";
        }

        plugin.getLogger().log(Level.INFO,
                "[NearbyNPCListener] Handling interaction: player={0}, entity={1}, type={2}",
                new Object[] { player.getName(), displayName, target.getType() });

        String npcId = extractNpcId(target);
        String levelId = resolveCurrentLevel(player);
        boolean flagshipTutorial = LevelIds.isFlagshipTutorial(levelId);
        boolean tutorialGuide = isTutorialGuide(target, displayName, npcId);
        boolean tutorialCompleted = sessions != null && sessions.hasCompletedTutorial(player);
        boolean awaitingFinalize = tutorialCompletionEmitted.containsKey(playerId)
                || (tutorialManager != null && tutorialManager.hasCompletionEmitted(player));
        boolean suppressIntent = (tutorialCompleted || awaitingFinalize) && (tutorialGuide || flagshipTutorial);
        boolean emittedCompletion = false;

        if (tutorialCompleted && (tutorialGuide || flagshipTutorial)) {
            if (tutorialGuide) {
                player.sendMessage(ChatColor.GRAY + "你已经完成教程，心悦向导在主线入口等待你。");
            }
            return true;
        }

        if (tutorialGuide && flagshipTutorial && !tutorialCompleted) {
            if (awaitingFinalize) {
                player.sendMessage(ChatColor.LIGHT_PURPLE + "你与【" + displayName + "】交谈。");
                player.sendActionBar(Component.text("你与【" + displayName + "】交谈", NamedTextColor.LIGHT_PURPLE));
                return true;
            }
            emittedCompletion = tryEmitTutorialComplete(player, target, levelId);
            if (emittedCompletion) {
                cancelPendingNearIntent(playerId);
                player.sendMessage(ChatColor.LIGHT_PURPLE + "你与【" + displayName + "】交谈。");
                player.sendActionBar(Component.text("你与【" + displayName + "】交谈", NamedTextColor.LIGHT_PURPLE));
                return true;
            }
        }

        player.sendMessage(ChatColor.LIGHT_PURPLE + "你与【" + displayName + "】交谈。");
        player.sendActionBar(Component.text("你与【" + displayName + "】交谈", NamedTextColor.LIGHT_PURPLE));

        if (ruleEvents != null) {
            if (!(tutorialGuide && flagshipTutorial)) {
                ruleEvents.emitNpcTalk(player, target, npcId, displayName, "right_click");
                if (isTradeNpc(target)) {
                    ruleEvents.emitNpcTrade(player, target, npcId, displayName);
                }
                ruleEvents.emitInteractEntity(player, target, "right_click");

                String questEvent = npcManager.lookupQuestEvent(target);
                if (questEvent.isBlank() && !npcId.isBlank()) {
                    questEvent = npcManager.lookupQuestEvent(npcId);
                }
                if (questEvent.isBlank()) {
                    questEvent = npcManager.lookupQuestEvent(displayName);
                }

                String canonicalQuestEvent = QuestEventCanonicalizer.canonicalize(questEvent);
                String eventType = !canonicalQuestEvent.isEmpty() ? canonicalQuestEvent : questEvent;
                String canonicalNpcName = npcId.isBlank() ? displayName : npcId;
                String triggerEvent = eventType;
                if (triggerEvent.isBlank()) {
                    triggerEvent = buildDefaultNpcTriggerEvent(canonicalNpcName, displayName, target);
                }

                if (!triggerEvent.isBlank() && consumeNpcQuest(player.getUniqueId(), "npc_trigger:" + triggerEvent)) {
                    Map<String, Object> payload = new LinkedHashMap<>();
                    payload.put("source", "npc_interact");
                    payload.put("npc", canonicalNpcName);
                    if (!levelId.isBlank()) {
                        payload.put("level_id", levelId);
                    }
                    appendLocation(payload, target.getLocation());
                    ruleEvents.emitNpcTrigger(player, target, canonicalNpcName, displayName, triggerEvent, payload);

                    if (!eventType.isBlank()) {
                        ruleEvents.emit(player, eventType, payload);
                        player.sendMessage(ChatColor.GOLD + "触发事件: " + eventType);
                        plugin.getLogger().log(Level.INFO,
                                "[NearbyNPCListener] Emitted event {0} + npc_trigger({1}) for player {2} (npc={3})",
                                new Object[] { eventType, triggerEvent, player.getName(), canonicalNpcName });
                    } else {
                        plugin.getLogger().log(Level.INFO,
                                "[NearbyNPCListener] Emitted default npc_trigger {0} for player {1} (npc={2})",
                                new Object[] { triggerEvent, player.getName(), canonicalNpcName });
                    }
                } else {
                    plugin.getLogger().log(Level.INFO,
                            "[NearbyNPCListener] Interaction throttled or unresolved: player={0}, npc={1}, event={2}, trigger={3}",
                            new Object[] { player.getName(), npcId.isBlank() ? displayName : npcId, eventType, triggerEvent });
                }
            }
        }

        if (router != null && !suppressIntent && !emittedCompletion) {
            router.handlePlayerSpeak(player, "我与 " + displayName + " 互动");
        }

        return true;
    }

    // player_like NPCs now spawn as HumanEntity with metadata instead of
    // ArmorStand, so
    // we must pull the canonical npc_id to ensure quest events fire regardless of
    // display name.

    private boolean hasFinishedTutorial(Player player) {
        if (player == null || sessions == null) {
            return false;
        }
        return sessions.hasCompletedTutorial(player);
    }

    private boolean shouldIgnoreTutorialListener(Player player) {
        if (player == null) {
            return false;
        }
        if (tutorialCompletionEmitted.containsKey(player.getUniqueId())
                || (tutorialManager != null && tutorialManager.hasCompletionEmitted(player))) {
            return true;
        }
        if (!hasFinishedTutorial(player)) {
            return false;
        }
        Location location = player.getLocation();
        if (isInTutorialWorld(location)) {
            return true;
        }
        return isFlagshipTutorialLevel(player);
    }

    private boolean tryEmitTutorialComplete(Player player, Entity entity, String levelId) {
        if (player == null || ruleEvents == null || sessions == null) {
            return false;
        }
        if (!LevelIds.isFlagshipTutorial(levelId)) {
            return false;
        }
        if (sessions.hasCompletedTutorial(player)) {
            return false;
        }
        UUID playerId = player.getUniqueId();
        if (tutorialManager != null && tutorialManager.hasCompletionEmitted(player)) {
            tutorialCompletionEmitted.putIfAbsent(playerId, Boolean.TRUE);
            return false;
        }
        if (tutorialCompletionEmitted.putIfAbsent(playerId, Boolean.TRUE) != null) {
            return false;
        }

        if (tutorialManager != null) {
            tutorialManager.markCompletionEmitted(player);
        }

        Map<String, Object> payload = new LinkedHashMap<>();
        payload.put("source", "tutorial_finalize");
        payload.put("npc", TUTORIAL_GUIDE_NAME);
        if (!levelId.isBlank()) {
            payload.put("level_id", levelId);
        }

        Location location = entity != null ? entity.getLocation() : player.getLocation();
        ruleEvents.emitQuestEvent(player, TUTORIAL_COMPLETE_EVENT, location, payload);
        return true;
    }

    private String extractNpcId(Entity entity) {
        if (entity.hasMetadata(NPC_ID_META)) {
            for (MetadataValue value : entity.getMetadata(NPC_ID_META)) {
                String raw = value.asString();
                String trimmed = raw.trim();
                if (!trimmed.isEmpty()) {
                    return trimmed;
                }
            }
        }

        Set<String> tags = entity.getScoreboardTags();
        for (String tag : tags) {
            if (tag == null) {
                continue;
            }
            if (tag.startsWith(NPC_ID_PREFIX)) {
                String trimmed = tag.substring(NPC_ID_PREFIX.length()).trim();
                if (!trimmed.isEmpty()) {
                    return trimmed;
                }
            }
        }

        return "";
    }

    private boolean consumeNpcQuest(UUID playerId, String questEvent) {
        long now = System.currentTimeMillis();
        String key = playerId + ":" + questEvent;
        Long last = npcQuestCooldown.get(key);
        if (last != null && now - last < NPC_INTERACT_COOLDOWN_MS) {
            return false;
        }
        npcQuestCooldown.put(key, now);
        return true;
    }

    private boolean isTutorialGuide(Entity entity, String displayName, String npcId) {
        if (entity == null) {
            return false;
        }
        if (npcId != null && !npcId.isBlank() && npcId.equalsIgnoreCase(TUTORIAL_GUIDE_ID)) {
            return true;
        }
        String stripped = displayName != null ? ChatColor.stripColor(displayName) : null;
        if (stripped != null && stripped.contains(TUTORIAL_GUIDE_NAME)) {
            return true;
        }
        Set<String> tags = entity.getScoreboardTags();
        for (String tag : tags) {
            if (tag == null) {
                continue;
            }
            String lowerTag = tag.toLowerCase(Locale.ROOT);
            if (lowerTag.contains(TUTORIAL_GUIDE_ID)) {
                return true;
            }
            if (lowerTag.contains(TUTORIAL_GUIDE_NAME)) {
                return true;
            }
        }
        return false;
    }

    private String resolveCurrentLevel(Player player) {
        if (player == null || storyManager == null) {
            return "";
        }
        return LevelIds.canonicalizeOrDefault(storyManager.getCurrentLevel(player));
    }

    private boolean isFlagshipTutorialLevel(Player player) {
        String levelId = resolveCurrentLevel(player);
        return LevelIds.isFlagshipTutorial(levelId);
    }

    private boolean isTradeNpc(Entity entity) {
        return entity instanceof AbstractVillager;
    }

    private Player resolvePlayerDamager(Entity damager) {
        if (damager instanceof Player) {
            return (Player) damager;
        }

        if (damager instanceof Projectile) {
            Projectile projectile = (Projectile) damager;
            Object shooter = projectile.getShooter();
            if (shooter instanceof Player) {
                return (Player) shooter;
            }
        }

        return null;
    }

    private String buildDefaultNpcTriggerEvent(String npcId, String displayName, Entity target) {
        String base = npcId;
        if (base == null || base.isBlank()) {
            base = displayName;
        }

        String stripped = base != null ? ChatColor.stripColor(base) : "";
        String normalized = stripped != null ? stripped.trim().toLowerCase(Locale.ROOT) : "";

        normalized = normalized.replaceAll("[\\s\\-]+", "_");
        normalized = normalized.replaceAll("[^\\p{L}\\p{N}_]+", "_");
        normalized = normalized.replaceAll("_+", "_");

        if (normalized.startsWith("_")) {
            normalized = normalized.substring(1);
        }
        if (normalized.endsWith("_")) {
            normalized = normalized.substring(0, normalized.length() - 1);
        }

        if (normalized.isBlank() && target != null) {
            normalized = target.getType().name().toLowerCase(Locale.ROOT);
        }
        if (normalized.isBlank()) {
            normalized = "npc";
        }

        return "npc_interact_" + normalized;
    }

    private void appendLocation(Map<String, Object> payload, Location location) {
        if (payload == null || location == null) {
            return;
        }
        Map<String, Object> loc = new LinkedHashMap<>();
        if (location.getWorld() != null) {
            loc.put("world", location.getWorld().getName());
        }
        loc.put("x", location.getX());
        loc.put("y", location.getY());
        loc.put("z", location.getZ());
        payload.put("location", loc);
    }
}