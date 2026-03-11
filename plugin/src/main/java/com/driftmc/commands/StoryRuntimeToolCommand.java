package com.driftmc.commands;

import java.io.IOException;
import java.lang.reflect.Type;
import java.net.URLEncoder;
import java.nio.charset.StandardCharsets;
import java.util.LinkedHashMap;
import java.util.Map;
import java.util.UUID;

import org.bukkit.Bukkit;
import org.bukkit.Location;
import org.bukkit.command.Command;
import org.bukkit.command.CommandExecutor;
import org.bukkit.command.CommandSender;
import org.bukkit.entity.Player;
import org.bukkit.plugin.java.JavaPlugin;

import com.driftmc.backend.BackendClient;
import com.driftmc.world.WorldPatchExecutor;
import com.google.gson.Gson;
import com.google.gson.JsonElement;
import com.google.gson.JsonObject;
import com.google.gson.JsonParser;
import com.google.gson.reflect.TypeToken;

import net.kyori.adventure.text.Component;
import net.kyori.adventure.text.format.NamedTextColor;

public class StoryRuntimeToolCommand implements CommandExecutor {

    public enum Mode {
        SPAWN_FRAGMENT,
        STORY_RESET
    }

    private static final Gson GSON = new Gson();

    private final JavaPlugin plugin;
    private final BackendClient backend;
    private final WorldPatchExecutor world;
    private final Mode mode;

    public StoryRuntimeToolCommand(JavaPlugin plugin, BackendClient backend, WorldPatchExecutor world, Mode mode) {
        this.plugin = plugin;
        this.backend = backend;
        this.world = world;
        this.mode = mode;
    }

    @Override
    public boolean onCommand(CommandSender sender, Command command, String label, String[] args) {
        if (sender == null) {
            return true;
        }

        if (!(sender instanceof Player player)) {
            sender.sendMessage("只有玩家可以执行该命令。");
            return true;
        }

        String requiredPermission = mode == Mode.SPAWN_FRAGMENT ? "drift.spawn" : "drift.taskdebug";
        if (!player.hasPermission(requiredPermission) && !player.isOp()) {
            player.sendMessage(Component.text("你没有权限执行该运行时工具命令。", NamedTextColor.RED));
            return true;
        }

        if (args.length > 0) {
            player.sendMessage(Component.text("该命令无需参数。", NamedTextColor.RED));
            return true;
        }

        String playerId = player.getName();
        String path = endpointPath(playerId);
        String requestBody = GSON.toJson(buildRequestBody(player));
        UUID playerUuid = player.getUniqueId();

        if (mode == Mode.SPAWN_FRAGMENT) {
            player.sendMessage(Component.text("⏳ 正在生成并投放场景片段...", NamedTextColor.YELLOW));
        } else {
            player.sendMessage(Component.text("⏳ 正在重置你的剧情运行态...", NamedTextColor.YELLOW));
        }

        Bukkit.getScheduler().runTaskAsynchronously(plugin, () -> {
            try {
                String response = backend.postJson(path, requestBody);
                Bukkit.getScheduler().runTask(plugin, () -> handleSuccess(playerUuid, response));
            } catch (IOException | IllegalStateException ex) {
                Bukkit.getScheduler().runTask(plugin, () -> handleFailure(playerUuid, ex));
            }
        });

        return true;
    }

    private Map<String, Object> buildRequestBody(Player player) {
        Map<String, Object> body = new LinkedHashMap<>();

        if (mode == Mode.SPAWN_FRAGMENT) {
            Location loc = player.getLocation();
            Map<String, Object> position = new LinkedHashMap<>();
            position.put("world", player.getWorld().getName());
            position.put("x", loc.getX());
            position.put("y", loc.getY());
            position.put("z", loc.getZ());
            body.put("player_position", position);
        }

        return body;
    }

    private String endpointPath(String playerId) {
        String encodedPlayer = urlSegment(playerId);
        if (mode == Mode.SPAWN_FRAGMENT) {
            return "/world/story/" + encodedPlayer + "/spawnfragment";
        }
        return "/world/story/" + encodedPlayer + "/reset";
    }

    private String urlSegment(String value) {
        return URLEncoder.encode(value, StandardCharsets.UTF_8);
    }

    private void handleSuccess(UUID playerUuid, String rawResponse) {
        Player player = Bukkit.getPlayer(playerUuid);
        if (player == null || !player.isOnline()) {
            return;
        }

        JsonObject root;
        try {
            JsonElement parsed = JsonParser.parseString(rawResponse);
            if (!parsed.isJsonObject()) {
                player.sendMessage(Component.text("❌ 后端返回了非 JSON 响应。", NamedTextColor.RED));
                return;
            }
            root = parsed.getAsJsonObject();
        } catch (RuntimeException ex) {
            player.sendMessage(Component.text("❌ 解析后端响应失败: " + ex.getMessage(), NamedTextColor.RED));
            return;
        }

        String status = getString(root, "status", "error");
        if (!"ok".equalsIgnoreCase(status)) {
            String detail = getString(root, "detail", "");
            if (detail.isEmpty()) {
                detail = getString(root, "msg", "unknown error");
            }
            player.sendMessage(Component.text("❌ 运行时工具执行失败: " + detail, NamedTextColor.RED));
            return;
        }

        applyWorldPatchFromResponse(player, root);

        String msg = getString(root, "msg", "");
        if (msg.isEmpty()) {
            msg = mode == Mode.SPAWN_FRAGMENT ? "Scene fragment generated." : "Story runtime reset completed.";
        }

        player.sendMessage(Component.text("✔ " + msg, NamedTextColor.GREEN));

        if (mode == Mode.SPAWN_FRAGMENT) {
            int fragmentCount = getInt(root, "fragment_count", -1);
            int eventCount = getInt(root, "event_count", -1);
            if (fragmentCount >= 0 || eventCount >= 0) {
                String summary = "fragment_count=" + (fragmentCount >= 0 ? fragmentCount : 0)
                        + " | event_count=" + (eventCount >= 0 ? eventCount : 0);
                player.sendMessage(Component.text(summary, NamedTextColor.GRAY));
            }
            return;
        }

        JsonObject reset = getObject(root, "reset");
        if (reset != null) {
            int clearedPersisted = getInt(reset, "cleared_persisted", 0);
            int clearedInventory = getInt(reset, "cleared_inventory", 0);
            player.sendMessage(Component.text(
                    "cleared_persisted=" + clearedPersisted + " | cleared_inventory=" + clearedInventory,
                    NamedTextColor.GRAY));
        }
    }

    private void handleFailure(UUID playerUuid, Exception error) {
        Player player = Bukkit.getPlayer(playerUuid);
        if (player == null || !player.isOnline()) {
            return;
        }
        player.sendMessage(Component.text("❌ 运行时工具执行失败: " + error.getMessage(), NamedTextColor.RED));
    }

    @SuppressWarnings("unchecked")
    private void applyWorldPatchFromResponse(Player player, JsonObject root) {
        JsonObject patchObj = getObject(root, "world_patch");
        if (patchObj == null) {
            return;
        }

        try {
            Type type = new TypeToken<Map<String, Object>>() {
            }.getType();
            Map<String, Object> patch = GSON.fromJson(patchObj, type);
            if (patch == null || patch.isEmpty()) {
                return;
            }

            Object mcObj = patch.get("mc");
            Map<String, Object> mcPatch;
            if (mcObj instanceof Map<?, ?> mapObj) {
                mcPatch = (Map<String, Object>) mapObj;
            } else {
                mcPatch = patch;
            }

            if (mcPatch.isEmpty()) {
                return;
            }

            world.execute(player, mcPatch);
        } catch (RuntimeException ex) {
            player.sendMessage(Component.text("❌ world_patch 执行失败: " + ex.getMessage(), NamedTextColor.RED));
        }
    }

    private JsonObject getObject(JsonObject root, String key) {
        if (root == null || key == null || !root.has(key)) {
            return null;
        }
        JsonElement value = root.get(key);
        if (value == null || !value.isJsonObject()) {
            return null;
        }
        return value.getAsJsonObject();
    }

    private String getString(JsonObject root, String key, String fallback) {
        if (root == null || key == null || !root.has(key)) {
            return fallback;
        }
        JsonElement value = root.get(key);
        if (value == null || !value.isJsonPrimitive()) {
            return fallback;
        }
        try {
            return value.getAsString();
        } catch (Exception ignored) {
            return fallback;
        }
    }

    private int getInt(JsonObject root, String key, int fallback) {
        if (root == null || key == null || !root.has(key)) {
            return fallback;
        }
        JsonElement value = root.get(key);
        if (value == null || !value.isJsonPrimitive()) {
            return fallback;
        }
        try {
            return value.getAsInt();
        } catch (Exception ignored) {
            return fallback;
        }
    }
}
