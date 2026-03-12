package com.driftmc.world;

import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.security.NoSuchAlgorithmException;
import java.util.ArrayList;
import java.util.Collections;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Locale;
import java.util.Map;
import java.util.UUID;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.CopyOnWriteArrayList;

import org.bukkit.Bukkit;
import org.bukkit.ChatColor;
import org.bukkit.Location;
import org.bukkit.Material;
import org.bukkit.Particle;
import org.bukkit.Sound;
import org.bukkit.SoundCategory;
import org.bukkit.World;
import org.bukkit.attribute.Attribute;
import org.bukkit.entity.Entity;
import org.bukkit.entity.EntityType;
import org.bukkit.entity.LivingEntity;
import org.bukkit.entity.Player;
import org.bukkit.plugin.java.JavaPlugin;
import org.bukkit.potion.PotionEffect;
import org.bukkit.potion.PotionEffectType;
import org.bukkit.scheduler.BukkitTask;

import com.driftmc.backend.BackendClient;
import com.driftmc.scene.QuestEventCanonicalizer;
import com.driftmc.scene.RuleEventBridge;
import com.google.gson.Gson;
import com.google.gson.JsonObject;

import okhttp3.Call;
import okhttp3.Callback;
import okhttp3.Response;

/**
 * WorldPatchExecutor
 *
 * 心悦宇宙 · 完整稳定版执行器（含 SafeTeleport v3）
 *
 * 统一执行来自后端的 world_patch / mc_patch：
 *
 * 支持 key：
 * tell / weather / time / teleport / build / spawn
 * effect / particle / sound / title / actionbar
 */
public class WorldPatchExecutor {

    private static final Gson GSON = new Gson();

    private final JavaPlugin plugin;
    private AdvancedWorldBuilder advancedBuilder;
    private RuleEventBridge ruleEventBridge;
    private final Map<UUID, CopyOnWriteArrayList<LocationTrigger>> triggerRegistry = new ConcurrentHashMap<>();
    private BukkitTask triggerPoller;
    private volatile BackendClient backend;

    public WorldPatchExecutor(JavaPlugin plugin) {
        this.plugin = plugin;
        this.advancedBuilder = new AdvancedWorldBuilder(plugin, this);
    }

    public JavaPlugin getPlugin() {
        return this.plugin;
    }

    public void setRuleEventBridge(RuleEventBridge bridge) {
        this.ruleEventBridge = bridge;
    }

    public RuleEventBridge getRuleEventBridge() {
        return this.ruleEventBridge;
    }

    public void setBackendClient(BackendClient backend) {
        this.backend = backend;
    }

    /**
     * Hook for subclasses to inject featured NPC behavior during scene patches.
     * Default implementation is a no-op.
     */
    public void ensureFeaturedNpc(Player player, Map<String, Object> metadata, Map<String, Object> operations) {
        // intentionally empty
    }

    public void shutdown() {
        if (triggerPoller != null) {
            triggerPoller.cancel();
            triggerPoller = null;
        }
        triggerRegistry.clear();
    }

    // =============================== 核心入口 ===============================
    public void execute(Player player, Map<String, Object> patch) {
        if (player == null || patch == null || patch.isEmpty()) {
            return;
        }

        final Map<String, Object> patchFinal = patch;

        // —— 异步切回主线程（纸片人保护）——
        if (!Bukkit.isPrimaryThread()) {
            Bukkit.getScheduler().runTask(plugin, () -> execute(player, patchFinal));
            return;
        }

        long startedAtMs = System.currentTimeMillis();
        String buildId = extractBuildId(patch);
        String payloadHash = extractPayloadHash(patch, buildId);
        if (payloadHash == null || payloadHash.isBlank() || "unknown".equalsIgnoreCase(payloadHash)) {
            payloadHash = computePayloadDigest(patch);
        }
        String reportBuildId = resolveReportBuildId(buildId, payloadHash, player.getName(), startedAtMs);
        String status = "EXECUTED";
        String failureCode = "NONE";
        int failed = 0;

        try {
            plugin.getLogger().info("[WorldPatchExecutor] execute patch = " + patch);

            Map<String, Object> primary = patch;
            processOperationMap(player, primary);

            Object mcObj = patch.get("mc");

            if (mcObj instanceof Map) {
                Map<String, Object> mcMap = asStringObjectMap(mcObj);
                processOperationMap(player, mcMap);
            } else if (mcObj instanceof List) {
                List<?> mcList = (List<?>) mcObj;
                for (Object entry : mcList) {
                    if (entry instanceof Map) {
                        Map<String, Object> entryMap = asStringObjectMap(entry);
                        processOperationMap(player, entryMap);
                    }
                }
            }
        } catch (RuntimeException ex) {
            status = "REJECTED";
            failureCode = "EXEC_EXCEPTION";
            failed = 1;
            plugin.getLogger().warning("[WorldPatchExecutor] execute failed build_id="
                    + (reportBuildId == null ? "<none>" : reportBuildId)
                    + " player=" + player.getName()
                    + " error=" + ex.getMessage());
            throw ex;
        } finally {
            int executed = "EXECUTED".equals(status) ? estimateOperationCount(patch) : 0;
            long durationMs = Math.max(0L, System.currentTimeMillis() - startedAtMs);
            reportApplyResult(reportBuildId, player.getName(), status, failureCode, executed, failed, durationMs, payloadHash);
        }
    }

    private String resolveReportBuildId(String buildId, String payloadHash, String playerId, long startedAtMs) {
        if (buildId != null && !buildId.isBlank()) {
            return buildId;
        }
        if (payloadHash != null && !payloadHash.isBlank() && !"unknown".equalsIgnoreCase(payloadHash)) {
            return "mc_auto_" + payloadHash;
        }
        String safePlayer = playerId == null || playerId.isBlank() ? "unknown" : playerId;
        return "mc_auto_" + safePlayer + "_" + startedAtMs;
    }

    private String computePayloadDigest(Map<String, Object> patch) {
        if (patch == null || patch.isEmpty()) {
            return "unknown";
        }
        try {
            MessageDigest digest = MessageDigest.getInstance("SHA-256");
            byte[] bytes = GSON.toJson(patch).getBytes(StandardCharsets.UTF_8);
            byte[] hash = digest.digest(bytes);
            StringBuilder sb = new StringBuilder(hash.length * 2);
            for (byte b : hash) {
                sb.append(String.format("%02x", b));
            }
            return sb.toString();
        } catch (NoSuchAlgorithmException ex) {
            return "unknown";
        }
    }

    private int estimateOperationCount(Map<String, Object> patch) {
        if (patch == null || patch.isEmpty()) {
            return 0;
        }

        int total = countOperationMap(patch);
        Object mcObj = patch.get("mc");
        if (mcObj instanceof Map<?, ?> mcMap) {
            total += countOperationMap(asStringObjectMap(mcMap));
        } else if (mcObj instanceof List<?> mcList) {
            for (Object entry : mcList) {
                if (entry instanceof Map<?, ?> entryMap) {
                    total += countOperationMap(asStringObjectMap(entryMap));
                }
            }
        }
        return Math.max(1, total);
    }

    private int countOperationMap(Map<String, Object> operations) {
        if (operations == null || operations.isEmpty()) {
            return 0;
        }

        int count = 0;
        count += countKeyWeight(operations.get("tell"));
        count += countKeyWeight(operations.get("weather"));
        count += countKeyWeight(operations.get("weather_transition"));
        count += countKeyWeight(operations.get("time"));
        count += countKeyWeight(operations.get("lighting_shift"));
        count += countKeyWeight(operations.get("music"));
        count += countKeyWeight(operations.get("teleport"));
        count += countKeyWeight(operations.get("trigger_zones"));
        count += countKeyWeight(operations.get("build"));
        count += countKeyWeight(operations.get("build_multi"));
        count += countKeyWeight(operations.get("spawn"));
        count += countKeyWeight(operations.get("spawn_multi"));
        count += countKeyWeight(operations.get("structure"));
        count += countKeyWeight(operations.get("blocks"));
        count += countKeyWeight(operations.get("effect"));
        count += countKeyWeight(operations.get("particle"));
        count += countKeyWeight(operations.get("sound"));
        count += countKeyWeight(operations.get("title"));
        count += countKeyWeight(operations.get("actionbar"));
        return count;
    }

    private int countKeyWeight(Object value) {
        if (value == null) {
            return 0;
        }
        if (value instanceof List<?> list) {
            return Math.max(1, list.size());
        }
        return 1;
    }

    private String extractBuildId(Map<String, Object> patch) {
        String rootBuildId = asNonBlankString(patch.get("build_id"));
        if (rootBuildId != null) {
            return rootBuildId;
        }

        Object mcObj = patch.get("mc");
        if (mcObj instanceof Map<?, ?> mcMap) {
            return asNonBlankString(mcMap.get("build_id"));
        }
        return null;
    }

    private String extractPayloadHash(Map<String, Object> patch, String fallbackBuildId) {
        String direct = asNonBlankString(patch.get("final_commands_hash_v2"));
        if (direct != null) {
            return direct;
        }

        Object hashObj = patch.get("hash");
        if (hashObj instanceof Map<?, ?> hashMap) {
            String merged = asNonBlankString(hashMap.get("final_commands"));
            if (merged != null) {
                return merged;
            }
            merged = asNonBlankString(hashMap.get("merged_blocks"));
            if (merged != null) {
                return merged;
            }
        }

        Object mcObj = patch.get("mc");
        if (mcObj instanceof Map<?, ?> mcMap) {
            String mcHash = asNonBlankString(mcMap.get("final_commands_hash_v2"));
            if (mcHash != null) {
                return mcHash;
            }
        }

        return fallbackBuildId == null || fallbackBuildId.isBlank() ? "unknown" : fallbackBuildId;
    }

    private String asNonBlankString(Object value) {
        if (value == null) {
            return null;
        }
        String text = String.valueOf(value).trim();
        return text.isEmpty() ? null : text;
    }

    private void reportApplyResult(
            String buildId,
            String playerId,
            String status,
            String failureCode,
            int executed,
            int failed,
            long durationMs,
            String payloadHash) {
        if (backend == null || buildId == null || buildId.isBlank()) {
            return;
        }

        JsonObject report = new JsonObject();
        report.addProperty("build_id", buildId);
        report.addProperty("player_id", playerId == null || playerId.isBlank() ? "unknown" : playerId);
        report.addProperty("status", status == null || status.isBlank() ? "EXECUTED" : status);
        report.addProperty("failure_code", failureCode == null || failureCode.isBlank() ? "NONE" : failureCode);
        report.addProperty("executed", Math.max(0, executed));
        report.addProperty("failed", Math.max(0, failed));
        report.addProperty("duration_ms", Math.max(0L, durationMs));
        report.addProperty("payload_hash", payloadHash == null || payloadHash.isBlank() ? buildId : payloadHash);

        backend.postJsonAsync("/world/apply/report", GSON.toJson(report), new Callback() {
            @Override
            public void onFailure(Call call, java.io.IOException e) {
                plugin.getLogger().warning("[WorldPatchExecutor] apply report failed build_id="
                        + buildId + " error=" + e.getMessage());
            }

            @Override
            public void onResponse(Call call, Response response) {
                try (response) {
                    if (!response.isSuccessful()) {
                        plugin.getLogger().warning("[WorldPatchExecutor] apply report non-2xx build_id="
                                + buildId + " code=" + response.code());
                    }
                }
            }
        });
    }

    @SuppressWarnings("unchecked")
    private void processOperationMap(Player player, Map<String, Object> operations) {
        if (operations == null || operations.isEmpty()) {
            return;
        }

        // tell
        handleTell(player, operations.get("tell"));

        // weather
        if (operations.containsKey("weather")) {
            handleWeather(player, string(operations.get("weather"), "clear"));
        }

        if (operations.containsKey("weather_transition")) {
            Object transitionObj = operations.get("weather_transition");
            if (transitionObj instanceof Map<?, ?> map) {
                handleWeatherTransition(player, (Map<String, Object>) map);
            } else {
                handleWeather(player, string(transitionObj, "clear"));
            }
        }

        // time
        if (operations.containsKey("time")) {
            handleTime(player, string(operations.get("time"), "day"));
        }

        if (operations.containsKey("lighting_shift")) {
            handleLightingShift(player, operations.get("lighting_shift"));
        }

        if (operations.containsKey("music")) {
            handleMusic(player, operations.get("music"));
        }

        Map<String, Object> teleportConfig = null;
        Location teleportTarget = null;
        if (operations.containsKey("teleport")) {
            Object tpObj = operations.get("teleport");
            if (tpObj instanceof Map<?, ?> tpRaw) {
                teleportConfig = (Map<String, Object>) tpRaw;
                teleportTarget = calculateSafeTeleportTarget(player, teleportConfig);
            }
        }

        Location anchorLocation = teleportTarget != null
                ? teleportTarget.clone()
                : player.getLocation().clone();

        if (operations.containsKey("trigger_zones")) {
            handleTriggerZones(player, operations.get("trigger_zones"), anchorLocation);
        }

        if (operations.containsKey("_scene_cleanup") && player != null) {
            clearPlayerTriggers(player.getUniqueId());
        }

        // build
        if (operations.containsKey("build")) {
            Object buildObj = operations.get("build");
            if (buildObj instanceof Map<?, ?> bRaw) {
                Map<String, Object> buildMap = asStringObjectMap(bRaw);
                if (!buildMap.isEmpty()) {
                    handleBuild(player, buildMap, anchorLocation);
                }
            } else if (buildObj instanceof List<?> buildList) {
                for (Object entry : (List<?>) buildList) {
                    if (entry instanceof Map<?, ?> entryRaw) {
                        Map<String, Object> entryMap = asStringObjectMap(entryRaw);
                        if (!entryMap.isEmpty()) {
                            handleBuild(player, entryMap, anchorLocation);
                        }
                    }
                }
            }
        }

        // build_multi（批量构建）
        boolean buildMultiHandled = false;
        if (operations.containsKey("build_multi")) {
            buildMultiHandled = handleBuildMultiEntries(player, operations.get("build_multi"), anchorLocation);
        }

        // structure（模板构建，若 build_multi 已处理则跳过避免重复）
        if (operations.containsKey("structure") && !buildMultiHandled) {
            handleStructureEntries(player, operations.get("structure"), anchorLocation);
        }

        // blocks（离散方块放置）
        if (operations.containsKey("blocks")) {
            handleBlocks(player, operations.get("blocks"), anchorLocation);
        }

        // spawn
        if (operations.containsKey("spawn")) {
            Object spawnObj = operations.get("spawn");
            if (spawnObj instanceof Map<?, ?> sRaw) {
                handleSpawn(player, (Map<String, Object>) sRaw, anchorLocation);
            } else if (spawnObj instanceof List<?> spawnList) {
                for (Object entry : (List<?>) spawnList) {
                    if (entry instanceof Map<?, ?> entryMap) {
                        handleSpawn(player, (Map<String, Object>) entryMap, anchorLocation);
                    }
                }
            }
        }

        // spawn_multi（批量生成实体）
        if (operations.containsKey("spawn_multi")) {
            handleSpawnMultiEntries(player, operations.get("spawn_multi"), anchorLocation);
        }

        // spawns（旧别名，兼容 AI world fallback）
        if (operations.containsKey("spawns")) {
            handleSpawnMultiEntries(player, operations.get("spawns"), anchorLocation);
        }

        if (teleportConfig != null && teleportTarget != null) {
            performTeleport(player, teleportConfig, teleportTarget);
        }

        // effect
        if (operations.containsKey("effect")) {
            Object effObj = operations.get("effect");
            if (effObj instanceof Map<?, ?> effRaw) {
                handleEffect(player, (Map<String, Object>) effRaw);
            }
        }

        // particle
        if (operations.containsKey("particle")) {
            Object pObj = operations.get("particle");
            if (pObj instanceof Map<?, ?> pRaw) {
                handleParticle(player, (Map<String, Object>) pRaw);
            }
        }

        // sound
        if (operations.containsKey("sound")) {
            Object sObj = operations.get("sound");
            if (sObj instanceof Map<?, ?> sRaw) {
                handleSound(player, (Map<String, Object>) sRaw);
            }
        }

        // title
        if (operations.containsKey("title")) {
            Object tObj = operations.get("title");
            if (tObj instanceof Map<?, ?> tRaw) {
                handleTitle(player, (Map<String, Object>) tRaw);
            }
        }

        // actionbar
        if (operations.containsKey("actionbar")) {
            Object abObj = operations.get("actionbar");
            if (abObj instanceof String abStr) {
                handleActionBar(player, abStr);
            }
        }
    }

    private boolean handleBuildMultiEntries(Player player, Object spec, Location anchor) {
        List<Map<String, Object>> entries = asOperationEntryList(spec);
        if (entries.isEmpty()) {
            return false;
        }

        List<Map<String, Object>> advancedEntries = new ArrayList<>();
        boolean executed = false;

        for (Map<String, Object> entry : entries) {
            if (isAdvancedBuildEntry(entry)) {
                advancedEntries.add(entry);
                continue;
            }
            handleBuild(player, entry, anchor);
            executed = true;
        }

        if (!advancedEntries.isEmpty()) {
            advancedBuilder.handleBuildMulti(player, advancedEntries, anchor);
            executed = true;
        }

        return executed;
    }

    private boolean isAdvancedBuildEntry(Map<String, Object> buildMap) {
        if (buildMap == null || buildMap.isEmpty()) {
            return false;
        }

        String shape = string(buildMap.get("shape"), "").toLowerCase(Locale.ROOT);
        switch (shape) {
            case "race_track", "hollow_cube", "grid", "fence_ring", "tunnel", "light_line" -> {
                return true;
            }
            default -> {
            }
        }

        return buildMap.get("center") instanceof Map<?, ?>
                || buildMap.get("start") instanceof Map<?, ?>
                || buildMap.get("end") instanceof Map<?, ?>;
    }

    private void handleStructureEntries(Player player, Object spec, Location anchor) {
        List<Map<String, Object>> entries = asOperationEntryList(spec);
        for (Map<String, Object> entry : entries) {
            handleStructure(player, entry, anchor);
        }
    }

    private void handleStructure(Player player, Map<String, Object> structureMap, Location anchor) {
        String template = string(
                structureMap.get("template"),
                string(structureMap.get("name"), string(structureMap.get("structure_type"), "camp_small")))
                .toLowerCase(Locale.ROOT);

        double[] baseOffset = resolveOffset(structureMap);
        String worldName = string(structureMap.get("world"), "");

        switch (template) {
            case "camp_small" -> {
                handleBuild(player, buildSpec("platform", 2, "OAK_PLANKS", worldName,
                        baseOffset[0], baseOffset[1], baseOffset[2]), anchor);
                handleBuild(player, buildSpec("line", 2, "OAK_FENCE", worldName,
                        baseOffset[0] - 1.0, baseOffset[1], baseOffset[2] - 1.0), anchor);
            }
            case "campfire_small", "campfire" -> {
            handleBuild(player, buildSpec("line", 1, "CAMPFIRE", worldName,
                baseOffset[0], baseOffset[1], baseOffset[2]), anchor);
            handleBuild(player, buildSpec("line", 1, "OAK_LOG", worldName,
                baseOffset[0] + 1.0, baseOffset[1], baseOffset[2]), anchor);
            }
            case "tent_basic", "tent" -> {
            handleBuild(player, buildSpec("house", 2, "OAK_PLANKS", worldName,
                baseOffset[0], baseOffset[1], baseOffset[2]), anchor);
            handleBuild(player, buildSpec("line", 2, "WHITE_WOOL", worldName,
                baseOffset[0], baseOffset[1] + 2.0, baseOffset[2]), anchor);
            }
            case "crate_supply", "supply_crate" -> {
            handleBuild(player, buildSpec("line", 1, "BARREL", worldName,
                baseOffset[0], baseOffset[1], baseOffset[2]), anchor);
            handleBuild(player, buildSpec("line", 1, "CHEST", worldName,
                baseOffset[0] + 1.0, baseOffset[1], baseOffset[2]), anchor);
            }
            case "cooking_area_basic" -> {
                handleBuild(player, buildSpec("line", 2, "COBBLESTONE", worldName,
                        baseOffset[0], baseOffset[1], baseOffset[2]), anchor);
                handleBuild(player, buildSpec("line", 1, "FURNACE", worldName,
                        baseOffset[0] + 1.0, baseOffset[1], baseOffset[2]), anchor);
            }
            case "market_stalls", "market_stall" -> {
            handleBuild(player, buildSpec("platform", 1, "OAK_PLANKS", worldName,
                baseOffset[0], baseOffset[1], baseOffset[2]), anchor);
            handleBuild(player, buildSpec("line", 3, "OAK_FENCE", worldName,
                baseOffset[0] - 1.0, baseOffset[1], baseOffset[2]), anchor);
            handleBuild(player, buildSpec("line", 3, "RED_WOOL", worldName,
                baseOffset[0] - 1.0, baseOffset[1] + 1.0, baseOffset[2]), anchor);
            handleBuild(player, buildSpec("line", 1, "BARREL", worldName,
                baseOffset[0] + 1.0, baseOffset[1], baseOffset[2] + 1.0), anchor);
            }
            case "merchant_cart", "trader_cart" -> {
            handleBuild(player, buildSpec("platform", 1, "OAK_PLANKS", worldName,
                baseOffset[0], baseOffset[1], baseOffset[2]), anchor);
            handleBuild(player, buildSpec("line", 1, "BARREL", worldName,
                baseOffset[0] + 1.0, baseOffset[1], baseOffset[2]), anchor);
            handleBuild(player, buildSpec("line", 1, "CHEST", worldName,
                baseOffset[0] - 1.0, baseOffset[1], baseOffset[2]), anchor);
            }
            case "food_stand", "street_food" -> {
            handleBuild(player, buildSpec("platform", 1, "OAK_PLANKS", worldName,
                baseOffset[0], baseOffset[1], baseOffset[2]), anchor);
            handleBuild(player, buildSpec("line", 1, "SMOKER", worldName,
                baseOffset[0] + 1.0, baseOffset[1], baseOffset[2]), anchor);
            handleBuild(player, buildSpec("line", 1, "BARREL", worldName,
                baseOffset[0] - 1.0, baseOffset[1], baseOffset[2]), anchor);
            }
            case "village_core", "village_center" -> {
            handleBuild(player, buildSpec("platform", 3, "SMOOTH_STONE", worldName,
                baseOffset[0], baseOffset[1], baseOffset[2]), anchor);
            handleBuild(player, buildSpec("line", 2, "LANTERN", worldName,
                baseOffset[0] - 1.0, baseOffset[1] + 1.0, baseOffset[2]), anchor);
            }
            case "village_plaza_small", "village_plaza" -> {
            handleBuild(player, buildSpec("platform", 2, "STONE_BRICKS", worldName,
                baseOffset[0], baseOffset[1], baseOffset[2]), anchor);
            handleBuild(player, buildSpec("line", 2, "OAK_FENCE", worldName,
                baseOffset[0], baseOffset[1], baseOffset[2] + 2.0), anchor);
            }
            case "village_house_basic", "village_house" -> {
            handleBuild(player, buildSpec("house", 3, "OAK_PLANKS", worldName,
                baseOffset[0], baseOffset[1], baseOffset[2]), anchor);
            }
            case "forge_basic", "forge" -> {
            handleBuild(player, buildSpec("platform", 1, "COBBLESTONE", worldName,
                baseOffset[0], baseOffset[1], baseOffset[2]), anchor);
            handleBuild(player, buildSpec("line", 1, "ANVIL", worldName,
                baseOffset[0] + 1.0, baseOffset[1], baseOffset[2]), anchor);
            handleBuild(player, buildSpec("line", 1, "FURNACE", worldName,
                baseOffset[0] - 1.0, baseOffset[1], baseOffset[2]), anchor);
            }
            case "anvil_station", "smith_anvil" -> {
            handleBuild(player, buildSpec("platform", 1, "STONE_BRICKS", worldName,
                baseOffset[0], baseOffset[1], baseOffset[2]), anchor);
            handleBuild(player, buildSpec("line", 1, "ANVIL", worldName,
                baseOffset[0], baseOffset[1], baseOffset[2] + 1.0), anchor);
            }
            case "smelter", "smelter_basic" -> {
            handleBuild(player, buildSpec("platform", 1, "COBBLESTONE", worldName,
                baseOffset[0], baseOffset[1], baseOffset[2]), anchor);
            handleBuild(player, buildSpec("line", 1, "BLAST_FURNACE", worldName,
                baseOffset[0], baseOffset[1], baseOffset[2] - 1.0), anchor);
            }
            case "ore_pile", "ore_stack" -> {
            handleBuild(player, buildSpec("line", 2, "STONE", worldName,
                baseOffset[0], baseOffset[1], baseOffset[2]), anchor);
            handleBuild(player, buildSpec("line", 1, "IRON_BLOCK", worldName,
                baseOffset[0] + 1.0, baseOffset[1] + 1.0, baseOffset[2]), anchor);
            }
            case "farm_plot", "farm_patch" -> {
            handleBuild(player, buildSpec("platform", 2, "FARMLAND", worldName,
                baseOffset[0], baseOffset[1], baseOffset[2]), anchor);
            handleBuild(player, buildSpec("line", 2, "WHEAT", worldName,
                baseOffset[0] - 1.0, baseOffset[1] + 1.0, baseOffset[2]), anchor);
            }
            case "mine_core", "mine" -> {
            handleBuild(player, buildSpec("platform", 2, "COBBLESTONE", worldName,
                baseOffset[0], baseOffset[1], baseOffset[2]), anchor);
            handleBuild(player, buildSpec("line", 2, "RAIL", worldName,
                baseOffset[0], baseOffset[1] + 1.0, baseOffset[2]), anchor);
            handleBuild(player, buildSpec("line", 1, "IRON_BLOCK", worldName,
                baseOffset[0] - 1.0, baseOffset[1], baseOffset[2]), anchor);
            handleBuild(player, buildSpec("line", 1, "LANTERN", worldName,
                baseOffset[0] + 1.0, baseOffset[1] + 1.0, baseOffset[2]), anchor);
            }
            case "dock_pier", "dock" -> {
            handleBuild(player, buildSpec("platform", 3, "OAK_PLANKS", worldName,
                baseOffset[0], baseOffset[1], baseOffset[2]), anchor);
            handleBuild(player, buildSpec("line", 3, "OAK_LOG", worldName,
                baseOffset[0], baseOffset[1], baseOffset[2] + 2.0), anchor);
            handleBuild(player, buildSpec("line", 2, "BARREL", worldName,
                baseOffset[0] - 1.0, baseOffset[1], baseOffset[2] + 1.0), anchor);
            handleBuild(player, buildSpec("line", 2, "LANTERN", worldName,
                baseOffset[0] + 1.0, baseOffset[1] + 1.0, baseOffset[2]), anchor);
            }
            case "library_hall", "library" -> {
            handleBuild(player, buildSpec("house", 3, "OAK_PLANKS", worldName,
                baseOffset[0], baseOffset[1], baseOffset[2]), anchor);
            handleBuild(player, buildSpec("line", 2, "BOOKSHELF", worldName,
                baseOffset[0], baseOffset[1], baseOffset[2] + 1.0), anchor);
            handleBuild(player, buildSpec("line", 1, "LECTERN", worldName,
                baseOffset[0] + 1.0, baseOffset[1], baseOffset[2]), anchor);
            handleBuild(player, buildSpec("line", 1, "LANTERN", worldName,
                baseOffset[0], baseOffset[1] + 2.0, baseOffset[2]), anchor);
            }
            case "temple_court", "temple" -> {
            handleBuild(player, buildSpec("platform", 3, "STONE_BRICKS", worldName,
                baseOffset[0], baseOffset[1], baseOffset[2]), anchor);
            handleBuild(player, buildSpec("line", 2, "CHISELED_STONE_BRICKS", worldName,
                baseOffset[0], baseOffset[1], baseOffset[2] + 2.0), anchor);
            handleBuild(player, buildSpec("line", 2, "SOUL_LANTERN", worldName,
                baseOffset[0] - 1.0, baseOffset[1] + 1.0, baseOffset[2]), anchor);
            handleBuild(player, buildSpec("line", 1, "CAMPFIRE", worldName,
                baseOffset[0] + 1.0, baseOffset[1], baseOffset[2]), anchor);
            }
            case "arena_ring", "arena" -> {
            handleBuild(player, buildSpec("platform", 3, "SMOOTH_STONE", worldName,
                baseOffset[0], baseOffset[1], baseOffset[2]), anchor);
            handleBuild(player, buildSpec("line", 4, "OAK_FENCE", worldName,
                baseOffset[0] - 2.0, baseOffset[1], baseOffset[2]), anchor);
            handleBuild(player, buildSpec("line", 2, "TORCH", worldName,
                baseOffset[0], baseOffset[1] + 1.0, baseOffset[2] + 2.0), anchor);
            }
            case "inn_lodge", "inn" -> {
            handleBuild(player, buildSpec("house", 3, "SPRUCE_PLANKS", worldName,
                baseOffset[0], baseOffset[1], baseOffset[2]), anchor);
            handleBuild(player, buildSpec("line", 2, "BARREL", worldName,
                baseOffset[0] - 1.0, baseOffset[1], baseOffset[2]), anchor);
            handleBuild(player, buildSpec("line", 1, "CAMPFIRE", worldName,
                baseOffset[0] + 1.0, baseOffset[1], baseOffset[2] + 1.0), anchor);
            handleBuild(player, buildSpec("line", 1, "LANTERN", worldName,
                baseOffset[0], baseOffset[1] + 2.0, baseOffset[2]), anchor);
            }
            case "workshop_floor", "workshop" -> {
            handleBuild(player, buildSpec("platform", 2, "OAK_PLANKS", worldName,
                baseOffset[0], baseOffset[1], baseOffset[2]), anchor);
            handleBuild(player, buildSpec("line", 2, "CRAFTING_TABLE", worldName,
                baseOffset[0] - 1.0, baseOffset[1], baseOffset[2]), anchor);
            handleBuild(player, buildSpec("line", 1, "ANVIL", worldName,
                baseOffset[0] + 1.0, baseOffset[1], baseOffset[2]), anchor);
            handleBuild(player, buildSpec("line", 1, "BLAST_FURNACE", worldName,
                baseOffset[0], baseOffset[1], baseOffset[2] - 1.0), anchor);
            }
            case "warehouse_stack", "warehouse" -> {
            handleBuild(player, buildSpec("house", 3, "OAK_PLANKS", worldName,
                baseOffset[0], baseOffset[1], baseOffset[2]), anchor);
            handleBuild(player, buildSpec("line", 3, "BARREL", worldName,
                baseOffset[0] + 1.0, baseOffset[1], baseOffset[2]), anchor);
            handleBuild(player, buildSpec("line", 2, "CHEST", worldName,
                baseOffset[0] - 1.0, baseOffset[1], baseOffset[2] + 1.0), anchor);
            handleBuild(player, buildSpec("line", 2, "OAK_LOG", worldName,
                baseOffset[0], baseOffset[1], baseOffset[2] - 2.0), anchor);
            }
            case "trade_post_stall", "trade_post" -> {
            handleBuild(player, buildSpec("platform", 2, "OAK_PLANKS", worldName,
                baseOffset[0], baseOffset[1], baseOffset[2]), anchor);
            handleBuild(player, buildSpec("line", 3, "OAK_FENCE", worldName,
                baseOffset[0] - 1.0, baseOffset[1], baseOffset[2]), anchor);
            handleBuild(player, buildSpec("line", 2, "YELLOW_WOOL", worldName,
                baseOffset[0] - 1.0, baseOffset[1] + 1.0, baseOffset[2]), anchor);
            handleBuild(player, buildSpec("line", 1, "CHEST", worldName,
                baseOffset[0] + 1.0, baseOffset[1], baseOffset[2]), anchor);
            handleBuild(player, buildSpec("line", 1, "BARREL", worldName,
                baseOffset[0] + 1.0, baseOffset[1], baseOffset[2] + 1.0), anchor);
            }
            case "fishing_hut", "fishing_hut_small" -> {
            handleBuild(player, buildSpec("house", 2, "SPRUCE_PLANKS", worldName,
                baseOffset[0], baseOffset[1], baseOffset[2]), anchor);
            handleBuild(player, buildSpec("line", 2, "BARREL", worldName,
                baseOffset[0] - 1.0, baseOffset[1], baseOffset[2]), anchor);
            handleBuild(player, buildSpec("line", 1, "CAMPFIRE", worldName,
                baseOffset[0] + 1.0, baseOffset[1], baseOffset[2]), anchor);
            handleBuild(player, buildSpec("line", 2, "BLUE_WOOL", worldName,
                baseOffset[0], baseOffset[1], baseOffset[2] + 2.0), anchor);
            handleBuild(player, buildSpec("line", 1, "LANTERN", worldName,
                baseOffset[0], baseOffset[1] + 1.0, baseOffset[2]), anchor);
            }
            case "mine_shaft_tunnel", "mine_shaft" -> {
            handleBuild(player, buildSpec("platform", 2, "COBBLESTONE", worldName,
                baseOffset[0], baseOffset[1], baseOffset[2]), anchor);
            handleBuild(player, buildSpec("line", 3, "RAIL", worldName,
                baseOffset[0], baseOffset[1] + 1.0, baseOffset[2]), anchor);
            handleBuild(player, buildSpec("line", 2, "OAK_LOG", worldName,
                baseOffset[0], baseOffset[1], baseOffset[2] + 1.0), anchor);
            handleBuild(player, buildSpec("line", 1, "LANTERN", worldName,
                baseOffset[0] + 1.0, baseOffset[1] + 2.0, baseOffset[2]), anchor);
            }
            case "ore_sorting_yard" -> {
            handleBuild(player, buildSpec("platform", 2, "STONE", worldName,
                baseOffset[0], baseOffset[1], baseOffset[2]), anchor);
            handleBuild(player, buildSpec("line", 2, "IRON_BLOCK", worldName,
                baseOffset[0] + 1.0, baseOffset[1] + 1.0, baseOffset[2]), anchor);
            handleBuild(player, buildSpec("line", 1, "BLAST_FURNACE", worldName,
                baseOffset[0] - 1.0, baseOffset[1], baseOffset[2]), anchor);
            handleBuild(player, buildSpec("line", 1, "CHEST", worldName,
                baseOffset[0], baseOffset[1], baseOffset[2] + 1.0), anchor);
            }
            case "dock_mooring_post" -> {
            handleBuild(player, buildSpec("line", 3, "OAK_LOG", worldName,
                baseOffset[0], baseOffset[1], baseOffset[2]), anchor);
            handleBuild(player, buildSpec("line", 2, "CHAIN", worldName,
                baseOffset[0] + 1.0, baseOffset[1] + 1.0, baseOffset[2]), anchor);
            handleBuild(player, buildSpec("line", 1, "LANTERN", worldName,
                baseOffset[0] + 1.0, baseOffset[1] + 2.0, baseOffset[2]), anchor);
            handleBuild(player, buildSpec("line", 1, "BARREL", worldName,
                baseOffset[0] - 1.0, baseOffset[1], baseOffset[2]), anchor);
            }
            case "dock_net_dryer" -> {
            handleBuild(player, buildSpec("platform", 1, "SPRUCE_PLANKS", worldName,
                baseOffset[0], baseOffset[1], baseOffset[2]), anchor);
            handleBuild(player, buildSpec("line", 2, "OAK_FENCE", worldName,
                baseOffset[0], baseOffset[1], baseOffset[2] + 1.0), anchor);
            handleBuild(player, buildSpec("line", 2, "WHITE_WOOL", worldName,
                baseOffset[0], baseOffset[1] + 1.0, baseOffset[2] + 1.0), anchor);
            handleBuild(player, buildSpec("line", 1, "BARREL", worldName,
                baseOffset[0] + 1.0, baseOffset[1], baseOffset[2]), anchor);
            }
            case "library_archive_stacks" -> {
            handleBuild(player, buildSpec("house", 2, "OAK_PLANKS", worldName,
                baseOffset[0], baseOffset[1], baseOffset[2]), anchor);
            handleBuild(player, buildSpec("line", 3, "BOOKSHELF", worldName,
                baseOffset[0], baseOffset[1], baseOffset[2] + 1.0), anchor);
            handleBuild(player, buildSpec("line", 1, "LECTERN", worldName,
                baseOffset[0] + 1.0, baseOffset[1], baseOffset[2]), anchor);
            handleBuild(player, buildSpec("line", 1, "LANTERN", worldName,
                baseOffset[0], baseOffset[1] + 2.0, baseOffset[2]), anchor);
            }
            case "library_reading_nook" -> {
            handleBuild(player, buildSpec("platform", 1, "OAK_PLANKS", worldName,
                baseOffset[0], baseOffset[1], baseOffset[2]), anchor);
            handleBuild(player, buildSpec("line", 1, "BOOKSHELF", worldName,
                baseOffset[0] + 1.0, baseOffset[1], baseOffset[2]), anchor);
            handleBuild(player, buildSpec("line", 1, "LECTERN", worldName,
                baseOffset[0] - 1.0, baseOffset[1], baseOffset[2]), anchor);
            handleBuild(player, buildSpec("line", 1, "LANTERN", worldName,
                baseOffset[0], baseOffset[1] + 1.0, baseOffset[2]), anchor);
            }
            case "temple_altar_circle" -> {
            handleBuild(player, buildSpec("platform", 2, "STONE_BRICKS", worldName,
                baseOffset[0], baseOffset[1], baseOffset[2]), anchor);
            handleBuild(player, buildSpec("line", 1, "CHISELED_STONE_BRICKS", worldName,
                baseOffset[0], baseOffset[1], baseOffset[2]), anchor);
            handleBuild(player, buildSpec("line", 2, "SOUL_LANTERN", worldName,
                baseOffset[0] - 1.0, baseOffset[1] + 1.0, baseOffset[2]), anchor);
            handleBuild(player, buildSpec("line", 1, "CAMPFIRE", worldName,
                baseOffset[0] + 1.0, baseOffset[1], baseOffset[2]), anchor);
            }
            case "temple_prayer_pillars" -> {
            handleBuild(player, buildSpec("platform", 2, "POLISHED_ANDESITE", worldName,
                baseOffset[0], baseOffset[1], baseOffset[2]), anchor);
            handleBuild(player, buildSpec("line", 2, "STONE_BRICK_WALL", worldName,
                baseOffset[0] - 1.0, baseOffset[1], baseOffset[2]), anchor);
            handleBuild(player, buildSpec("line", 2, "STONE_BRICK_WALL", worldName,
                baseOffset[0] + 1.0, baseOffset[1], baseOffset[2]), anchor);
            handleBuild(player, buildSpec("line", 1, "SOUL_LANTERN", worldName,
                baseOffset[0], baseOffset[1] + 2.0, baseOffset[2]), anchor);
            }
            case "arena_training_ring" -> {
            handleBuild(player, buildSpec("platform", 2, "SMOOTH_STONE", worldName,
                baseOffset[0], baseOffset[1], baseOffset[2]), anchor);
            handleBuild(player, buildSpec("line", 3, "OAK_FENCE", worldName,
                baseOffset[0] - 1.0, baseOffset[1], baseOffset[2]), anchor);
            handleBuild(player, buildSpec("line", 2, "TARGET", worldName,
                baseOffset[0] + 1.0, baseOffset[1], baseOffset[2]), anchor);
            handleBuild(player, buildSpec("line", 2, "TORCH", worldName,
                baseOffset[0], baseOffset[1] + 1.0, baseOffset[2] + 1.0), anchor);
            }
            case "arena_armory_rack" -> {
            handleBuild(player, buildSpec("platform", 1, "STONE_BRICKS", worldName,
                baseOffset[0], baseOffset[1], baseOffset[2]), anchor);
            handleBuild(player, buildSpec("line", 2, "OAK_FENCE", worldName,
                baseOffset[0], baseOffset[1], baseOffset[2] + 1.0), anchor);
            handleBuild(player, buildSpec("line", 1, "IRON_BARS", worldName,
                baseOffset[0] + 1.0, baseOffset[1], baseOffset[2]), anchor);
            handleBuild(player, buildSpec("line", 1, "ANVIL", worldName,
                baseOffset[0] - 1.0, baseOffset[1], baseOffset[2]), anchor);
            handleBuild(player, buildSpec("line", 1, "CHEST", worldName,
                baseOffset[0], baseOffset[1], baseOffset[2] - 1.0), anchor);
            }
            case "inn_common_room" -> {
            handleBuild(player, buildSpec("house", 2, "SPRUCE_PLANKS", worldName,
                baseOffset[0], baseOffset[1], baseOffset[2]), anchor);
            handleBuild(player, buildSpec("line", 2, "BARREL", worldName,
                baseOffset[0] - 1.0, baseOffset[1], baseOffset[2]), anchor);
            handleBuild(player, buildSpec("line", 1, "CAMPFIRE", worldName,
                baseOffset[0] + 1.0, baseOffset[1], baseOffset[2]), anchor);
            handleBuild(player, buildSpec("line", 1, "CRAFTING_TABLE", worldName,
                baseOffset[0], baseOffset[1], baseOffset[2] + 1.0), anchor);
            handleBuild(player, buildSpec("line", 1, "LANTERN", worldName,
                baseOffset[0], baseOffset[1] + 2.0, baseOffset[2]), anchor);
            }
            case "inn_store_room" -> {
            handleBuild(player, buildSpec("platform", 1, "SPRUCE_PLANKS", worldName,
                baseOffset[0], baseOffset[1], baseOffset[2]), anchor);
            handleBuild(player, buildSpec("line", 2, "BARREL", worldName,
                baseOffset[0], baseOffset[1], baseOffset[2] + 1.0), anchor);
            handleBuild(player, buildSpec("line", 1, "CHEST", worldName,
                baseOffset[0] + 1.0, baseOffset[1], baseOffset[2]), anchor);
            handleBuild(player, buildSpec("line", 1, "SMOKER", worldName,
                baseOffset[0] - 1.0, baseOffset[1], baseOffset[2]), anchor);
            }
            case "workshop_tool_bench" -> {
            handleBuild(player, buildSpec("platform", 2, "OAK_PLANKS", worldName,
                baseOffset[0], baseOffset[1], baseOffset[2]), anchor);
            handleBuild(player, buildSpec("line", 2, "CRAFTING_TABLE", worldName,
                baseOffset[0], baseOffset[1], baseOffset[2] + 1.0), anchor);
            handleBuild(player, buildSpec("line", 1, "ANVIL", worldName,
                baseOffset[0] + 1.0, baseOffset[1], baseOffset[2]), anchor);
            handleBuild(player, buildSpec("line", 1, "BLAST_FURNACE", worldName,
                baseOffset[0] - 1.0, baseOffset[1], baseOffset[2]), anchor);
            handleBuild(player, buildSpec("line", 1, "LANTERN", worldName,
                baseOffset[0], baseOffset[1] + 1.0, baseOffset[2]), anchor);
            }
            case "workshop_parts_shelf" -> {
            handleBuild(player, buildSpec("platform", 1, "OAK_PLANKS", worldName,
                baseOffset[0], baseOffset[1], baseOffset[2]), anchor);
            handleBuild(player, buildSpec("line", 2, "BARREL", worldName,
                baseOffset[0], baseOffset[1], baseOffset[2] + 1.0), anchor);
            handleBuild(player, buildSpec("line", 1, "CHEST", worldName,
                baseOffset[0] + 1.0, baseOffset[1], baseOffset[2]), anchor);
            handleBuild(player, buildSpec("line", 2, "OAK_SLAB", worldName,
                baseOffset[0] - 1.0, baseOffset[1] + 1.0, baseOffset[2]), anchor);
            handleBuild(player, buildSpec("line", 1, "LANTERN", worldName,
                baseOffset[0], baseOffset[1] + 2.0, baseOffset[2]), anchor);
            }
            case "warehouse_loading_bay" -> {
            handleBuild(player, buildSpec("platform", 2, "OAK_PLANKS", worldName,
                baseOffset[0], baseOffset[1], baseOffset[2]), anchor);
            handleBuild(player, buildSpec("line", 3, "OAK_LOG", worldName,
                baseOffset[0], baseOffset[1], baseOffset[2] - 1.0), anchor);
            handleBuild(player, buildSpec("line", 2, "CHEST", worldName,
                baseOffset[0] + 1.0, baseOffset[1], baseOffset[2]), anchor);
            handleBuild(player, buildSpec("line", 2, "BARREL", worldName,
                baseOffset[0] - 1.0, baseOffset[1], baseOffset[2]), anchor);
            handleBuild(player, buildSpec("line", 1, "RAIL", worldName,
                baseOffset[0], baseOffset[1], baseOffset[2] + 1.0), anchor);
            }
            case "warehouse_crate_lane" -> {
            handleBuild(player, buildSpec("platform", 2, "OAK_PLANKS", worldName,
                baseOffset[0], baseOffset[1], baseOffset[2]), anchor);
            handleBuild(player, buildSpec("line", 3, "BARREL", worldName,
                baseOffset[0], baseOffset[1], baseOffset[2] + 1.0), anchor);
            handleBuild(player, buildSpec("line", 2, "CHEST", worldName,
                baseOffset[0] + 1.0, baseOffset[1], baseOffset[2]), anchor);
            handleBuild(player, buildSpec("line", 2, "OAK_LOG", worldName,
                baseOffset[0] - 1.0, baseOffset[1], baseOffset[2]), anchor);
            }
            case "trade_post_checkpoint_gate" -> {
            handleBuild(player, buildSpec("platform", 2, "OAK_PLANKS", worldName,
                baseOffset[0], baseOffset[1], baseOffset[2]), anchor);
            handleBuild(player, buildSpec("line", 3, "OAK_FENCE", worldName,
                baseOffset[0], baseOffset[1], baseOffset[2] + 1.0), anchor);
            handleBuild(player, buildSpec("line", 2, "COBBLESTONE_WALL", worldName,
                baseOffset[0] + 1.0, baseOffset[1], baseOffset[2]), anchor);
            handleBuild(player, buildSpec("line", 2, "YELLOW_WOOL", worldName,
                baseOffset[0], baseOffset[1] + 1.0, baseOffset[2] + 1.0), anchor);
            handleBuild(player, buildSpec("line", 1, "LANTERN", worldName,
                baseOffset[0], baseOffset[1] + 2.0, baseOffset[2]), anchor);
            handleBuild(player, buildSpec("line", 1, "CHEST", worldName,
                baseOffset[0] - 1.0, baseOffset[1], baseOffset[2]), anchor);
            }
            case "trade_post_caravan_camp" -> {
            handleBuild(player, buildSpec("house", 2, "WHITE_WOOL", worldName,
                baseOffset[0], baseOffset[1], baseOffset[2]), anchor);
            handleBuild(player, buildSpec("line", 1, "CAMPFIRE", worldName,
                baseOffset[0] + 1.0, baseOffset[1], baseOffset[2] + 1.0), anchor);
            handleBuild(player, buildSpec("line", 2, "BARREL", worldName,
                baseOffset[0] - 1.0, baseOffset[1], baseOffset[2]), anchor);
            handleBuild(player, buildSpec("line", 2, "CHEST", worldName,
                baseOffset[0] + 1.0, baseOffset[1], baseOffset[2]), anchor);
            handleBuild(player, buildSpec("line", 1, "CRAFTING_TABLE", worldName,
                baseOffset[0], baseOffset[1], baseOffset[2] - 1.0), anchor);
            handleBuild(player, buildSpec("line", 1, "LANTERN", worldName,
                baseOffset[0], baseOffset[1] + 2.0, baseOffset[2]), anchor);
            }
            case "fishing_drying_rack" -> {
            handleBuild(player, buildSpec("platform", 1, "SPRUCE_PLANKS", worldName,
                baseOffset[0], baseOffset[1], baseOffset[2]), anchor);
            handleBuild(player, buildSpec("line", 3, "OAK_FENCE", worldName,
                baseOffset[0], baseOffset[1], baseOffset[2] + 1.0), anchor);
            handleBuild(player, buildSpec("line", 2, "BLUE_WOOL", worldName,
                baseOffset[0], baseOffset[1] + 1.0, baseOffset[2] + 1.0), anchor);
            handleBuild(player, buildSpec("line", 1, "CAMPFIRE", worldName,
                baseOffset[0] + 1.0, baseOffset[1], baseOffset[2]), anchor);
            handleBuild(player, buildSpec("line", 1, "BARREL", worldName,
                baseOffset[0] - 1.0, baseOffset[1], baseOffset[2]), anchor);
            }
            case "fishing_boat_shed" -> {
            handleBuild(player, buildSpec("house", 2, "SPRUCE_PLANKS", worldName,
                baseOffset[0], baseOffset[1], baseOffset[2]), anchor);
            handleBuild(player, buildSpec("line", 2, "OAK_LOG", worldName,
                baseOffset[0], baseOffset[1], baseOffset[2] + 1.0), anchor);
            handleBuild(player, buildSpec("line", 1, "CHEST", worldName,
                baseOffset[0] + 1.0, baseOffset[1], baseOffset[2]), anchor);
            handleBuild(player, buildSpec("line", 1, "BARREL", worldName,
                baseOffset[0] - 1.0, baseOffset[1], baseOffset[2]), anchor);
            handleBuild(player, buildSpec("line", 2, "BLUE_WOOL", worldName,
                baseOffset[0], baseOffset[1], baseOffset[2] + 2.0), anchor);
            handleBuild(player, buildSpec("line", 1, "LANTERN", worldName,
                baseOffset[0], baseOffset[1] + 1.0, baseOffset[2]), anchor);
            }
            default -> handleBuild(player, buildSpec("platform", 1, "OAK_PLANKS", worldName,
                    baseOffset[0], baseOffset[1], baseOffset[2]), anchor);
        }
    }

    private Map<String, Object> buildSpec(
            String shape,
            int size,
            String material,
            String worldName,
            double dx,
            double dy,
            double dz) {
        Map<String, Object> spec = new LinkedHashMap<>();
        spec.put("shape", shape);
        spec.put("size", size);
        spec.put("material", material);
        if (worldName != null && !worldName.isBlank()) {
            spec.put("world", worldName);
        }
        Map<String, Object> offset = new LinkedHashMap<>();
        offset.put("dx", dx);
        offset.put("dy", dy);
        offset.put("dz", dz);
        spec.put("offset", offset);
        return spec;
    }

    private void handleBlocks(Player player, Object spec, Location anchor) {
        List<Map<String, Object>> entries = asOperationEntryList(spec);
        for (Map<String, Object> entry : entries) {
            handleSingleBlock(player, entry, anchor);
        }
    }

    private void handleSingleBlock(Player player, Map<String, Object> blockMap, Location anchor) {
        if (blockMap == null || blockMap.isEmpty()) {
            return;
        }

        String token = string(blockMap.get("type"), "");
        if (token.isBlank()) {
            token = string(blockMap.get("block"), string(blockMap.get("material"), ""));
        }
        Material material = resolveMaterial(token, Material.OAK_PLANKS);

        Location loc = anchor != null ? anchor.clone() : player.getLocation().clone();

        String worldName = string(blockMap.get("world"), "");
        if (!worldName.isBlank()) {
            World world = Bukkit.getWorld(worldName);
            if (world != null) {
                loc.setWorld(world);
            }
        }

        if (blockMap.get("location") instanceof Map<?, ?> locationRaw) {
            Map<String, Object> locationMap = asStringObjectMap(locationRaw);
            applyAbsoluteCoordinates(loc, locationMap);
            applyWorldName(loc, string(locationMap.get("world"), ""));
        }

        applyAbsoluteCoordinates(loc, blockMap);
        applyOffsetCoordinates(loc, blockMap);

        World targetWorld = loc.getWorld() == null ? player.getWorld() : loc.getWorld();
        targetWorld.getBlockAt(loc.getBlockX(), loc.getBlockY(), loc.getBlockZ()).setType(material);
    }

    private void handleSpawnMultiEntries(Player player, Object spec, Location anchor) {
        List<Map<String, Object>> entries = asOperationEntryList(spec);
        if (entries.isEmpty()) {
            return;
        }

        List<Map<String, Object>> advancedEntries = new ArrayList<>();
        for (Map<String, Object> entry : entries) {
            if (isAdvancedSpawnEntry(entry)) {
                advancedEntries.add(entry);
                continue;
            }
            handleSpawn(player, entry, anchor);
        }

        if (!advancedEntries.isEmpty()) {
            advancedBuilder.handleSpawnMulti(player, advancedEntries, anchor);
        }
    }

    private boolean isAdvancedSpawnEntry(Map<String, Object> spawnMap) {
        if (spawnMap == null || spawnMap.isEmpty()) {
            return false;
        }
        boolean hasPosition = spawnMap.get("position") instanceof Map<?, ?>;
        boolean hasDirectCoordinates = spawnMap.get("x") != null
                || spawnMap.get("y") != null
                || spawnMap.get("z") != null
                || spawnMap.get("offset") instanceof Map<?, ?>
                || spawnMap.get("dx") != null
                || spawnMap.get("dy") != null
                || spawnMap.get("dz") != null;
        return hasPosition && !hasDirectCoordinates;
    }

    private List<Map<String, Object>> asOperationEntryList(Object spec) {
        List<Map<String, Object>> entries = new ArrayList<>();
        if (spec instanceof Map<?, ?> map) {
            Map<String, Object> converted = asStringObjectMap(map);
            if (!converted.isEmpty()) {
                entries.add(converted);
            }
            return entries;
        }

        if (spec instanceof List<?> list) {
            for (Object entry : list) {
                if (entry instanceof Map<?, ?> entryMap) {
                    Map<String, Object> converted = asStringObjectMap(entryMap);
                    if (!converted.isEmpty()) {
                        entries.add(converted);
                    }
                }
            }
        }
        return entries;
    }

    private double[] resolveOffset(Map<String, Object> payload) {
        double dx = 0.0D;
        double dy = 0.0D;
        double dz = 0.0D;

        if (payload.get("offset") instanceof Map<?, ?> offsetRaw) {
            Map<String, Object> offsetMap = asStringObjectMap(offsetRaw);
            dx += number(offsetMap.get("dx"), 0.0D).doubleValue();
            dy += number(offsetMap.get("dy"), 0.0D).doubleValue();
            dz += number(offsetMap.get("dz"), 0.0D).doubleValue();
        }

        if (payload.get("dx") != null) {
            dx += number(payload.get("dx"), 0.0D).doubleValue();
        }
        if (payload.get("dy") != null) {
            dy += number(payload.get("dy"), 0.0D).doubleValue();
        }
        if (payload.get("dz") != null) {
            dz += number(payload.get("dz"), 0.0D).doubleValue();
        }

        return new double[] { dx, dy, dz };
    }

    private void applyAbsoluteCoordinates(Location loc, Map<String, Object> payload) {
        if (payload == null || payload.isEmpty()) {
            return;
        }
        if (payload.get("x") != null) {
            loc.setX(number(payload.get("x"), loc.getX()).doubleValue());
        }
        if (payload.get("y") != null) {
            loc.setY(number(payload.get("y"), loc.getY()).doubleValue());
        }
        if (payload.get("z") != null) {
            loc.setZ(number(payload.get("z"), loc.getZ()).doubleValue());
        }
    }

    private void applyOffsetCoordinates(Location loc, Map<String, Object> payload) {
        if (payload == null || payload.isEmpty()) {
            return;
        }

        double[] offset = resolveOffset(payload);
        loc.add(offset[0], offset[1], offset[2]);
    }

    private void applyWorldName(Location loc, String worldName) {
        if (worldName == null || worldName.isBlank()) {
            return;
        }
        World targetWorld = Bukkit.getWorld(worldName);
        if (targetWorld != null) {
            loc.setWorld(targetWorld);
        }
    }

    private Material resolveMaterial(String token, Material fallback) {
        String normalized = string(token, "").trim().toLowerCase(Locale.ROOT);
        if (normalized.isBlank()) {
            return fallback;
        }

        if (normalized.startsWith("minecraft:")) {
            normalized = normalized.substring("minecraft:".length());
        }

        switch (normalized) {
            case "fire", "bonfire" -> normalized = "campfire";
            case "plank", "planks", "wood" -> normalized = "oak_planks";
            case "log" -> normalized = "oak_log";
            default -> {
            }
        }

        String materialName = normalized.replace('-', '_').toUpperCase(Locale.ROOT);
        Material material = Material.matchMaterial(materialName);
        return material == null ? fallback : material;
    }

    // =============================== tell ===============================
    private void handleTell(Player player, Object tellObj) {
        if (tellObj == null)
            return;

        if (tellObj instanceof String tell) {
            player.sendMessage(ChatColor.AQUA + "【心悦宇宙】 " + ChatColor.WHITE + tell);
        } else if (tellObj instanceof List<?> list) {
            for (Object line : list) {
                if (line == null)
                    continue;
                player.sendMessage(ChatColor.AQUA + "【心悦宇宙】 " + ChatColor.WHITE + line.toString());
            }
        }
    }

    // =============================== weather ===============================
    private void handleWeather(Player player, String weather) {
        World world = player.getWorld();
        weather = weather.toLowerCase();

        switch (weather) {
            case "clear" -> {
                world.setStorm(false);
                world.setThundering(false);
                world.setWeatherDuration(20 * 60 * 5);
                player.sendMessage(ChatColor.YELLOW + "✧ 天空放晴，心绪也变得清透。");
            }
            case "rain" -> {
                world.setStorm(true);
                world.setThundering(false);
                player.sendMessage(ChatColor.BLUE + "✧ 细雨落下，像是心里的某种投影。");
            }
            case "storm", "thunder" -> {
                world.setStorm(true);
                world.setThundering(true);
                player.sendMessage(ChatColor.DARK_BLUE + "✧ 雷声滚滚，世界在为你的故事鼓点。");
            }
            case "dream_sky" -> {
                world.setStorm(false);
                world.setThundering(false);
                player.sendMessage(ChatColor.LIGHT_PURPLE + "✧ 天空像被染成柔软的梦色。");
            }
            case "dark_sky" -> {
                world.setStorm(true);
                world.setThundering(false);
                player.sendMessage(ChatColor.DARK_PURPLE + "✧ 乌云压顶，像是剧情即将转折。");
            }
            default -> {
                world.setStorm(false);
                world.setThundering(false);
            }
        }
    }

    private void handleWeatherTransition(Player player, Map<String, Object> payload) {
        if (payload == null || payload.isEmpty()) {
            return;
        }
        String fromState = string(payload.get("from"), "");
        String toState = string(payload.get("to"), string(payload.get("state"), ""));
        String message = string(payload.get("message"), "");
        if (!toState.isBlank()) {
            handleWeather(player, toState);
        }
        if (!message.isBlank()) {
            player.sendMessage(ChatColor.BLUE + "✧ " + message);
        } else if (!fromState.isBlank() || !toState.isBlank()) {
            player.sendMessage(ChatColor.BLUE + "✧ 天气转场：" + humanize(fromState) + " → " + humanize(toState));
        }
    }

    // =============================== time ===============================
    private void handleTime(Player player, String time) {
        World world = player.getWorld();
        time = time.toLowerCase();

        long ticks;
        switch (time) {
            case "day" -> ticks = 1000L;
            case "sunrise" -> ticks = 23000L;
            case "sunset" -> ticks = 12000L;
            case "midnight" -> ticks = 18000L;
            case "night" -> ticks = 14000L;
            default -> ticks = world.getTime();
        }

        world.setTime(ticks);
        player.sendMessage(ChatColor.GOLD + "✧ 时间被轻轻拨动，场景也随之改变。");
    }

    private void handleLightingShift(Player player, Object payload) {
        if (payload == null) {
            return;
        }

        String shiftName = "";
        String suggestedTime = "";

        if (payload instanceof String shift) {
            shiftName = shift;
        } else if (payload instanceof Map<?, ?> map) {
            shiftName = string(map.get("label"), string(map.get("id"), string(map.get("name"), "")));
            suggestedTime = string(map.get("time"), "");
        }

        if (!shiftName.isBlank()) {
            player.sendMessage(ChatColor.GOLD + "✧ 光线变化：" + humanize(shiftName));
        }

        String normalized = shiftName.toLowerCase(Locale.ROOT);
        if (!suggestedTime.isBlank()) {
            handleTime(player, suggestedTime);
        } else if (!normalized.isBlank()) {
            if (normalized.contains("sunrise") || normalized.contains("dawn")) {
                handleTime(player, "sunrise");
            } else if (normalized.contains("dusk") || normalized.contains("sunset")) {
                handleTime(player, "sunset");
            } else if (normalized.contains("night") || normalized.contains("neon")) {
                handleTime(player, "night");
            }
        }
    }

    private void handleMusic(Player player, Object payload) {
        if (payload == null) {
            return;
        }

        String record = null;
        double volume = 0.8;
        double pitch = 1.0;

        if (payload instanceof String direct) {
            record = direct;
        } else if (payload instanceof Map<?, ?> map) {
            record = string(map.get("record"), string(map.get("id"), ""));
            volume = number(map.get("volume"), 0.8).doubleValue();
            pitch = number(map.get("pitch"), 1.0).doubleValue();
        }

        if (record == null || record.isBlank()) {
            return;
        }

        Sound sound = resolveRecord(record);
        if (sound == null) {
            return;
        }

        float vol = (float) volume;
        float pit = (float) pitch;
        player.playSound(player.getLocation(), sound, SoundCategory.RECORDS, Math.max(0.0f, vol), Math.max(0.1f, pit));
        player.sendMessage(ChatColor.LIGHT_PURPLE + "♪ 音轨切换：" + humanize(record));
    }

    // =============================== teleport ★ SafeTeleport v3
    // ===============================
    private Location calculateSafeTeleportTarget(Player player, Map<String, Object> tpMap) {
        World world = player.getWorld();
        Location base = player.getLocation();

        String mode = string(tpMap.get("mode"), "relative");
        double x = number(tpMap.get("x"), 0).doubleValue();
        double y = number(tpMap.get("y"), base.getY()).doubleValue();
        double z = number(tpMap.get("z"), 0).doubleValue();

        Location rawTarget;
        if ("absolute".equalsIgnoreCase(mode)) {
            rawTarget = new Location(world, x, y, z, base.getYaw(), base.getPitch());
        } else {
            rawTarget = base.clone().add(x, y, z);
        }

        var chunk = world.getChunkAt(rawTarget);
        if (!chunk.isLoaded()) {
            chunk.load(true);
            plugin.getLogger().info("[SafeTeleport] Chunk forced load at " +
                    chunk.getX() + "," + chunk.getZ());
        }

        int highestBlockY = world.getHighestBlockYAt(rawTarget.getBlockX(), rawTarget.getBlockZ());
        double safeY = rawTarget.getY();

        if (safeY <= 1) {
            safeY = highestBlockY + 1.2;
        } else if (safeY - highestBlockY > 6) {
            safeY = highestBlockY + 1.2;
        }

        Material blockAt = world.getBlockAt(rawTarget).getType();
        if (blockAt.isSolid()) {
            safeY = Math.max(safeY, highestBlockY + 1.2);
            plugin.getLogger().warning("[SafeTeleport] inside solid block → Y fixed to " + safeY);
        }

        return new Location(
                world,
                rawTarget.getX(),
                safeY,
                rawTarget.getZ(),
                base.getYaw(),
                base.getPitch());
    }

    @SuppressWarnings("unchecked")
    private void performTeleport(Player player, Map<String, Object> tpMap, Location safeTarget) {
        World world = player.getWorld();

        Bukkit.getScheduler().runTask(plugin, () -> {
            player.teleport(safeTarget);
            plugin.getLogger().info(String.format("[SafeTeleport] Player teleported to %.2f,%.2f,%.2f",
                    safeTarget.getX(), safeTarget.getY(), safeTarget.getZ()));

            player.sendMessage(ChatColor.GREEN + "✧ 你被世界轻轻挪到了一个安全的位置。");

            if (tpMap.containsKey("safe_platform")) {
                Object spObj = tpMap.get("safe_platform");
                if (spObj instanceof Map<?, ?> spRaw) {
                    Map<String, Object> sp = (Map<String, Object>) spRaw;
                    String matName = string(sp.get("material"), "GLASS");
                    int radius = number(sp.get("radius"), 2).intValue();
                    Material mat = Material.matchMaterial(matName.toUpperCase());
                    if (mat == null) {
                        mat = Material.GLASS;
                    }
                    buildPlatform(world, safeTarget.clone().add(0, -1, 0), radius, mat);
                }
            }
        });
    }

    // =============================== build ===============================

    @SuppressWarnings("unchecked")
    private void handleBuild(Player player, Map<String, Object> buildMap, Location anchor) {
        World world = player.getWorld();
        Location base = anchor != null ? anchor.clone() : player.getLocation().clone();

        String worldName = string(buildMap.get("world"), "");
        if (!worldName.isBlank()) {
            World targetWorld = Bukkit.getWorld(worldName);
            if (targetWorld != null) {
                world = targetWorld;
                base.setWorld(targetWorld);
            }
        }

        String shape = string(buildMap.get("shape"), "platform");
        String materialName = string(buildMap.get("material"), "OAK_PLANKS");
        Material material = Material.matchMaterial(materialName.toUpperCase());
        if (material == null)
            material = Material.OAK_PLANKS;

        int size = number(buildMap.get("size"), 3).intValue();
        if (size < 1)
            size = 1;

        Map<String, Object> offsetMap = null;
        if (buildMap.get("offset") instanceof Map<?, ?> off) {
            offsetMap = (Map<String, Object>) off;
        } else if (buildMap.get("safe_offset") instanceof Map<?, ?> off2) {
            offsetMap = (Map<String, Object>) off2;
        }

        Location origin = base.clone();
        if (offsetMap != null) {
            double dx = number(offsetMap.get("dx"), 0).doubleValue();
            double dy = number(offsetMap.get("dy"), 0).doubleValue();
            double dz = number(offsetMap.get("dz"), 0).doubleValue();
            origin.add(dx, dy, dz);
        }

        shape = shape.toLowerCase();
        switch (shape) {
            case "platform" -> buildPlatform(world, origin, size, material);
            case "house" -> buildSimpleHouse(world, origin, size, material);
            case "wall" -> buildWall(world, origin, size, material);
            case "line" -> buildLine(world, origin, size, material);
            case "sphere" -> buildSphere(world, origin, size, material, false);
            case "hollow_sphere" -> buildSphere(world, origin, size, material, true);
            case "cylinder" -> buildCylinder(world, origin, size, material);
            case "floating_platform" -> buildPlatform(world, origin.add(0, size, 0), size, material);
            case "heart_pad" -> buildHeartPad(world, origin, size, material);
            default -> buildPlatform(world, origin, size, material);
        }

        player.sendMessage(ChatColor.YELLOW + "✧ 世界根据你的心念，构筑了「" + shape + "」。");
    }

    private void buildPlatform(World world, Location origin, int radius, Material mat) {
        int ox = origin.getBlockX();
        int oy = origin.getBlockY();
        int oz = origin.getBlockZ();

        for (int x = -radius; x <= radius; x++) {
            for (int z = -radius; z <= radius; z++) {
                world.getBlockAt(ox + x, oy, oz + z).setType(mat);
            }
        }
    }

    private void buildWall(World world, Location origin, int size, Material mat) {
        int ox = origin.getBlockX();
        int oy = origin.getBlockY();
        int oz = origin.getBlockZ();

        int h = Math.max(3, size);
        for (int y = 0; y < h; y++) {
            for (int x = 0; x < size; x++) {
                world.getBlockAt(ox + x, oy + y, oz).setType(mat);
            }
        }
    }

    private void buildLine(World world, Location origin, int length, Material mat) {
        int ox = origin.getBlockX();
        int oy = origin.getBlockY();
        int oz = origin.getBlockZ();
        for (int i = 0; i < length; i++) {
            world.getBlockAt(ox + i, oy, oz).setType(mat);
        }
    }

    private void buildSimpleHouse(World world, Location origin, int size, Material mat) {
        int ox = origin.getBlockX();
        int oy = origin.getBlockY();
        int oz = origin.getBlockZ();

        int w = size;
        int h = Math.max(3, size);

        for (int x = 0; x < w; x++) {
            for (int z = 0; z < w; z++) {
                world.getBlockAt(ox + x, oy, oz + z).setType(mat);
            }
        }

        for (int y = 1; y <= h; y++) {
            for (int x = 0; x < w; x++) {
                world.getBlockAt(ox + x, oy + y, oz).setType(mat);
                world.getBlockAt(ox + x, oy + y, oz + w - 1).setType(mat);
            }
            for (int z = 0; z < w; z++) {
                world.getBlockAt(ox, oy + y, oz + z).setType(mat);
                world.getBlockAt(ox + w - 1, oy + y, oz + z).setType(mat);
            }
        }

        for (int x = 0; x < w; x++) {
            for (int z = 0; z < w; z++) {
                world.getBlockAt(ox + x, oy + h + 1, oz + z).setType(mat);
            }
        }
    }

    private void buildSphere(World world, Location origin, int radius, Material mat, boolean hollow) {
        int ox = origin.getBlockX();
        int oy = origin.getBlockY();
        int oz = origin.getBlockZ();

        int r2 = radius * radius;
        int inner = (radius - 1) * (radius - 1);

        for (int x = -radius; x <= radius; x++) {
            for (int y = -radius; y <= radius; y++) {
                for (int z = -radius; z <= radius; z++) {
                    int d2 = x * x + y * y + z * z;
                    if (d2 > r2)
                        continue;
                    if (hollow && d2 < inner)
                        continue;
                    world.getBlockAt(ox + x, oy + y, oz + z).setType(mat);
                }
            }
        }
    }

    private void buildCylinder(World world, Location origin, int radius, Material mat) {
        int ox = origin.getBlockX();
        int oy = origin.getBlockY();
        int oz = origin.getBlockZ();

        int h = Math.max(3, radius);

        for (int y = 0; y < h; y++) {
            for (int x = -radius; x <= radius; x++) {
                for (int z = -radius; z <= radius; z++) {
                    if (x * x + z * z <= radius * radius) {
                        world.getBlockAt(ox + x, oy + y, oz + z).setType(mat);
                    }
                }
            }
        }
    }

    // ♥ 小心悦专属心形平台
    private void buildHeartPad(World world, Location origin, int size, Material mat) {
        int ox = origin.getBlockX();
        int oy = origin.getBlockY();
        int oz = origin.getBlockZ();

        double r = size;

        for (int x = -size; x <= size; x++) {
            for (int z = -size; z <= size; z++) {
                double nx = x / r;
                double nz = z / r;
                double f = Math.pow(nx * nx + nz * nz - 1, 3) - nx * nx * nz * nz * nz;
                if (f <= 0) {
                    world.getBlockAt(ox + x, oy, oz + z).setType(mat);
                }
            }
        }
    }

    // =============================== spawn ===============================
    @SuppressWarnings("unchecked")
    private void handleSpawn(Player player, Map<String, Object> spawnMap, Location anchor) {
        World world = player.getWorld();
        Location base = anchor != null ? anchor.clone() : player.getLocation().clone();

        String typeName = string(spawnMap.get("type"), "ARMOR_STAND");
        String name = string(spawnMap.get("name"), "");

        Map<String, Object> offsetMap = null;
        if (spawnMap.get("offset") instanceof Map<?, ?> off) {
            offsetMap = (Map<String, Object>) off;
        }

        Map<String, Object> positionMap = null;
        if (spawnMap.get("position") instanceof Map<?, ?> positionRaw) {
            positionMap = asStringObjectMap(positionRaw);
        }

        Location loc = base.clone();

        String worldName = string(spawnMap.get("world"), "");
        if (!worldName.isBlank()) {
            World targetWorld = Bukkit.getWorld(worldName);
            if (targetWorld != null) {
                loc.setWorld(targetWorld);
            }
        }

        if (spawnMap.get("x") != null) {
            loc.setX(number(spawnMap.get("x"), loc.getX()).doubleValue());
        }
        if (spawnMap.get("y") != null) {
            loc.setY(number(spawnMap.get("y"), loc.getY()).doubleValue());
        }
        if (spawnMap.get("z") != null) {
            loc.setZ(number(spawnMap.get("z"), loc.getZ()).doubleValue());
        }

        if (positionMap != null && !positionMap.isEmpty()) {
            if (spawnMap.get("x") == null && positionMap.get("x") != null) {
                loc.setX(number(positionMap.get("x"), loc.getX()).doubleValue());
            }
            if (spawnMap.get("y") == null && positionMap.get("y") != null) {
                loc.setY(number(positionMap.get("y"), loc.getY()).doubleValue());
            }
            if (spawnMap.get("z") == null && positionMap.get("z") != null) {
                loc.setZ(number(positionMap.get("z"), loc.getZ()).doubleValue());
            }

            if (worldName.isBlank()) {
                String positionWorld = string(positionMap.get("world"), "");
                if (!positionWorld.isBlank()) {
                    World targetWorld = Bukkit.getWorld(positionWorld);
                    if (targetWorld != null) {
                        loc.setWorld(targetWorld);
                    }
                }
            }
        }

        if (offsetMap != null) {
            double dx = number(offsetMap.get("dx"), 0).doubleValue();
            double dy = number(offsetMap.get("dy"), 0).doubleValue();
            double dz = number(offsetMap.get("dz"), 0).doubleValue();
            loc.add(dx, dy, dz);
        }

        if (spawnMap.get("dx") != null || spawnMap.get("dy") != null || spawnMap.get("dz") != null) {
            double dx = number(spawnMap.get("dx"), 0).doubleValue();
            double dy = number(spawnMap.get("dy"), 0).doubleValue();
            double dz = number(spawnMap.get("dz"), 0).doubleValue();
            loc.add(dx, dy, dz);
        }

        if (spawnMap.get("yaw") != null) {
            loc.setYaw(number(spawnMap.get("yaw"), loc.getYaw()).floatValue());
        }
        if (spawnMap.get("pitch") != null) {
            loc.setPitch(number(spawnMap.get("pitch"), loc.getPitch()).floatValue());
        }

        if (loc.getWorld() != null && loc.getWorld() != world) {
            world = loc.getWorld();
        }

        EntityType type = EntityType.fromName(typeName.toUpperCase());
        if (type == null) {
            type = EntityType.ARMOR_STAND;
        }

        if (type == EntityType.PLAYER) {
            player.teleport(loc);
            plugin.getLogger().info(String.format(Locale.ROOT,
                    "[WorldPatchExecutor] Treated player spawn as teleport to %.2f, %.2f, %.2f", loc.getX(),
                    loc.getY(), loc.getZ()));
            player.sendMessage(ChatColor.GREEN + "✧ 你被世界轻轻挪到了一个新的位置。");
            return;
        }

        Entity entity = world.spawnEntity(loc, type);
        if (entity instanceof LivingEntity living) {
            if (!name.isEmpty()) {
                living.setCustomName(name);
                living.setCustomNameVisible(true);
            }
            var attr = living.getAttribute(Attribute.GENERIC_MAX_HEALTH);
            if (attr != null) {
                attr.setBaseValue(40.0);
                living.setHealth(40.0);
            }
            entity.teleport(loc);
        }

        afterSpawn(player, spawnMap, entity);

        player.sendMessage(ChatColor.LIGHT_PURPLE + "✧ 世界召唤了一个存在：" +
                (name.isEmpty() ? type.name() : name));
    }

    protected void afterSpawn(Player player, Map<String, Object> spawnSpec, Entity entity) {
        // extension hook for subclasses
    }

    // =============================== effect ===============================
    private void handleEffect(Player player, Map<String, Object> effMap) {
        String typeName = string(effMap.get("type"), "SPEED");
        int seconds = number(effMap.get("seconds"), 5).intValue();
        int amplifier = number(effMap.get("amplifier"), 1).intValue();

        PotionEffectType pet = PotionEffectType.getByName(typeName.toUpperCase());
        if (pet == null)
            pet = PotionEffectType.SPEED;

        player.addPotionEffect(new PotionEffect(pet, seconds * 20, amplifier));
        player.sendMessage(ChatColor.DARK_PURPLE + "✧ 你的状态被「" + typeName + "」轻轻改变。");
    }

    // =============================== particle ===============================
    private void handleParticle(Player player, Map<String, Object> pMap) {
        World world = player.getWorld();
        Location base = player.getLocation().add(0, 1, 0);

        String typeName = string(pMap.get("type"), "HEART");
        int count = number(pMap.get("count"), 40).intValue();
        double radius = number(pMap.get("radius"), 1.5).doubleValue();

        Particle particle = Particle.HEART;
        try {
            particle = Particle.valueOf(typeName.toUpperCase());
        } catch (IllegalArgumentException ignored) {
        }

        for (int i = 0; i < count; i++) {
            double angle = 2 * Math.PI * i / count;
            double dx = Math.cos(angle) * radius;
            double dz = Math.sin(angle) * radius;
            world.spawnParticle(particle, base.getX() + dx, base.getY(), base.getZ() + dz, 1, 0, 0, 0, 0);
        }

        player.sendMessage(ChatColor.LIGHT_PURPLE + "✧ 粒子在你周围旋转，像飘移的思绪。");
    }

    // =============================== sound ===============================
    private void handleSound(Player player, Map<String, Object> sMap) {
        Location loc = player.getLocation();

        String typeName = string(sMap.get("type"), "BLOCK_NOTE_BLOCK_BELL");
        float volume = number(sMap.get("volume"), 1.0).floatValue();
        float pitch = number(sMap.get("pitch"), 1.0).floatValue();

        Sound sound = Sound.BLOCK_NOTE_BLOCK_BELL;
        try {
            sound = Sound.valueOf(typeName.toUpperCase());
        } catch (IllegalArgumentException ignored) {
        }

        player.getWorld().playSound(loc, sound, volume, pitch);
    }

    // =============================== title / actionbar
    // ===============================
    private void handleTitle(Player player, Map<String, Object> tMap) {
        String main = string(tMap.get("main"), "");
        String sub = string(tMap.get("sub"), "");
        int fadeIn = number(tMap.get("fade_in"), 10).intValue();
        int stay = number(tMap.get("stay"), 60).intValue();
        int fadeOut = number(tMap.get("fade_out"), 10).intValue();

        player.sendTitle(
                ChatColor.LIGHT_PURPLE + main,
                ChatColor.WHITE + sub,
                fadeIn, stay, fadeOut);
    }

    private void handleActionBar(Player player, String text) {
        player.sendActionBar(ChatColor.AQUA + text);
    }

    // =============================== triggers ===============================
    private void handleTriggerZones(Player player, Object spec, Location anchor) {
        if (player == null || spec == null) {
            return;
        }

        List<Map<String, Object>> entries = new ArrayList<>();
        if (spec instanceof Map<?, ?> map) {
            entries.add(asStringObjectMap(map));
        } else if (spec instanceof List<?> list) {
            for (Object entry : list) {
                if (entry instanceof Map<?, ?> entryMap) {
                    entries.add(asStringObjectMap(entryMap));
                }
            }
        }

        if (entries.isEmpty()) {
            return;
        }

        clearPlayerTriggers(player.getUniqueId());

        Location reference = anchor != null ? anchor.clone() : player.getLocation().clone();
        CopyOnWriteArrayList<LocationTrigger> triggers = new CopyOnWriteArrayList<>();

        for (Map<String, Object> entry : entries) {
            String questEvent = string(entry.get("quest_event"), "").toLowerCase(Locale.ROOT);
            questEvent = QuestEventCanonicalizer.canonicalize(questEvent);
            if (questEvent.isBlank()) {
                continue;
            }
            double radius = number(entry.get("radius"), 3.0D).doubleValue();
            boolean repeat = Boolean.TRUE.equals(entry.get("repeat"));
            boolean once = !repeat;
            Location center = resolveTriggerCenter(reference, entry, player);
            String triggerId = string(entry.get("id"), questEvent);
            triggers.add(new LocationTrigger(triggerId, center, radius, questEvent, once));
        }

        if (triggers.isEmpty()) {
            return;
        }

        triggerRegistry.put(player.getUniqueId(), triggers);
        ensureTriggerTask();
    }

    private void ensureTriggerTask() {
        if (triggerPoller != null) {
            return;
        }
        triggerPoller = Bukkit.getScheduler().runTaskTimer(plugin, this::pollTriggerZones, 40L, 20L);
    }

    private void pollTriggerZones() {
        if (triggerRegistry.isEmpty()) {
            return;
        }

        List<UUID> removals = new ArrayList<>();

        for (Map.Entry<UUID, CopyOnWriteArrayList<LocationTrigger>> entry : triggerRegistry.entrySet()) {
            UUID playerId = entry.getKey();
            Player player = Bukkit.getPlayer(playerId);
            if (player == null || !player.isOnline()) {
                removals.add(playerId);
                continue;
            }

            CopyOnWriteArrayList<LocationTrigger> triggers = entry.getValue();
            if (triggers == null || triggers.isEmpty()) {
                removals.add(playerId);
                continue;
            }

            Location playerLoc = player.getLocation();
            if (playerLoc.getWorld() == null) {
                continue;
            }

            for (LocationTrigger trigger : triggers) {
                if (trigger.once && trigger.triggered) {
                    continue;
                }
                if (trigger.center.getWorld() == null || !playerLoc.getWorld().equals(trigger.center.getWorld())) {
                    continue;
                }
                if (playerLoc.distanceSquared(trigger.center) <= trigger.radiusSq) {
                    trigger.triggered = true;
                    if (ruleEventBridge != null) {
                        Map<String, Object> payload = new LinkedHashMap<>();
                        payload.put("trigger_id", trigger.id);
                        payload.put("radius", trigger.radius);
                        payload.put("source", "trigger_zone");
                        ruleEventBridge.emitQuestEvent(player, trigger.questEvent, trigger.center, payload);
                    }
                }
            }

            triggers.removeIf(LocationTrigger::shouldRemove);
            if (triggers.isEmpty()) {
                removals.add(playerId);
            }
        }

        for (UUID playerId : removals) {
            triggerRegistry.remove(playerId);
        }

        if (triggerRegistry.isEmpty() && triggerPoller != null) {
            triggerPoller.cancel();
            triggerPoller = null;
        }
    }

    private void clearPlayerTriggers(UUID playerId) {
        triggerRegistry.remove(playerId);
        if (triggerRegistry.isEmpty() && triggerPoller != null) {
            triggerPoller.cancel();
            triggerPoller = null;
        }
    }

    private Location resolveTriggerCenter(Location anchor, Map<String, Object> spec, Player fallback) {
        Location base;
        if (anchor != null) {
            base = anchor.clone();
        } else if (fallback != null) {
            base = fallback.getLocation().clone();
        } else if (!Bukkit.getWorlds().isEmpty()) {
            base = Bukkit.getWorlds().get(0).getSpawnLocation().clone();
        } else {
            return new Location(null, 0, 0, 0);
        }

        String worldName = string(spec.get("world"), "");
        if (!worldName.isBlank()) {
            var world = Bukkit.getWorld(worldName);
            if (world != null) {
                base.setWorld(world);
            }
        }

        double x = base.getX();
        double y = base.getY();
        double z = base.getZ();

        if (spec.get("x") != null) {
            x = number(spec.get("x"), x).doubleValue();
        }
        if (spec.get("y") != null) {
            y = number(spec.get("y"), y).doubleValue();
        }
        if (spec.get("z") != null) {
            z = number(spec.get("z"), z).doubleValue();
        }

        Map<String, Object> offset = asStringObjectMap(spec.get("offset"));
        if (!offset.isEmpty()) {
            x += number(offset.get("dx"), 0).doubleValue();
            y += number(offset.get("dy"), 0).doubleValue();
            z += number(offset.get("dz"), 0).doubleValue();
        }

        if (spec.get("dx") != null || spec.get("dy") != null || spec.get("dz") != null) {
            x += number(spec.get("dx"), 0).doubleValue();
            y += number(spec.get("dy"), 0).doubleValue();
            z += number(spec.get("dz"), 0).doubleValue();
        }

        return new Location(base.getWorld(), x, y, z);
    }

    // =============================== 工具 ===============================
    private String string(Object o, String def) {
        return o == null ? def : o.toString();
    }

    private Number number(Object o, Number def) {
        if (o instanceof Number n)
            return n;
        if (o == null)
            return def;
        try {
            return Double.parseDouble(o.toString());
        } catch (Exception e) {
            return def;
        }
    }

    private Map<String, Object> asStringObjectMap(Object value) {
        if (!(value instanceof Map<?, ?> raw)) {
            return Collections.emptyMap();
        }

        Map<String, Object> converted = new LinkedHashMap<>();
        for (Map.Entry<?, ?> entry : raw.entrySet()) {
            Object key = entry.getKey();
            if (key instanceof String keyStr) {
                converted.put(keyStr, entry.getValue());
            }
        }
        return converted;
    }

    private Sound resolveRecord(String recordName) {
        if (recordName == null) {
            return null;
        }
        String token = recordName.trim();
        if (token.isEmpty()) {
            return null;
        }
        token = token.replace("minecraft:", "");
        token = token.replace("record_", "");
        token = token.replace('-', '_');
        String enumName = token.toUpperCase(Locale.ROOT);
        if (!enumName.startsWith("MUSIC_DISC_")) {
            enumName = "MUSIC_DISC_" + enumName;
        }
        try {
            return Sound.valueOf(enumName);
        } catch (IllegalArgumentException ex) {
            plugin.getLogger().fine("[WorldPatchExecutor] Unknown record: " + recordName);
            return null;
        }
    }

    private String humanize(String token) {
        if (token == null || token.isBlank()) {
            return "平缓";
        }
        String cleaned = token.replace("minecraft:", "").replace('_', ' ').trim();
        if (cleaned.isEmpty()) {
            return token;
        }
        return cleaned.substring(0, 1).toUpperCase(Locale.ROOT) + cleaned.substring(1);
    }

    private static final class LocationTrigger {
        final String id;
        final Location center;
        final double radius;
        final double radiusSq;
        final String questEvent;
        final boolean once;
        boolean triggered;

        LocationTrigger(String id, Location center, double radius, String questEvent, boolean once) {
            this.id = id;
            this.center = center;
            this.radius = radius;
            this.radiusSq = radius * radius;
            this.questEvent = questEvent;
            this.once = once;
            this.triggered = false;
        }

        boolean shouldRemove() {
            return once && triggered;
        }
    }
}
