package com.driftmc.npc;

import java.util.ArrayList;
import java.util.Collections;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Locale;
import java.util.Map;
import java.util.Set;
import java.util.UUID;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.CopyOnWriteArrayList;
import java.util.logging.Level;

import org.bukkit.Bukkit;
import org.bukkit.ChatColor;
import org.bukkit.Location;
import org.bukkit.Material;
import org.bukkit.OfflinePlayer;
import org.bukkit.World;
import org.bukkit.entity.ArmorStand;
import org.bukkit.entity.Entity;
import org.bukkit.entity.EntityType;
import org.bukkit.entity.LivingEntity;
import org.bukkit.entity.Player;
import org.bukkit.entity.Rabbit;
import org.bukkit.event.EventHandler;
import org.bukkit.event.Listener;
import org.bukkit.event.entity.CreatureSpawnEvent;
import org.bukkit.event.entity.CreatureSpawnEvent.SpawnReason;
import org.bukkit.event.entity.EntityDeathEvent;
import org.bukkit.inventory.ItemStack;
import org.bukkit.inventory.meta.SkullMeta;
import org.bukkit.plugin.java.JavaPlugin;
import org.bukkit.scheduler.BukkitRunnable;
import org.bukkit.scheduler.BukkitTask;

import com.driftmc.scene.QuestEventCanonicalizer;

import net.kyori.adventure.text.Component;
import net.kyori.adventure.text.format.NamedTextColor;
import net.kyori.adventure.text.serializer.plain.PlainTextComponentSerializer;

public class NPCManager implements Listener {

    private static final String NPC_TAG = "drift:npc";
    private static final long PENDING_EXPIRY_MS = 6_000L;

    private static final Map<String, String> NAMEPLATE_OVERRIDES;
    private static final Map<String, String> SKIN_FALLBACK_PLAYERS;
    private static final String DEFAULT_SKIN_OWNER = "MHF_Villager";

    static {
        Map<String, String> names = new LinkedHashMap<>();
        names.put("赛车手桃子", "桃子 · 赛道教练");
        names.put("心悦向导", "心悦向导 · 教学引导");
        names.put("登山者", "登山者 · 山地向导");
        NAMEPLATE_OVERRIDES = Collections.unmodifiableMap(names);

        Map<String, String> skins = new LinkedHashMap<>();
        skins.put("tutorial_guide", "MHF_Villager");
        skins.put("racer_taozi", "MHF_Rabbit");
        skins.put("climber_summit", "MHF_SnowGolem");
        SKIN_FALLBACK_PLAYERS = Collections.unmodifiableMap(skins);
    }

    private final JavaPlugin plugin;

    private final CopyOnWriteArrayList<Entity> spawnedNPCs = new CopyOnWriteArrayList<>();
    private final Map<UUID, MarkerHandle> markers = new ConcurrentHashMap<>();
    private final Map<String, NpcSkin> activeSkins = new ConcurrentHashMap<>();
    private final Map<String, Long> pendingSpawns = new ConcurrentHashMap<>();
    private final Map<String, EmotionProfile> emotionProfiles = new ConcurrentHashMap<>();
    private final Map<String, String> npcQuestTriggers = new ConcurrentHashMap<>();

    public NPCManager(JavaPlugin plugin) {
        this.plugin = plugin;
    }

    public List<Entity> getSpawnedNPCs() {
        spawnedNPCs.removeIf(entity -> entity == null || !entity.isValid());
        return spawnedNPCs;
    }

    public void registerAutoFeaturedNpc(LivingEntity entity, String declaredName) {
        if (entity == null) {
            return;
        }
        String name = declaredName;
        if (name == null || name.isBlank()) {
            name = resolveName(entity);
        }
        if (!name.isBlank()) {
            pendingSpawns.remove(normalize(name));
        }
        registerNpc(entity, name);
    }

    public boolean isNpc(Entity entity) {
        if (entity == null) {
            return false;
        }
        Set<String> tags = entity.getScoreboardTags();
        if (tags != null && tags.contains(NPC_TAG)) {
            return true;
        }
        return spawnedNPCs.contains(entity);
    }

    public void spawnRabbit(Player player, String name) {
        Location loc = player.getLocation();
        World world = loc.getWorld();
        if (world == null) {
            return;
        }

        Location spawnLoc = loc.clone().add(1, 0, 1);
        Rabbit rabbit = (Rabbit) world.spawnEntity(spawnLoc, EntityType.RABBIT);
        rabbit.customName(Component.text(name, NamedTextColor.LIGHT_PURPLE));
        rabbit.setCustomNameVisible(true);
        rabbit.addScoreboardTag(NPC_TAG);
        registerNpc(rabbit, name);
        player.sendMessage(Component.text("NPC " + name + " 已出现。", NamedTextColor.AQUA));
    }

    public void onScenePatch(Player player, Map<String, Object> metadata, Map<String, Object> operations) {
        registerSceneSkins(metadata);
        registerNpcQuestEvents(metadata, operations);
        collectPendingNames(operations);
        Bukkit.getScheduler().runTask(plugin, this::refreshNpcAppearances);
    }

    public void onSceneCleanup(Player player, Map<String, Object> metadata) {
        activeSkins.clear();
        pendingSpawns.clear();
        npcQuestTriggers.clear();
        refreshNpcAppearances();
    }

    public void applyEmotionPatch(Player player, Map<String, Object> payload) {
        if (payload == null || payload.isEmpty()) {
            return;
        }

        String tone = asString(payload.get("tone"));
        String label = asString(payload.get("label"));
        List<String> targets = asStringList(payload.get("targets"));
        if (targets.isEmpty()) {
            targets = List.of("心悦向导", "登山者");
        }

        EmotionProfile profile = new EmotionProfile(label, tone, System.currentTimeMillis());
        for (String target : targets) {
            if (target == null || target.isBlank()) {
                continue;
            }
            emotionProfiles.put(normalize(target), profile);
        }

        refreshNpcAppearances();

        List<String> lines = asStringList(payload.get("lines"));
        if (player != null && !lines.isEmpty()) {
            for (String line : lines) {
                if (line.isBlank()) {
                    continue;
                }
                player.sendMessage(Component.text(line, NamedTextColor.GOLD));
            }
        }

        String actionbar = asString(payload.get("actionbar"));
        if (player != null && !actionbar.isBlank()) {
            player.sendActionBar(Component.text(actionbar, NamedTextColor.AQUA));
        }
    }

    @EventHandler(ignoreCancelled = true)
    public void onEntitySpawn(CreatureSpawnEvent event) {
        LivingEntity entity = event.getEntity();

        String declared = resolveName(entity);
        String canonical = normalize(declared);

        boolean expected = pendingSpawns.containsKey(canonical);
        if (!expected) {
            if (!entity.getScoreboardTags().contains(NPC_TAG)) {
                // Non-managed spawn
                return;
            }
        } else {
            Long expiry = pendingSpawns.get(canonical);
            if (expiry != null && expiry < System.currentTimeMillis()) {
                pendingSpawns.remove(canonical);
                expected = false;
            }
        }

        if (!expected && event.getSpawnReason() != SpawnReason.CUSTOM) {
            return;
        }

        pendingSpawns.remove(canonical);
        registerNpc(entity, declared);
    }

    @EventHandler
    public void onEntityDeath(EntityDeathEvent event) {
        unregisterNpc(event.getEntity());
    }

    private void registerNpc(LivingEntity entity, String declaredName) {
        if (entity == null) {
            return;
        }
        if (isTutorialWorld(entity) && isDuplicateTutorialNpc(declaredName)) {
            plugin.getLogger().log(Level.FINE,
                    "[NPCManager] Suppressed duplicate tutorial NPC spawn: {0}",
                    declaredName);
            pendingSpawns.remove(normalize(declaredName));
            entity.remove();
            return;
        }
        if (!spawnedNPCs.contains(entity)) {
            spawnedNPCs.add(entity);
        }

        if (entity instanceof ArmorStand armorStand) {
            // ArmorStand markers ignore interactions; ensure the featured NPC keeps a
            // hitbox.
            armorStand.setMarker(false);
            armorStand.setInvisible(false);
            armorStand.setSmall(false);
            armorStand.setGravity(false);
        }

        applyAppearance(entity, declaredName);
        entity.addScoreboardTag(NPC_TAG);

        String baseName = resolveName(entity);
        String worldName = entity.getLocation().getWorld() != null
                ? entity.getLocation().getWorld().getName()
                : "unknown";
        plugin.getLogger().log(Level.INFO,
                "[NPCManager] Registered NPC {0} ({1}) at {2}:{3},{4},{5}",
                new Object[] {
                        baseName,
                        entity.getType(),
                        worldName,
                        entity.getLocation().getBlockX(),
                        entity.getLocation().getBlockY(),
                        entity.getLocation().getBlockZ()
                });
    }

    private void unregisterNpc(Entity entity) {
        if (entity == null) {
            return;
        }
        spawnedNPCs.remove(entity);
        removeMarker(entity.getUniqueId());
    }

    private void applyAppearance(LivingEntity entity, String declaredName) {
        String baseName = declaredName != null && !declaredName.isBlank()
                ? declaredName
                : resolveName(entity);
        Component display = formatDisplay(baseName);
        entity.customName(display);
        entity.setCustomNameVisible(true);

        NpcSkin skin = findSkin(baseName);
        attachMarker(entity, display, skin);
    }

    private void refreshNpcAppearances() {
        spawnedNPCs.removeIf(entity -> entity == null || !entity.isValid());
        for (Entity entity : spawnedNPCs) {
            if (entity instanceof LivingEntity living) {
                applyAppearance(living, resolveName(living));
            }
        }
    }

    private boolean isTutorialWorld(Entity entity) {
        if (entity == null) {
            return false;
        }
        World world = entity.getWorld();
        if (world == null) {
            return false;
        }
        String worldName = world.getName();
        if (worldName == null) {
            return false;
        }
        return worldName.toLowerCase(Locale.ROOT).contains("tutorial");
    }

    private boolean isDuplicateTutorialNpc(String declaredName) {
        String canonical = normalize(declaredName);
        if (canonical.isEmpty()) {
            return false;
        }
        spawnedNPCs.removeIf(entity -> entity == null || !entity.isValid());
        for (Entity existing : spawnedNPCs) {
            if (!(existing instanceof LivingEntity living) || !living.isValid()) {
                continue;
            }
            if (!isTutorialWorld(existing)) {
                continue;
            }
            String existingName = normalize(resolveName(existing));
            if (!existingName.isEmpty() && existingName.equals(canonical)) {
                return true;
            }
        }
        return false;
    }

    private void attachMarker(LivingEntity entity, Component display, NpcSkin skin) {
        removeMarker(entity.getUniqueId());

        ArmorStand stand = entity.getWorld().spawn(entity.getLocation().add(0, entity.getHeight() + 0.25, 0),
                ArmorStand.class, spawned -> {
                    spawned.setInvisible(true);
                    spawned.setMarker(true);
                    spawned.setSmall(true);
                    spawned.setGravity(false);
                    spawned.setSilent(true);
                    spawned.setPersistent(false);
                    spawned.customName(display);
                    spawned.setCustomNameVisible(true);
                });

        ItemStack helmet = createPortrait(skin, display);
        if (helmet != null && stand.getEquipment() != null) {
            stand.getEquipment().setHelmet(helmet);
        }

        BukkitTask task = new BukkitRunnable() {
            @Override
            public void run() {
                if (!entity.isValid() || entity.isDead() || stand.isDead()) {
                    cancel();
                    stand.remove();
                    markers.remove(entity.getUniqueId());
                    return;
                }
                Location head = entity.getLocation().clone().add(0, entity.getHeight() + 0.25, 0);
                stand.teleport(head);
            }
        }.runTaskTimer(plugin, 1L, 5L);

        markers.put(entity.getUniqueId(), new MarkerHandle(stand, task));
    }

    private void removeMarker(UUID entityId) {
        MarkerHandle handle = markers.remove(entityId);
        if (handle != null) {
            handle.dispose();
        }
    }

    private Component formatDisplay(String baseName) {
        String reference = baseName;
        if (reference != null) {
            String stripped = ChatColor.stripColor(reference);
            if (stripped != null && !stripped.isBlank()) {
                reference = stripped.trim();
            }
        }

        String styled = reference;
        if (styled != null && NAMEPLATE_OVERRIDES.containsKey(styled)) {
            styled = NAMEPLATE_OVERRIDES.get(styled);
        }
        if (styled == null || styled.isBlank()) {
            styled = (reference != null && !reference.isBlank()) ? reference : "旅者";
        }

        String emotionKey = reference != null && !reference.isBlank() ? reference : baseName;
        EmotionProfile profile = emotionProfiles.get(normalize(emotionKey));
        if (profile != null) {
            String cue = !profile.label().isBlank() ? profile.label() : profile.tone();
            if (cue != null && !cue.isBlank()) {
                styled = styled + " · " + cue;
            }
        }
        return Component.text(styled, NamedTextColor.LIGHT_PURPLE);
    }

    private void registerSceneSkins(Map<String, Object> metadata) {
        List<Map<String, Object>> raw = extractSkinList(metadata);
        if (raw.isEmpty()) {
            return;
        }
        activeSkins.clear();
        for (Map<String, Object> entry : raw) {
            String id = asString(entry.get("id"));
            if (id.isBlank()) {
                continue;
            }
            String skinKey = asString(entry.get("skin"));
            activeSkins.put(normalize(id), new NpcSkin(id, skinKey));
        }
    }

    private void collectPendingNames(Map<String, Object> operations) {
        if (operations == null || operations.isEmpty()) {
            return;
        }
        walkOperations(operations);
    }

    private void walkOperations(Object candidate) {
        if (candidate instanceof Map<?, ?> map) {
            Map<String, Object> cast = castToStringMap(map);
            Object spawn = cast.get("spawn");
            if (spawn != null) {
                registerSpawnNames(spawn);
            }
            Object spawnMulti = cast.get("spawn_multi");
            if (spawnMulti != null) {
                registerSpawnNames(spawnMulti);
            }
            Object questEvents = cast.get("npc_trigger_events");
            if (questEvents != null) {
                collectNpcQuestEvents(questEvents);
            }
            for (Object value : cast.values()) {
                if (value instanceof Map<?, ?> || value instanceof List<?>) {
                    walkOperations(value);
                }
            }
        } else if (candidate instanceof List<?> list) {
            for (Object entry : list) {
                walkOperations(entry);
            }
        }
    }

    private void registerSpawnNames(Object candidate) {
        if (candidate instanceof Map<?, ?> map) {
            String name = asString(map.get("name"));
            if (!name.isBlank()) {
                pendingSpawns.put(normalize(name), System.currentTimeMillis() + PENDING_EXPIRY_MS);
            }
        } else if (candidate instanceof List<?> list) {
            for (Object entry : list) {
                registerSpawnNames(entry);
            }
        }
    }

    private List<Map<String, Object>> extractSkinList(Map<String, Object> metadata) {
        if (metadata == null) {
            return Collections.emptyList();
        }
        Object raw = metadata.get("npc_skins");
        if (!(raw instanceof List<?> list)) {
            return Collections.emptyList();
        }
        List<Map<String, Object>> result = new ArrayList<>();
        for (Object element : list) {
            if (element instanceof Map<?, ?> map) {
                result.add(castToStringMap(map));
            }
        }
        return result;
    }

    private void registerNpcQuestEvents(Map<String, Object> metadata, Map<String, Object> operations) {
        npcQuestTriggers.clear();
        if (metadata != null) {
            Object metaSpec = metadata.get("npc_triggers");
            if (metaSpec != null) {
                collectNpcQuestEvents(metaSpec);
            }
        }
        if (operations != null) {
            Object opSpec = operations.get("npc_trigger_events");
            if (opSpec != null) {
                collectNpcQuestEvents(opSpec);
            }
        }
    }

    private void collectNpcQuestEvents(Object candidate) {
        if (candidate instanceof Map<?, ?> map) {
            recordNpcQuestEvent(castToStringMap(map));
        } else if (candidate instanceof List<?> list) {
            for (Object entry : list) {
                collectNpcQuestEvents(entry);
            }
        }
    }

    private void recordNpcQuestEvent(Map<String, Object> spec) {
        if (spec == null || spec.isEmpty()) {
            return;
        }
        String npc = asString(spec.getOrDefault("npc", spec.get("id"))).trim();
        String questEvent = asString(spec.get("quest_event")).trim();
        if (npc.isBlank() || questEvent.isBlank()) {
            return;
        }
        String canonicalEvent = QuestEventCanonicalizer.canonicalize(questEvent);
        if (canonicalEvent.isEmpty()) {
            return;
        }
        npcQuestTriggers.put(normalize(npc), canonicalEvent);
    }

    public String lookupQuestEvent(Entity entity) {
        if (entity == null) {
            return "";
        }
        return lookupQuestEvent(resolveName(entity));
    }

    public String lookupQuestEvent(String npcName) {
        if (npcName == null) {
            return "";
        }
        return npcQuestTriggers.getOrDefault(normalize(npcName), "");
    }

    private Map<String, Object> castToStringMap(Map<?, ?> source) {
        Map<String, Object> result = new LinkedHashMap<>();
        for (Map.Entry<?, ?> entry : source.entrySet()) {
            if (entry.getKey() != null) {
                result.put(String.valueOf(entry.getKey()), entry.getValue());
            }
        }
        return result;
    }

    private NpcSkin findSkin(String baseName) {
        return activeSkins.get(normalize(baseName));
    }

    private ItemStack createPortrait(NpcSkin skin, Component display) {
        String owner = DEFAULT_SKIN_OWNER;
        if (skin != null) {
            String key = skinKeyBase(skin.skinKey());
            owner = SKIN_FALLBACK_PLAYERS.getOrDefault(key, DEFAULT_SKIN_OWNER);
        }
        ItemStack head = new ItemStack(Material.PLAYER_HEAD);
        SkullMeta meta = (SkullMeta) head.getItemMeta();
        if (meta != null) {
            OfflinePlayer offlineOwner = Bukkit.getOfflinePlayer(owner);
            meta.setOwningPlayer(offlineOwner);
            meta.displayName(display);
            head.setItemMeta(meta);
        }
        return head;
    }

    private String resolveName(Entity entity) {
        if (entity == null) {
            return "";
        }
        Component comp = entity.customName();
        if (comp != null) {
            return PlainTextComponentSerializer.plainText().serialize(comp);
        }
        String legacy = entity.getName();
        return legacy != null ? legacy : "";
    }

    private String normalize(String value) {
        if (value == null) {
            return "";
        }
        return value.replace("§", "").trim().toLowerCase(Locale.ROOT);
    }

    private String skinKeyBase(String skinKey) {
        if (skinKey == null) {
            return "";
        }
        String base = skinKey;
        int slash = base.lastIndexOf('/') + 1;
        if (slash > 0 && slash < base.length()) {
            base = base.substring(slash);
        }
        if (base.endsWith(".png")) {
            base = base.substring(0, base.length() - 4);
        }
        return base.toLowerCase(Locale.ROOT);
    }

    private String asString(Object value) {
        if (value == null) {
            return "";
        }
        if (value instanceof String s) {
            return s;
        }
        return String.valueOf(value);
    }

    private List<String> asStringList(Object value) {
        if (value == null) {
            return Collections.emptyList();
        }
        if (value instanceof List<?> list) {
            List<String> result = new ArrayList<>();
            for (Object element : list) {
                String str = asString(element).trim();
                if (!str.isEmpty()) {
                    result.add(str);
                }
            }
            return result;
        }
        String single = asString(value).trim();
        if (single.isEmpty()) {
            return Collections.emptyList();
        }
        return List.of(single);
    }

    private record NpcSkin(String id, String skinKey) {
    }

    private record EmotionProfile(String label, String tone, long appliedAt) {
    }

    private static final class MarkerHandle {
        private final ArmorStand stand;
        private final BukkitTask task;

        MarkerHandle(ArmorStand stand, BukkitTask task) {
            this.stand = stand;
            this.task = task;
        }

        void dispose() {
            if (task != null) {
                task.cancel();
            }
            if (stand != null && !stand.isDead()) {
                stand.remove();
            }
        }
    }
}