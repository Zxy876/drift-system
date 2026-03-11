package com.driftmc.intent;

import java.lang.reflect.Type;
import java.util.HashMap;
import java.util.Map;
import java.util.UUID;

import org.bukkit.Bukkit;
import org.bukkit.ChatColor;
import org.bukkit.entity.Player;
import org.bukkit.plugin.java.JavaPlugin;

import com.driftmc.backend.BackendClient;
import com.driftmc.dsl.DslExecutor;
import com.driftmc.npc.NPCManager;
import com.driftmc.session.PlayerSessionManager;
import com.driftmc.world.WorldPatchExecutor;
import com.google.gson.Gson;
import com.google.gson.JsonObject;
import com.google.gson.JsonParser;
import com.google.gson.reflect.TypeToken;

/**
 * IntentRouter
 * 负责处理自然语言 → 后端 → 世界补丁
 */
public class IntentRouter {

    private static final Gson GSON = new Gson();

    private final JavaPlugin plugin;
    private final BackendClient backend;
    private final DslExecutor dsl;
    private final NPCManager npcs;
    private final WorldPatchExecutor world;
    private final PlayerSessionManager sessions;

    public IntentRouter(
            JavaPlugin plugin,
            BackendClient backend,
            DslExecutor dsl,
            NPCManager npcs,
            WorldPatchExecutor world,
            PlayerSessionManager sessions) {
        this.plugin = plugin;
        this.backend = backend;
        this.dsl = dsl;
        this.npcs = npcs;
        this.world = world;
        this.sessions = sessions;
    }

    /**
     * 玩家说话 → 走后端故事引擎 → world_patch → 世界变化
     */
    public void handlePlayerSpeak(Player player, String text) {

        if (player == null || text == null || text.isEmpty()) {
            return;
        }

        final String trimmed = text.trim();
        if (trimmed.isEmpty()) {
            return;
        }

        final UUID playerUuid = player.getUniqueId();
        final String playerId = player.getName();

        Bukkit.getScheduler().runTaskAsynchronously(plugin, () -> {
            try {
                Map<String, Object> bodyMap = new HashMap<>();
                bodyMap.put("player_id", playerId);
                bodyMap.put("world_state", new HashMap<>());

                Map<String, Object> action = new HashMap<>();
                action.put("say", trimmed);
                bodyMap.put("action", action);

                String body = GSON.toJson(bodyMap);
                String resp = backend.postJson("/story/advance", body);

                Bukkit.getScheduler().runTask(plugin, () -> handleResponse(playerUuid, trimmed, resp));

            } catch (Exception e) {
                Bukkit.getScheduler().runTask(plugin, () -> handleFailure(playerUuid, e));
            }
        });
    }

    private void handleResponse(UUID playerUuid, String text, String resp) {
        Player online = Bukkit.getPlayer(playerUuid);
        if (online == null || !online.isOnline()) {
            return;
        }

        plugin.getLogger().info("[IntentRouter] speak='" + text + "', resp=" + resp);

        try {
            JsonObject root = JsonParser.parseString(resp).getAsJsonObject();
            if (root.has("node") && root.get("node").isJsonObject()) {
                JsonObject node = root.getAsJsonObject("node");
                String title = node.has("title") ? node.get("title").getAsString() : "";
                String t = node.has("text") ? node.get("text").getAsString() : "";

                if (!title.isEmpty()) {
                    online.sendMessage(ChatColor.AQUA + "【" + title + "】");
                }
                if (!t.isEmpty()) {
                    online.sendMessage(ChatColor.WHITE + t);
                }
            }

            if (root.has("world_patch") && root.get("world_patch").isJsonObject()) {
                JsonObject patchObj = root.getAsJsonObject("world_patch");
                Type type = new TypeToken<Map<String, Object>>() {
                }.getType();
                Map<String, Object> patch = GSON.fromJson(patchObj, type);

                plugin.getLogger().info("[IntentRouter] world_patch(from backend) = " + patch);

                if (patch != null && !patch.isEmpty()) {
                    Object mcObj = patch.get("mc");

                    @SuppressWarnings("unchecked")
                    Map<String, Object> mcPatch = (mcObj instanceof Map)
                            ? (Map<String, Object>) mcObj
                            : patch;

                    plugin.getLogger().info("[IntentRouter] mc_patch = " + mcPatch);

                    world.execute(online, mcPatch);
                }
            }

        } catch (Exception parseEx) {
            plugin.getLogger().warning("[IntentRouter] failed to parse response: " + parseEx.getMessage());
            online.sendMessage(ChatColor.RED + "❌ AI 解析失败: " + parseEx.getMessage());
        }
    }

    private void handleFailure(UUID playerUuid, Exception error) {
        Player online = Bukkit.getPlayer(playerUuid);
        plugin.getLogger().warning("[IntentRouter] handlePlayerSpeak error: " + error.getMessage());
        if (online != null && online.isOnline()) {
            online.sendMessage(ChatColor.RED + "❌ AI 解析失败: " + error.getMessage());
        }
    }
}