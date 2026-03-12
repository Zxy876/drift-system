package com.driftmc.world;

import java.util.Locale;
import java.util.Set;
import java.util.UUID;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.ConcurrentLinkedQueue;
import java.util.concurrent.atomic.AtomicBoolean;
import java.util.logging.Level;

import org.bukkit.Bukkit;
import org.bukkit.Material;
import org.bukkit.World;
import org.bukkit.entity.Player;
import org.bukkit.plugin.java.JavaPlugin;
import org.bukkit.scheduler.BukkitTask;

import com.driftmc.backend.BackendClient;
import com.google.gson.Gson;
import com.google.gson.JsonArray;
import com.google.gson.JsonElement;
import com.google.gson.JsonObject;

import okhttp3.Call;
import okhttp3.Callback;
import okhttp3.Response;

public class PayloadExecutorV1 {

    private static final int MAX_QUEUE = 5;
    private static final int MAX_BLOCKS = 5000;
    private static final int MIN_BATCH_SIZE = 20;
    private static final int MAX_BATCH_SIZE = 100;
    private static final int BATCH_STEP = 10;
    private static final Gson GSON = new Gson();

    private final JavaPlugin plugin;
    private final BackendClient backend;
    private final ConcurrentLinkedQueue<PayloadJob> queue = new ConcurrentLinkedQueue<>();
    private final Set<String> executedBuildIds = ConcurrentHashMap.newKeySet();
    private final Set<String> inflightBuildIds = ConcurrentHashMap.newKeySet();
    private final AtomicBoolean workerStarted = new AtomicBoolean(false);

    private BukkitTask workerTask;
    private PayloadJob currentJob;
    private int currentBatchSize = MAX_BATCH_SIZE;
    private long lastTickNanos = 0L;

    public PayloadExecutorV1(JavaPlugin plugin, BackendClient backend) {
        this.plugin = plugin;
        this.backend = backend;
    }

    public boolean enqueue(Player player, JsonObject payload) {
        if (player == null || payload == null) {
            return false;
        }

        ValidationResult validation = validatePayload(payload);
        if (!validation.ok) {
            player.sendMessage("§c[生成拒绝] " + validation.failureCode);
            plugin.getLogger().log(Level.WARNING, "[PayloadExecutorV1] reject payload: {0}", validation.failureCode);
            reportAsync(
                    buildIdFromPayload(payload),
                    player.getName(),
                    "REJECTED",
                    normalizeFailureCode(validation.failureCode),
                    0,
                    0,
                    0,
                    payloadHashFromPayload(payload));
            return false;
        }

        String buildId = validation.buildId;
        if (executedBuildIds.contains(buildId)) {
            plugin.getLogger().log(Level.INFO, "[PayloadExecutorV1] skip duplicate executed build_id={0}", buildId);
            reportAsync(buildId, player.getName(), "REJECTED", "DUPLICATE_BUILD_ID", 0, 0, 0, validation.payloadHash);
            return true;
        }

        if (!inflightBuildIds.add(buildId)) {
            plugin.getLogger().log(Level.INFO, "[PayloadExecutorV1] skip inflight build_id={0}", buildId);
            reportAsync(buildId, player.getName(), "REJECTED", "DUPLICATE_BUILD_ID", 0, 0, 0, validation.payloadHash);
            return true;
        }

        int queueDepth = queue.size();
        if (queueDepth >= MAX_QUEUE) {
            inflightBuildIds.remove(buildId);
            player.sendMessage("§c[生成繁忙] 队列已满，请稍后再试。");
            plugin.getLogger().warning("[PayloadExecutorV1] reject payload: QUEUE_FULL");
            reportAsync(buildId, player.getName(), "REJECTED", "QUEUE_FULL", 0, 0, 0, validation.payloadHash);
            return false;
        }

        PayloadJob job = new PayloadJob(player.getUniqueId(), player.getName(), buildId, validation.payloadHash,
            validation.commands, validation.origin);
        queue.offer(job);
        startWorkerIfNeeded();
        return true;
    }

    public void shutdown() {
        if (workerTask != null) {
            workerTask.cancel();
            workerTask = null;
        }
        queue.clear();
        inflightBuildIds.clear();
        currentJob = null;
        workerStarted.set(false);
    }

    private void startWorkerIfNeeded() {
        if (!workerStarted.compareAndSet(false, true)) {
            return;
        }
        workerTask = Bukkit.getScheduler().runTaskTimer(plugin, this::tick, 0L, 1L);
    }

    private void tick() {
        adjustBatchSize();

        if (currentJob == null) {
            currentJob = queue.poll();
            if (currentJob != null) {
                Player p = Bukkit.getPlayer(currentJob.playerId);
                if (p != null && p.isOnline()) {
                    p.sendMessage("§e开始生成场景... build_id=" + currentJob.buildId);
                    CommandEntry first = currentJob.commands.isEmpty() ? null : currentJob.commands.get(0);
                    String originText = currentJob.origin == null
                            ? "unknown"
                            : "(" + currentJob.origin.baseX + "," + currentJob.origin.baseY + "," + currentJob.origin.baseZ + ")";
                    String firstText = first == null
                            ? "none"
                            : "(" + first.x + "," + first.y + "," + first.z + ")";
                    p.sendMessage("§7[DEBUG] build_id=" + currentJob.buildId + " origin=" + originText + " first_block="
                            + firstText);
                }
            }
        }

        if (currentJob == null) {
            return;
        }

        Player player = Bukkit.getPlayer(currentJob.playerId);
        World world = player != null ? player.getWorld() : Bukkit.getWorlds().isEmpty() ? null : Bukkit.getWorlds().get(0);
        if (world == null) {
            failAndFinishCurrent("WORLD_NOT_AVAILABLE");
            return;
        }

        int budget = currentBatchSize;
        while (budget-- > 0 && currentJob.index < currentJob.commands.size()) {
            CommandEntry cmd = currentJob.commands.get(currentJob.index++);
            boolean ok = applyOne(world, cmd);
            if (ok) {
                currentJob.executed++;
            } else {
                currentJob.failed++;
            }
        }

        currentJob.ticks++;
        maybeNotifyProgress(player, currentJob);

        if (currentJob.index >= currentJob.commands.size()) {
            finishCurrentJob(player);
        }
    }

    private void adjustBatchSize() {
        long now = System.nanoTime();
        if (lastTickNanos > 0L) {
            long deltaNanos = now - lastTickNanos;
            long deltaMillis = deltaNanos / 1_000_000L;
            if (deltaMillis > 70L) {
                currentBatchSize = Math.max(MIN_BATCH_SIZE, currentBatchSize - BATCH_STEP);
            } else if (deltaMillis < 55L) {
                currentBatchSize = Math.min(MAX_BATCH_SIZE, currentBatchSize + BATCH_STEP);
            }
        }
        lastTickNanos = now;
    }

    private void maybeNotifyProgress(Player player, PayloadJob job) {
        if (player == null || !player.isOnline()) {
            return;
        }
        if (job.ticks % 20 != 0) {
            return;
        }
        int total = job.commands.size();
        int done = job.index;
        int percent = total == 0 ? 100 : (done * 100 / total);
        player.sendMessage("§7生成进度 " + percent + "% (" + done + "/" + total + ")");
    }

    private void finishCurrentJob(Player player) {
        PayloadJob done = currentJob;
        executedBuildIds.add(done.buildId);
        inflightBuildIds.remove(done.buildId);

        long durationMs = Math.max(0L, System.currentTimeMillis() - done.startedAtMs);
        String status = done.failed > 0 ? "PARTIAL" : "EXECUTED";
        String failureCode = done.failed > 0 ? "EXEC_EXCEPTION" : "NONE";
        reportAsync(done.buildId, done.playerName, status, failureCode, done.executed, done.failed, durationMs,
                done.payloadHash);

        if (player != null && player.isOnline()) {
            player.sendMessage("§a生成完成 ✅ executed=" + done.executed + " failed=" + done.failed);
        }

        plugin.getLogger().log(
                Level.INFO,
                "[PayloadExecutorV1] done build_id={0} executed={1} failed={2} queue_depth={3}",
                new Object[] { done.buildId, done.executed, done.failed, queue.size() });

        currentJob = null;
    }

    private void failAndFinishCurrent(String reason) {
        if (currentJob == null) {
            return;
        }
        PayloadJob failedJob = currentJob;
        inflightBuildIds.remove(failedJob.buildId);
        long durationMs = Math.max(0L, System.currentTimeMillis() - failedJob.startedAtMs);
        reportAsync(failedJob.buildId, failedJob.playerName, "REJECTED", reason, failedJob.executed, failedJob.failed,
            durationMs, failedJob.payloadHash);
        Player p = Bukkit.getPlayer(failedJob.playerId);
        if (p != null && p.isOnline()) {
            p.sendMessage("§c[生成失败] " + reason);
        }
        plugin.getLogger().log(Level.WARNING, "[PayloadExecutorV1] failed build_id={0}, reason={1}",
                new Object[] { failedJob.buildId, reason });
        currentJob = null;
    }

    private boolean applyOne(World world, CommandEntry cmd) {
        if (!"setblock".equals(cmd.op)) {
            plugin.getLogger().log(Level.WARNING, "[PayloadExecutorV1] unknown op={0}", cmd.op);
            return false;
        }
        Material material = resolveMaterial(cmd.block);
        if (material == null || material == Material.AIR && !"air".equals(cmd.block)) {
            plugin.getLogger().log(Level.WARNING, "[PayloadExecutorV1] invalid block id={0}", cmd.block);
            return false;
        }
        if (cmd.y < 0 || cmd.y > 320) {
            return false;
        }

        world.getChunkAt(cmd.x >> 4, cmd.z >> 4).load();
        world.getBlockAt(cmd.x, cmd.y, cmd.z).setType(material, false);
        return true;
    }

    private Material resolveMaterial(String blockId) {
        if (blockId == null || blockId.isBlank()) {
            return null;
        }
        String canonical = blockId.toLowerCase(Locale.ROOT).trim();
        if (!canonical.matches("^[a-z0-9_:\\-]+$")) {
            return null;
        }
        if (canonical.contains(":")) {
            canonical = canonical.substring(canonical.indexOf(':') + 1);
        }
        return Material.matchMaterial(canonical.toUpperCase(Locale.ROOT));
    }

    private ValidationResult validatePayload(JsonObject payload) {
        if (!payload.has("version") || !"plugin_payload_v1".equals(asString(payload.get("version")))) {
            return ValidationResult.reject("INVALID_VERSION");
        }

        String buildId = asString(payload.get("build_id"));
        if (buildId == null || buildId.isBlank()) {
            return ValidationResult.reject("MISSING_BUILD_ID");
        }

        if (!payload.has("commands") || !payload.get("commands").isJsonArray()) {
            return ValidationResult.reject("EMPTY_COMMANDS");
        }

        JsonArray commandsArray = payload.getAsJsonArray("commands");
        if (commandsArray.isEmpty()) {
            return ValidationResult.reject("EMPTY_COMMANDS");
        }
        if (commandsArray.size() > MAX_BLOCKS) {
            return ValidationResult.reject("TOO_MANY_BLOCKS");
        }

        java.util.List<CommandEntry> commands = new java.util.ArrayList<>(commandsArray.size());
        for (JsonElement element : commandsArray) {
            if (!element.isJsonObject()) {
                return ValidationResult.reject("INVALID_COMMAND");
            }
            JsonObject cmdObj = element.getAsJsonObject();
            String op = asString(cmdObj.get("op"));
            String block = asString(cmdObj.get("block"));
            Integer x = asInt(cmdObj.get("x"));
            Integer y = asInt(cmdObj.get("y"));
            Integer z = asInt(cmdObj.get("z"));
            if (op == null || block == null || x == null || y == null || z == null) {
                return ValidationResult.reject("INVALID_COMMAND");
            }
            if (y < 0 || y > 320) {
                return ValidationResult.reject("INVALID_COORD");
            }
            if (resolveMaterial(block) == null) {
                return ValidationResult.reject("INVALID_BLOCK_ID");
            }
            commands.add(new CommandEntry(op, x, y, z, block));
        }

        OriginEntry origin = null;
        if (payload.has("origin") && payload.get("origin").isJsonObject()) {
            JsonObject originObj = payload.getAsJsonObject("origin");
            Integer baseX = asInt(originObj.get("base_x"));
            Integer baseY = asInt(originObj.get("base_y"));
            Integer baseZ = asInt(originObj.get("base_z"));
            if (baseX != null && baseY != null && baseZ != null) {
                origin = new OriginEntry(baseX, baseY, baseZ);
            }
        }

        return ValidationResult.ok(buildId, payloadHashFromPayload(payload), commands, origin);
    }

    private String normalizeFailureCode(String code) {
        if ("TOO_MANY_BLOCKS".equals(code) || "INVALID_BLOCK_ID".equals(code) || "OUT_OF_BOUNDS".equals(code)
                || "QUEUE_FULL".equals(code) || "DUPLICATE_BUILD_ID".equals(code)) {
            return code;
        }
        return "INVALID_PAYLOAD";
    }

    private String buildIdFromPayload(JsonObject payload) {
        if (payload != null && payload.has("build_id")) {
            String value = asString(payload.get("build_id"));
            if (value != null && !value.isBlank()) {
                return value;
            }
        }
        return "unknown";
    }

    private String payloadHashFromPayload(JsonObject payload) {
        if (payload != null && payload.has("hash") && payload.get("hash").isJsonObject()) {
            JsonObject hash = payload.getAsJsonObject("hash");
            String value = asString(hash.get("merged_blocks"));
            if (value != null && !value.isBlank()) {
                return value;
            }
        }
        String buildId = buildIdFromPayload(payload);
        return buildId;
    }

    private void reportAsync(
            String buildId,
            String playerId,
            String status,
            String failureCode,
            int executed,
            int failed,
            long durationMs,
            String payloadHash) {
        if (backend == null) {
            return;
        }

        JsonObject report = new JsonObject();
        report.addProperty("build_id", buildId == null || buildId.isBlank() ? "unknown" : buildId);
        report.addProperty("player_id", playerId == null || playerId.isBlank() ? "unknown" : playerId);
        report.addProperty("status", status);
        report.addProperty("failure_code", failureCode);
        report.addProperty("executed", Math.max(0, executed));
        report.addProperty("failed", Math.max(0, failed));
        report.addProperty("duration_ms", Math.max(0L, durationMs));
        report.addProperty("payload_hash", (payloadHash == null || payloadHash.isBlank()) ? "unknown" : payloadHash);

        backend.postJsonAsync("/world/apply/report", GSON.toJson(report), new Callback() {
            @Override
            public void onFailure(Call call, java.io.IOException e) {
                plugin.getLogger().log(Level.WARNING, "[PayloadExecutorV1] report failed build_id={0}: {1}",
                        new Object[] { report.get("build_id").getAsString(), e.getMessage() });
            }

            @Override
            public void onResponse(Call call, Response response) {
                try (response) {
                    if (!response.isSuccessful()) {
                        plugin.getLogger().log(Level.WARNING,
                                "[PayloadExecutorV1] report non-2xx build_id={0} code={1}",
                                new Object[] { report.get("build_id").getAsString(), response.code() });
                    }
                }
            }
        });
    }

    private String asString(JsonElement element) {
        if (element == null || element.isJsonNull() || !element.isJsonPrimitive()) {
            return null;
        }
        return element.getAsString();
    }

    private Integer asInt(JsonElement element) {
        if (element == null || element.isJsonNull() || !element.isJsonPrimitive()) {
            return null;
        }
        try {
            return element.getAsInt();
        } catch (Exception ex) {
            return null;
        }
    }

    private static final class ValidationResult {
        private final boolean ok;
        private final String failureCode;
        private final String buildId;
        private final String payloadHash;
        private final java.util.List<CommandEntry> commands;
        private final OriginEntry origin;

        private ValidationResult(boolean ok, String failureCode, String buildId, String payloadHash,
                java.util.List<CommandEntry> commands, OriginEntry origin) {
            this.ok = ok;
            this.failureCode = failureCode;
            this.buildId = buildId;
            this.payloadHash = payloadHash;
            this.commands = commands;
            this.origin = origin;
        }

        private static ValidationResult reject(String failureCode) {
            return new ValidationResult(false, failureCode, null, null, java.util.List.of(), null);
        }

        private static ValidationResult ok(String buildId, String payloadHash, java.util.List<CommandEntry> commands,
                OriginEntry origin) {
            return new ValidationResult(true, "NONE", buildId, payloadHash, commands, origin);
        }
    }

    private static final class OriginEntry {
        private final int baseX;
        private final int baseY;
        private final int baseZ;

        private OriginEntry(int baseX, int baseY, int baseZ) {
            this.baseX = baseX;
            this.baseY = baseY;
            this.baseZ = baseZ;
        }
    }

    private static final class CommandEntry {
        private final String op;
        private final int x;
        private final int y;
        private final int z;
        private final String block;

        private CommandEntry(String op, int x, int y, int z, String block) {
            this.op = op;
            this.x = x;
            this.y = y;
            this.z = z;
            this.block = block;
        }
    }

    private static final class PayloadJob {
        private final UUID playerId;
        private final String playerName;
        private final String buildId;
        private final String payloadHash;
        private final long startedAtMs;
        private final java.util.List<CommandEntry> commands;
        private final OriginEntry origin;
        private int index = 0;
        private int executed = 0;
        private int failed = 0;
        private int ticks = 0;

        private PayloadJob(UUID playerId, String playerName, String buildId, String payloadHash,
                java.util.List<CommandEntry> commands, OriginEntry origin) {
            this.playerId = playerId;
            this.playerName = playerName;
            this.buildId = buildId;
            this.payloadHash = payloadHash;
            this.startedAtMs = System.currentTimeMillis();
            this.commands = commands;
            this.origin = origin;
        }
    }
}
